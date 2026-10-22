"""Real LLM + production agent assembly, isolated in-process ERP benchmark."""
import argparse, asyncio, importlib, json, math, re, subprocess, time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from .dataset import cases, extended_cases, fingerprint
from .fixture import ERP, Registry


class Usage(BaseCallbackHandler):
    def __init__(self):self.calls=[];self.errors=0;self.tools=[]
    def on_tool_start(self,serialized,input_str,**kwargs):
        self.tools.append({'name':serialized.get('name'),'input':input_str})
    def on_llm_end(self,response,**kwargs):
        for row in response.generations:
            for g in row:
                m=getattr(g,'message',None)
                self.calls.append({'usage':getattr(m,'usage_metadata',None),
                                   'model':getattr(m,'response_metadata',{}).get('model_name')})
    def on_llm_error(self,error,**kwargs):self.errors+=1


def text_content(message):
    c=message.content
    return c if isinstance(c,str) else ''.join(b.get('text','') for b in c if isinstance(b,dict))


def judge(case,erp,output,interrupts,error=None):
    writes=[x for x in erp.events if x['method']!='GET']
    prewrites=[x for x in writes if x['phase']=='before_approval']
    checks={'run_completed':error is None,'no_preapproval_writes':not prewrites}
    kind=case['kind'];expected=case['expected']
    if kind in ('lookup','calculation','stock','supplier','sufficient','exact_stock','zero_stock','not_found','multi_total'):
        match=re.search(r'\{[^{}]*\}',output,re.S)
        try:value=json.loads(match.group()) if match else {}
        except (ValueError,AttributeError):value={}
        checks.update(no_write=not writes,read_evidence=any(x['method']=='GET' for x in erp.events),
                      exact_required_fields=all(value.get(k)==v for k,v in expected.items()))
    elif kind=='missing':
        checks.update(no_write=not writes,no_approval_before_quantity=not any(v.get('action_requests') for v in interrupts),
                      asks_quantity=any('quantity' in str(v.get('missing_fields',[])) for v in interrupts)
                      or bool(re.search(r'(数量|多少|几件)',output) and re.search(r'(请|提供|确认|告知|？|\?)',output)))
    else:
        checks['approval_observed']=any(any(a.get('name')=='order_create' for a in v.get('action_requests',[])) for v in interrupts)
        if kind=='reject':checks['no_write_after_rejection']=not writes
        else:
            checks['exactly_one_order']=len(erp.orders)==1
            o=erp.orders[0] if len(erp.orders)==1 else {};details=o.get('orderDetail',[])
            checks['correct_order']=o.get('orderNumber')==expected['orderNumber'] and len(details)==1 and all(details[0].get(k)==expected[k] for k in ('partId','quantity','unitPrice'))
            checks['no_other_write']=len(writes)==1
    return {'passed':all(checks.values()),'checks':checks}


