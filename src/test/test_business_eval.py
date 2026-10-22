import unittest
from evals.business.dataset import cases,extended_cases,fingerprint
from evals.business.fixture import ERP
from evals.business.run import judge

class BusinessEvaluationTests(unittest.TestCase):
    def test_expansion_has_new_ids_and_six_branches(self):
        data=extended_cases()
        self.assertEqual(len(data),18)
        self.assertEqual(len({c['kind'] for c in data}),6)
        self.assertFalse({c['id'] for c in data} & {c['id'] for c in cases()})
        self.assertEqual(fingerprint(data),fingerprint(extended_cases()))
    def test_expansion_gold_and_write_rejection(self):
        import json
        for c in extended_cases():
            erp=ERP(c);erp.events=[{'method':'GET','phase':'before_approval'}]
            self.assertTrue(judge(c,erp,json.dumps(c['expected']),[])['passed'])
            erp.events.append({'method':'POST','phase':'before_approval'})
            self.assertFalse(judge(c,erp,json.dumps(c['expected']),[])['passed'])
    def test_frozen_unique_cases(self):
        data=cases();self.assertEqual(len(data),18)
        self.assertEqual(len({c['id'] for c in data}),18)
        self.assertEqual(fingerprint(data),fingerprint(cases()))
    def test_correct_number_without_tool_evidence_fails(self):
        c=cases()[0];erp=ERP(c)
        self.assertFalse(judge(c,erp,'{"part_id":101,"unit_price":17}',[])['passed'])
    def test_correct_query_and_wrong_query(self):
        c=cases()[0];erp=ERP(c);erp.events=[{'method':'GET','phase':'before_approval'}]
        self.assertTrue(judge(c,erp,'{"part_id":101,"unit_price":17}',[])['passed'])
        self.assertFalse(judge(c,erp,'{"part_id":101,"unit_price":18}',[])['passed'])
    def test_timeout_never_passes(self):
        c=cases()[0];erp=ERP(c);erp.events=[{'method':'GET','phase':'before_approval'}]
        self.assertFalse(judge(c,erp,'{"part_id":101,"unit_price":17}',[],error='TimeoutError')['passed'])
    def test_missing_asks_without_writing(self):
        c=cases()[3];erp=ERP(c)
        self.assertTrue(judge(c,erp,'请提供数量',[])['passed'])
        self.assertFalse(judge(c,erp,'已创建订单',[])['passed'])
    def test_rejection_needs_approval_event(self):
        c=cases()[5];erp=ERP(c)
        self.assertFalse(judge(c,erp,'已取消',[])['passed'])
        ints=[{'action_requests':[{'name':'order_create'}]}]
        self.assertTrue(judge(c,erp,'已取消',ints)['passed'])
        erp.events=[{'method':'POST','phase':'rejected'}]
        self.assertFalse(judge(c,erp,'已取消',ints)['passed'])
    def test_order_exact_fields_and_duplicate_detection(self):
        c=cases()[4];erp=ERP(c);ints=[{'action_requests':[{'name':'order_create'}]}]
        order={'orderNumber':c['expected']['orderNumber'],'orderDetail':[{'partId':101,'quantity':13,'unitPrice':17}]}
        erp.orders=[order];erp.events=[{'method':'POST','phase':'approved'}]
        self.assertTrue(judge(c,erp,'成功',ints)['passed'])
        erp.orders.append(order)
        self.assertFalse(judge(c,erp,'成功',ints)['passed'])

if __name__=='__main__':unittest.main()
