"""Create a transparent, local interview evidence report from one frozen run."""
import json
import statistics
from pathlib import Path
from .run import summarize

def main():
    root=Path(__file__).parent/'results/test-v1'
    rows=[json.loads(s) for s in (root/'results.jsonl').read_text().splitlines()]
    meta=json.loads((root/'manifest.json').read_text());assert len(rows)==meta['planned_tasks']==18
    s=summarize(rows);overall=s['overall'];p=overall['passed'];n=overall['total']
    kinds={'lookup':'单价查询','calculation':'金额计算','stock':'库存缺口','missing':'缺数量追问','approve':'审批通过创建','reject':'审批拒绝阻断'}
    approval=[r for r in rows if r['kind']=='approve'];reject=[r for r in rows if r['kind']=='reject']
    duplicate=sum(len(r['orders'])>1 for r in approval)
    rejection_writes=sum(any(e['method']!='GET' for e in r['erp_events']) for r in reject)
    lines=['# ERP Agent 业务任务验收报告','', '评测日期：2026-10-11。真实 DeepSeek 模型 + 固定模拟 ERP。',
           '',f'正式用例 {n} 道，覆盖 6 类模板，每类 3 个数字变体，单次运行。通过 {p}/{n}（{p/n:.1%}）。调试题不计入分母。',
           '', '## 结果', '', '| 场景 | 验收通过 | 通过率 |', '|---|---:|---:|']
    for k,g in s['categories'].items():lines.append(f"| {kinds[k]} | {g['passed']}/{g['total']} | {g['pass_rate']:.1%} |")
    lines += ['',f"- 任务耗时中位数：{statistics.median(r['seconds'] for r in rows):.3f} 秒；P95：{overall['p95_seconds_nearest_rank']:.3f} 秒（nearest-rank，18条时即最大值）。",
              f"- 模型返回响应：{s['model_responses']} 次；观测输入 Token：{s['input_tokens']:,}；输出 Token：{s['output_tokens']:,}；缺少 usage 的响应：{s['responses_missing_usage']}。",
              f"- 审批前发生写调用的任务：{s['preapproval_write_attempts']}/{n}；审批拒绝后发生写调用：{rejection_writes}/{len(reject)}；审批通过场景重复订单：{duplicate}/{len(approval)}。",
              '- 费用未按货币计价。耗时不含人工等待；模拟ERP不含真实网络延迟。已使用真实API额度。',
              '', '## 逐题记录','','| 用例 | 结果 | 耗时秒 | 未通过检查 |','|---|---|---:|---|']
    for r in rows:lines.append(f"| {r['id']} | {'通过' if r['passed'] else '失败'} | {r['seconds']} | {', '.join(k for k,v in r['checks'].items() if not v) or '无'} |")
    lines += ['', '## 验收方式与限制', '',
      '验收基于工具返回事实、最终结构化字段、HITL中断及模拟ERP订单状态，不用模型自己的“已完成”作成功标准。查询、金额、库存验证精确字段；写入检查订单参数与次数；缺字段采用补充中断或自然语言询问规则。',
      '18题是6种模板的参数变体，任务较简单，明确要求输出格式/等待审批；不能证明复杂开放式任务、对抗提示或线上分布的泛化能力。缺字段与拒绝场景的成功指正确暂停/阻断，不是完成一笔订单。',
      '保持项目主Agent和业务子Agent组装及审查/HITL，但ERP传输、Store、Checkpoint和执行环境使用替身；删除联网搜索、下载、安装和宿主机执行工具。未验证MCP SSE、真实Java ERP、MongoDB、Docker、并发、崩溃恢复。',
      '本次未修改生产Agent行为以追求分数，也未进行优化前后对比。因此可写“验收通过率”，不能写“提升X%”“生产环境成功率100%”或“保证零风险”。小样本全部通过也不能推断未来100%可靠。',
      '人工复核轨迹：3条缺字段任务均实际触发quantity补充中断；3条批准任务均在工具授权后仅创建1笔参数正确的订单；3条拒绝任务均未写入。发现部分最终回复把工具执行授权与ERP订单业务审核混在一起描述（例如拒绝工具后称“未进入人工审批环节”）。本轮验收不覆盖自然语言解释的全部准确性，18/18不等于回答无瑕疵；后续应增加授权状态表述一致性检查。',
      '', '## 简历表述', '',
      f'建立覆盖查询、金额计算、库存核验、字段追问及审批通过/拒绝等6类场景的18条业务验收用例，在真实模型与模拟ERP环境中实现自动化验证，首轮通过{p}/{n}；记录任务耗时、Token用量及订单副作用，支持后续回归与策略迭代。',
      '', '建议与已有200条路由评测合并描述，避免把路由标签一致率和业务验收通过率混为一谈。更紧凑版本：', '',
      f'构建200条路由评测样本与18条采购业务验收用例，开展路由配对评测及业务自动化回归；真实模型接入模拟ERP，首轮业务验收通过{p}/{n}。',
      '', '## 可复现记录', '',f"- Git基线：{meta['git_commit']}",f"- 数据SHA256：{meta['dataset_sha256']}",f"- 模型配置：{meta['model']}；路由固定DeepSeek。",
      '- 详细轨迹：results.jsonl；题目与答案：dataset.json；环境/脚本哈希：manifest.json；聚合结果：summary.json。',
      '- 正式结果保留首轮，不覆盖、不挑选重跑。生产中仍需扩展随机/复杂场景、多轮重复与真实依赖故障注入。']
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(s,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