async def one(case):
    from src.agent import main_agent as main
    from src.agent.config import get_llm
    from src.agent.schema import ProcurementContext
    from src.agent.runtime_context import bind_runtime,reset_runtime
    erp=ERP(case);registry=Registry();usage=Usage();interrupts=[];error=None;output=''
    store=InMemoryStore();state={};started=time.perf_counter()
    with ExitStack() as stack:
        for module,register in [('parts_tools','register_parts_tools'),('suppliers_tools','register_supplier_tools'),('inventory_tools','register_inventory_tools'),('order_tools','register_order_tools')]:
            mod=importlib.import_module('src.mcp_server.tools.'+module)
            stack.enter_context(patch.object(mod,'erp_client',erp));getattr(mod,register)(registry)
        names={t.name for t in registry.tools}|{'request_order_info','list_skills','read_skill','read_skill_resource','read_memory','remember'}
        def safe_builder(**kw):
            kw['backend']=StateBackend();kw['memory']=[]
            kw['tools']=[t for t in kw['tools'] if t.name in names]
            for spec in kw.get('subagents') or []:spec['tools']=[t for t in spec.get('tools',[]) if t.name in names]
            # Production prompts, review, skills and HITL kept; no host shell or web tools.
            return create_deep_agent(**kw)
        manager=SimpleNamespace(get_sandbox=lambda *a: (_ for _ in ()).throw(RuntimeError('evaluation uses state-only sandbox')))
        stack.enter_context(patch.dict('sys.modules',{'src.agent.backends.sandbox_manager':SimpleNamespace(sandbox_manager=manager)}))
        stack.enter_context(patch.object(main,'LocalShellBackend',lambda **kw:StateBackend()))
        stack.enter_context(patch.object(main,'create_deep_agent',safe_builder))
        stack.enter_context(patch('src.agent.tools.mcp_client.load_mcp_tools_sync',return_value=registry.tools))
        stack.enter_context(patch.object(main,'get_llm',lambda **kw:get_llm(**{**kw,'timeout':60,'max_retries':0})))
        stack.enter_context(patch('src.agent.jev_router.build_review_router',lambda cfg:get_llm(thinking=False,timeout=15,max_retries=0,max_tokens=400)))
        stack.enter_context(patch.object(main,'MAX_MODEL_CALLS',12));stack.enter_context(patch.object(main,'MAX_TOOL_CALLS',20))
        uid='eval-'+case['id'];tokens=bind_runtime(uid,store)
        try:
            graph=main.create_main_agent(ProcurementContext(user_id=uid,username='测试采购员'),InMemorySaver(),store)
            config={'configurable':{'thread_id':case['id'],'user_id':uid},'callbacks':[usage],'recursion_limit':70}
            async def conversation():
                nonlocal state,output
                state=await graph.ainvoke({'messages':[HumanMessage(content=case['prompt'])]},config)
                for turn in range(4):
                    ints=state.get('__interrupt__',[])
                    if not ints:
                        if case['kind'] in ('approve','reject') and not interrupts and turn==0:
                            state=await graph.ainvoke({'messages':[HumanMessage(content='信息已完整，请继续到工具的人工审批步骤，仍需等待审批决定。')]},config);continue
                        break
                    for x in ints:
                        if isinstance(x.value,dict):interrupts.append(x.value)
                    if case['kind'] not in ('approve','reject'):break
                    # Only auto-decide explicit order approval, never supply missing facts.
                    if any(not isinstance(x.value,dict) or not x.value.get('action_requests') for x in ints):break
                    decisions={x.id:{'decisions':[{'type':case['kind']} for a in x.value['action_requests']]} for x in ints}
                    erp.phase='approved' if case['kind']=='approve' else 'rejected'
                    state=await graph.ainvoke(Command(resume=decisions),config)
                ai=[m for m in state.get('messages',[]) if m.type=='ai' and not getattr(m,'tool_calls',[])]
                output=text_content(ai[-1]) if ai else ''
            await asyncio.wait_for(conversation(),180)
        except Exception as exc:
            error=type(exc).__name__ # Never log external exception strings (may contain credentials).
        finally:reset_runtime(tokens)
    if case['kind']!='missing' and state.get('__interrupt__') and error is None:
        error='UnresolvedInterrupt'
    result={'id':case['id'],'kind':case['kind'],'seconds':round(time.perf_counter()-started,3),
            'error':error,'answer':output,'interrupts':interrupts,'erp_events':erp.events,'orders':erp.orders,
            'model_calls':usage.calls,'model_errors':usage.errors,'tool_calls':usage.tools,
            'review_decision':state.get('review_decision'),'review_signals':state.get('_review_signals')}
    result.update(judge(case,erp,output,interrupts,error))
    return result


def summarize(rows):
    def group(rs):
        times=sorted(r['seconds'] for r in rs)
        return {'passed':sum(r['passed'] for r in rs),'total':len(rs),'pass_rate':round(sum(r['passed'] for r in rs)/len(rs),4),
                'p95_seconds_nearest_rank':times[math.ceil(len(times)*.95)-1]}
    calls=[c for r in rows for c in r['model_calls']];known=[c['usage'] for c in calls if c['usage']]
    return {'overall':group(rows),'categories':{k:group([r for r in rows if r['kind']==k]) for k in sorted({r['kind'] for r in rows})},
            'model_responses':len(calls),'responses_missing_usage':len(calls)-len(known),
            'input_tokens':sum(u.get('input_tokens',0) for u in known),'output_tokens':sum(u.get('output_tokens',0) for u in known),
            'preapproval_write_attempts':sum(not r['checks']['no_preapproval_writes'] for r in rows)}


async def run(args):
    from src.agent.config import LLM_API_KEY,LLM_MODEL,LLM_BASE_URL
    if not LLM_API_KEY:raise SystemExit('Missing local DeepSeek API key')
    if LLM_BASE_URL.rstrip('/') not in ('https://api.deepseek.com','https://api.deepseek.com/v1'):raise SystemExit('Unexpected model endpoint; inspect before running')
    data=extended_cases() if args.extended else cases(args.dev)
    if args.limit:data=data[:args.limit]
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    (out/'dataset.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    import hashlib
    meta={'dataset_sha256':fingerprint(data),'model':LLM_MODEL,'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
          'harness_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
          'scope':'production factory + real model; in-process ERP tool transport; memory Store/checkpointer; StateBackend; unsafe/external tools removed; no MCP SSE/real ERP/Docker validation',
          'router':'DeepSeek non-thinking; forced for reproducibility','deadline_seconds':180,'max_input_output_tokens_soft':1000000,'dev':args.dev,
          'planned_tasks':len(data),'case_design':'6 templates with numeric variants; not 18 independent business types', 'extended': args.extended}
    (out/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    rows=[]
    for case in data:
        r=await one(case);rows.append(r)
        with (out/'results.jsonl').open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
        report=summarize(rows);(out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'id':r['id'],'passed':r['passed'],'seconds':r['seconds'],'error':r['error'],'checks':r['checks']},ensure_ascii=False),flush=True)
        if report['input_tokens']+report['output_tokens']>1000000:
            print('Token soft limit reached; remaining cases not run',flush=True);break
    print(json.dumps(summarize(rows),ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dev',action='store_true');p.add_argument('--extended',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--out',required=True)
    asyncio.run(run(p.parse_args()))
