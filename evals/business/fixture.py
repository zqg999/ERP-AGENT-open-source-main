"""In-process ERP transport fixture. Never contacts a real ERP."""
import copy
from langchain_core.tools import StructuredTool


class Registry:
    def __init__(self): self.tools=[]
    def tool(self):
        def register(fn):
            self.tools.append(StructuredTool.from_function(coroutine=fn,name=fn.__name__,description=fn.__doc__))
            return fn
        return register


class ERP:
    def __init__(self,case):
        self.data=copy.deepcopy(case['fixtures']);self.orders=[];self.events=[];self.phase='before_approval'
    def answer(self,data=None,code=200,message='success'):
        return {'code':code,'message':message,'data':data}
    async def get(self,path,params=None,**kwargs):
        params=params or {};self.events.append({'method':'GET','path':path,'params':params,'phase':self.phase})
        group = next((g for g in ('parts','suppliers','inventory','orders') if f'/{g}/' in path),None)
        rows=copy.deepcopy(self.orders if group=='orders' else self.data.get(group,[]))
        if '/get/' in path:
            value=next((r for r in rows if r['id']==int(path.rsplit('/',1)[1])),None)
            return self.answer(value,200 if value else 404,'success' if value else 'not found')
        name=params.get('name') or params.get('partName')
        if name: rows=[r for r in rows if name in r.get('name',r.get('partDetail',{}).get('name',''))]
        if '/supplier/' in path: rows=[r for r in rows if r.get('supplierId')==int(path.rsplit('/',1)[1])]
        if path.endswith('/page'):
            current,size=params.get('current',1),params.get('size',10)
            return self.answer({'records':rows[(current-1)*size:current*size],'total':len(rows),'current':current,'size':size,'pages':1})
        if path.endswith('/search'):return self.answer(rows)
        if path.endswith('/warning'):return self.answer([r for r in rows if r['currentQuantity']<r['safetyStock']])
        return self.answer(None,501,'Fixture endpoint not implemented')
    async def post(self,path,json_data=None,params=None,**kwargs):
        self.events.append({'method':'POST','path':path,'data':json_data,'params':params,'phase':self.phase})
        if path!='/api/orders/create':return self.answer(None,501,'Fixture write endpoint not implemented')
        # Do not deduplicate: repeated creates must remain visible to the evaluator.
        order=copy.deepcopy(json_data or {});order['id']=7001+len(self.orders);self.orders.append(order)
        return self.answer(order)
    async def put(self,path,**kwargs):return await self.post(path,**kwargs)
    async def delete(self,path,**kwargs):return await self.post(path,**kwargs)
