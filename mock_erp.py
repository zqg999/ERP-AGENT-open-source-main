"""Mock ERP HTTP Server —— 让 Agent 能调工具的最小后端（监听 8081）"""
import copy
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI(title="Mock ERP")


# ============ 假数据 ============
SUPPLIERS = [
    {"id": 1, "name": "博世", "contact": "张经理", "phone": "13800000001",
     "status": 1, "creditRating": "A", "address": "上海"},
    {"id": 2, "name": "电装", "contact": "李经理", "phone": "13800000002",
     "status": 1, "creditRating": "A", "address": "北京"},
    {"id": 3, "name": "大陆集团", "contact": "王经理", "phone": "13800000003",
     "status": 1, "creditRating": "B", "address": "广州"},
    {"id": 4, "name": "德尔福", "contact": "赵经理", "phone": "13800000004",
     "status": 0, "creditRating": "C", "address": "深圳"},
]

PARTS = [
    {"id": 101, "name": "火花塞", "supplierId": 1, "unitPrice": 35.0, "spec": "M14x1.25"},
    {"id": 102, "name": "喷油嘴", "supplierId": 2, "unitPrice": 88.5, "spec": "4孔"},
    {"id": 103, "name": "刹车片", "supplierId": 3, "unitPrice": 120.0, "spec": "前轮"},
    {"id": 104, "name": "空气滤清器", "supplierId": 1, "unitPrice": 45.0, "spec": "通用"},
]

INVENTORY = [
    {"id": 201, "partId": 101, "currentQuantity": 500, "safetyStock": 100, "warehouse": "A1"},
    {"id": 202, "partId": 102, "currentQuantity": 80, "safetyStock": 100, "warehouse": "A2"},
    {"id": 203, "partId": 103, "currentQuantity": 300, "safetyStock": 50, "warehouse": "B1"},
    {"id": 204, "partId": 104, "currentQuantity": 200, "safetyStock": 30, "warehouse": "B2"},
]

ORDERS = []


def ok(data, code=200, message="success"):
    return {"code": code, "message": message, "data": data}


def _by_name(rows, name):
    return [r for r in rows if name and name in r.get("name", "")]


def _page(rows, current, size):
    total = len(rows)
    start = (current - 1) * size
    return {"records": rows[start:start + size], "total": total,
            "current": current, "size": size,
            "pages": max(1, (total + size - 1) // size)}


# ============ 供应商 ============
@app.get("/api/suppliers/search")
async def s_search(name: str = ""):
    rows = _by_name(SUPPLIERS, name)
    return ok(rows if rows else SUPPLIERS)


@app.get("/api/suppliers/page")
async def s_page(current: int = 1, size: int = 10, name: str = None,
                 status: int = None, credit_rating: str = None):
    rows = copy.deepcopy(SUPPLIERS)
    if name: rows = _by_name(rows, name)
    if status is not None: rows = [r for r in rows if r["status"] == status]
    if credit_rating: rows = [r for r in rows if r["creditRating"] == credit_rating]
    return ok(_page(rows, current, size))


@app.get("/api/suppliers/get/{sid}")
async def s_get(sid: int):
    row = next((r for r in SUPPLIERS if r["id"] == sid), None)
    return ok(row) if row else ok(None, 404, "not found")


# ============ 零件 ============
@app.get("/api/parts/search")
async def p_search(partName: str = "", name: str = ""):
    key = partName or name
    rows = _by_name(PARTS, key)
    return ok(rows if rows else PARTS)


@app.get("/api/parts/page")
async def p_page(current: int = 1, size: int = 10, name: str = None):
    rows = copy.deepcopy(PARTS)
    if name: rows = _by_name(rows, name)
    return ok(_page(rows, current, size))


@app.get("/api/parts/get/{pid}")
async def p_get(pid: int):
    row = next((r for r in PARTS if r["id"] == pid), None)
    return ok(row) if row else ok(None, 404, "not found")


@app.get("/api/parts/by-supplier/{sid}")
async def p_by_sup(sid: int):
    return ok([r for r in PARTS if r["supplierId"] == sid])


# ============ 库存 ============
@app.get("/api/inventory/page")
async def i_page(current: int = 1, size: int = 10):
    return ok(_page(copy.deepcopy(INVENTORY), current, size))


@app.get("/api/inventory/warning")
async def i_warn():
    return ok([r for r in INVENTORY if r["currentQuantity"] < r["safetyStock"]])


@app.get("/api/inventory/check")
async def i_check(partId: int = None):
    if partId is None:
        return ok([])
    row = next((r for r in INVENTORY if r["partId"] == partId), None)
    return ok(row) if row else ok(None, 404, "not found")


@app.get("/api/inventory/get/{iid}")
async def i_get(iid: int):
    row = next((r for r in INVENTORY if r["id"] == iid), None)
    return ok(row) if row else ok(None, 404, "not found")


@app.post("/api/inventory/inbound")
async def i_in(request: Request):
    payload = await request.json()
    return ok({"message": "inbound ok", "payload": payload})


@app.post("/api/inventory/outbound")
async def i_out(request: Request):
    payload = await request.json()
    return ok({"message": "outbound ok", "payload": payload})


# ============ 订单 ============
@app.get("/api/orders/page")
async def o_page(current: int = 1, size: int = 10):
    return ok(_page(copy.deepcopy(ORDERS), current, size))


@app.get("/api/orders/get/{oid}")
async def o_get(oid: int):
    row = next((r for r in ORDERS if r["id"] == oid), None)
    return ok(row) if row else ok(None, 404, "not found")


@app.get("/api/orders/search-details")
async def o_search():
    return ok(copy.deepcopy(ORDERS))


@app.get("/api/orders/statistics")
async def o_stat():
    return ok({"total": len(ORDERS),
               "amount": sum(o.get("amount", 0) for o in ORDERS)})


@app.post("/api/orders/create")
async def o_create(request: Request):
    payload = await request.json()
    order = copy.deepcopy(payload or {})
    order["id"] = 7001 + len(ORDERS)
    ORDERS.append(order)
    return ok(order)


@app.put("/api/orders/update")
async def o_update(request: Request):
    return ok(await request.json())


@app.put("/api/orders/update-status")
async def o_status(request: Request):
    return ok(await request.json())


# ============ 健康检查 ============
@app.get("/")
async def root():
    return {"status": "ok", "service": "Mock ERP"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8081)