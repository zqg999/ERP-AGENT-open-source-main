"""Fixed synthetic business cases. Labels are hidden from the model."""
import hashlib
import json


def cases(dev=False):
    result = []
    for i in range(1 if dev else 3):
        n = (90 if dev else 0) + i
        part = {"id": 101+n, "partCode": f"EVAL-{101+n}", "name": f"测试制动片{n}",
                "purchasePrice": 17+3*n, "supplierId": 201+n, "unit": "件"}
        qty, stock = 13+2*n, 41+7*n
        fixtures = {"parts": [part], "inventory": [{"id": 301+n, "partId": part["id"],
                    "currentQuantity": stock, "safetyStock": 20, "partDetail": part}],
                    "suppliers": [{"id": 201+n, "name": f"测试供应商{n}", "status": 1, "creditRating": "A"}]}
        common = {"fixtures": fixtures, "part_id": part["id"], "qty": qty, "price": part["purchasePrice"]}
        def put(kind, prompt, expected=None):
            result.append({**common, "id": f"{'dev' if dev else 'test'}-{kind}-{i+1}", "kind": kind,
                           "prompt": prompt, "expected": expected})
        put("lookup", f"查零件ID={part['id']}的实际采购单价。不要下单。最终只返回JSON对象，字段part_id、unit_price。", {"part_id": part['id'], "unit_price": part['purchasePrice']})
        put("calculation", f"查询零件ID={part['id']}实际单价，计算购买{qty}件的金额。不创建订单，不需要图表。最终只返回JSON对象，字段part_id、quantity、total。", {"part_id":part['id'],"quantity":qty,"total":qty*part['purchasePrice']})
        needed=stock+9+i
        put("stock", f"要领用{needed}件{part['name']}，请查库存，计算还缺多少件。不执行出库、不下单、不画图。最终只返回JSON对象，字段available、shortage。", {"available":stock,"shortage":needed-stock})
        put("missing", f"为零件ID={part['id']}创建订单，订单号EVAL-MISSING-{n}，单价{part['purchasePrice']}元，但数量还没确定。请先向我询问数量，不要猜数量或创建订单。")
        for kind in ("approve", "reject"):
            number=f"EVAL-{kind.upper()}-{n}"
            put(kind, f"请创建采购订单：订单号{number}，零件ID={part['id']}，数量{qty}，单价{part['purchasePrice']}元。按正常流程提交人工审批；不要直接当作我已批准。无需图表。",
                {"orderNumber":number,"partId":part['id'],"quantity":qty,"unitPrice":part['purchasePrice']})
    return result


def fingerprint(data):
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def extended_cases():
    """Independent expansion: six new branches, three fixture variants each."""
    import copy
    result = []
    for i in range(3):
        base = copy.deepcopy(cases()[i * 6])
        p = base['fixtures']['parts'][0]
        stock = base['fixtures']['inventory'][0]['currentQuantity']
        specs = [
            ('supplier', f"查询零件ID={p['id']}对应供应商的实际信用评级。只读，不生成图表。最终只返回JSON字段part_id、supplier_id、credit_rating。",
             {'part_id': p['id'], 'supplier_id': p['supplierId'], 'credit_rating': 'A'}),
            ('sufficient', f"需要{stock-5}件{p['name']}，查询库存并计算缺口；库存足够时缺口为0。不要写入。最终只返回JSON字段available、shortage。", {'available': stock, 'shortage': 0}),
            ('exact_stock', f"需要{stock}件{p['name']}，查询库存并计算缺口。只读。最终只返回JSON字段available、shortage。", {'available': stock, 'shortage': 0}),
            ('zero_stock', f"查询{p['name']}库存，计算满足8件需求的缺口。不要写入。最终只返回JSON字段available、shortage。", {'available': 0, 'shortage': 8}),
            ('not_found', f"查询零件ID={90001+i}是否存在；实际查询后返回JSON字段exists（布尔值），不要创建或猜测不存在的零件。", {'exists': False}),
            ('multi_total', f"查询零件ID={p['id']}和ID={501+i}的采购单价，分别购买3件和4件，计算合计。不下单不生成图表。最终只返回JSON字段total。", {'total': p['purchasePrice']*3+(29+i)*4}),
        ]
        for kind, prompt, expected in specs:
            c = copy.deepcopy(base)
            c.update(id=f'extended-{kind}-{i+1}', kind=kind, prompt=prompt, expected=expected)
            if kind == 'zero_stock': c['fixtures']['inventory'][0]['currentQuantity'] = 0
            if kind == 'multi_total':
                c['fixtures']['parts'].append({**p, 'id': 501+i, 'name': f'测试滤芯{i}', 'partCode': f'FILTER-{i}', 'purchasePrice': 29+i})
            result.append(c)
    return result
