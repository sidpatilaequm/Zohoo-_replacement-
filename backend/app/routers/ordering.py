"""Sales orders, deliveries and goods issue."""
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from .. import models as M, schemas as S
from ..deps import Ctx, need
from ..inventory import (D0, TOL, require_trading, on_hand, post_move,
                         delivered_on, so_status, suggest_picks)

router = APIRouter(tags=["ordering"])


def _sellable(ctx, mid):
    return sum((r["qty"] for r in on_hand(ctx, mid) if r["stock_type"] == "NORMAL"), D0)


@router.get("/sales-orders")
def list_so(ctx: Ctx = Depends(need("so"))):
    require_trading(ctx)
    out = []
    for o in ctx.db.execute(ctx.scope(select(M.SalesOrder), M.SalesOrder)
                            .order_by(M.SalesOrder.doc_date.desc())).scalars():
        lines = []
        for l in sorted(o.lines, key=lambda x: x.line_no):
            done = delivered_on(ctx, o.id, l.material_id)
            lines.append({"material_id": l.material_id, "code": l.material.code,
                          "descr": l.material.descr, "uom": l.material.uom,
                          "batch_managed": l.material.batch_managed,
                          "qty": float(l.qty), "price": float(l.price),
                          "delivered": float(done),
                          "outstanding": float(Decimal(str(l.qty)) - done),
                          "available": float(_sellable(ctx, l.material_id))})
        out.append({"id": o.id, "doc_no": o.doc_no, "doc_date": o.doc_date,
                    "req_date": o.req_date, "customer": o.customer.name,
                    "customer_id": o.customer_id, "cust_ref": o.cust_ref,
                    "status": so_status(ctx, o), "lines": lines,
                    "value": float(sum(Decimal(str(l.qty)) * Decimal(str(l.price))
                                       for l in o.lines))})
    return out


@router.post("/sales-orders", status_code=201)
def add_so(body: S.SalesOrderIn, ctx: Ctx = Depends(need("so"))):
    require_trading(ctx)
    c = ctx.get(M.Customer, body.customer_id)
    if not c:
        raise HTTPException(422, "No such customer in this organisation")
    doc_no = body.doc_no or f"SO/{ctx.tenant.id}/{len(ctx.db.execute(ctx.scope(select(M.SalesOrder), M.SalesOrder)).scalars().all()) + 1:03d}"
    if ctx.db.execute(ctx.scope(select(M.SalesOrder), M.SalesOrder)
                      .where(M.SalesOrder.doc_no == doc_no)).scalar_one_or_none():
        raise HTTPException(409, f"Sales order {doc_no} already exists")
    o = M.SalesOrder(tenant_id=ctx.tenant.id, doc_no=doc_no, doc_date=body.doc_date,
                     req_date=body.req_date, customer_id=c.id, cust_ref=body.cust_ref)
    ctx.db.add(o)
    ctx.db.flush()
    short = []
    for n, li in enumerate(body.lines, 1):
        m = ctx.get(M.Material, li.material_id)
        if not m:
            raise HTTPException(422, f"Line {n}: that material does not exist here")
        price = li.price if li.price is not None else m.price
        ctx.db.add(M.SoLine(so_id=o.id, line_no=n, material_id=m.id,
                            qty=li.qty, price=price))
        avail = _sellable(ctx, m.id)
        if Decimal(str(li.qty)) > avail + TOL:
            short.append({"material": m.code, "ordered": float(li.qty),
                          "available": float(avail)})
    ctx.db.commit()
    ctx.db.refresh(o)
    return {"id": o.id, "doc_no": o.doc_no, "short": short,
            "note": ("The order is taken; these lines cannot be delivered in full until stock arrives."
                     if short else "Everything ordered is on hand.")}


@router.delete("/sales-orders/{sid}", status_code=204)
def del_so(sid: int, ctx: Ctx = Depends(need("so"))):
    o = ctx.get(M.SalesOrder, sid)
    if not o:
        raise HTTPException(404, "No such sales order")
    if so_status(ctx, o) != "OPEN":
        raise HTTPException(409, "Something has already been delivered against that order")
    ctx.db.delete(o)
    ctx.db.commit()


@router.get("/deliveries/suggest/{so_id}")
def suggest(so_id: int, ctx: Ctx = Depends(need("del"))):
    """Propose picks for what is still outstanding, earliest expiry first."""
    require_trading(ctx)
    o = ctx.get(M.SalesOrder, so_id)
    if not o:
        raise HTTPException(404, "No such sales order")
    out = []
    for l in sorted(o.lines, key=lambda x: x.line_no):
        done = delivered_on(ctx, o.id, l.material_id)
        want = Decimal(str(l.qty)) - done
        picks = suggest_picks(ctx, l.material_id, want) if want > TOL else []
        avail = [{"batch": r["batch"], "stock_type": r["stock_type"],
                  "exp_date": r["exp_date"], "qty": float(r["qty"])}
                 for r in on_hand(ctx, l.material_id) if r["qty"] > 0]
        out.append({"material_id": l.material_id, "code": l.material.code,
                    "descr": l.material.descr, "batch_managed": l.material.batch_managed,
                    "ordered": float(l.qty), "delivered": float(done),
                    "outstanding": float(want), "available": avail,
                    "suggested": [{"batch": p["batch"], "stock_type": p["stock_type"],
                                   "exp_date": p["exp_date"], "qty": float(p["qty"])}
                                  for p in picks],
                    "short": float(max(D0, want - sum((p["qty"] for p in picks), D0)))})
    return {"so_no": o.doc_no, "customer": o.customer.name, "lines": out}


@router.post("/deliveries", status_code=201)
def post_delivery(body: S.DeliveryIn, ctx: Ctx = Depends(need("del"))):
    require_trading(ctx)
    o = ctx.get(M.SalesOrder, body.so_id)
    if not o:
        raise HTTPException(422, "No such sales order")
    doc_no = body.doc_no or f"DL/{ctx.tenant.id}/{len(ctx.db.execute(ctx.scope(select(M.Delivery), M.Delivery)).scalars().all()) + 1:03d}"
    if ctx.db.execute(ctx.scope(select(M.Delivery), M.Delivery)
                      .where(M.Delivery.doc_no == doc_no)).scalar_one_or_none():
        raise HTTPException(409, f"Delivery {doc_no} already exists")

    so_line = {l.material_id: l for l in o.lines}
    stock = {(r["material_id"], r["batch"], r["stock_type"]): r["qty"] for r in on_hand(ctx)}
    want = {}
    for p in body.picks:
        if p.material_id not in so_line:
            raise HTTPException(422, "A pick refers to a material that is not on the order")
        want[p.material_id] = want.get(p.material_id, D0) + Decimal(str(p.qty))
        key = (p.material_id, p.batch or "", p.stock_type)
        have = stock.get(key, D0)
        if Decimal(str(p.qty)) > have + TOL:
            m = ctx.db.get(M.Material, p.material_id)
            raise HTTPException(422,
                f"{m.code}: only {have} available in batch {p.batch or '(none)'} "
                f"as {p.stock_type.lower()} stock")
        stock[key] = have - Decimal(str(p.qty))
    for mid, q in want.items():
        l = so_line[mid]
        outstanding = Decimal(str(l.qty)) - delivered_on(ctx, o.id, mid)
        if q > outstanding + TOL:
            raise HTTPException(422,
                f"{l.material.code}: only {outstanding} remain open on the order")

    d = M.Delivery(tenant_id=ctx.tenant.id, doc_no=doc_no, doc_date=body.doc_date,
                   so_id=o.id, ship_to=body.ship_to)
    ctx.db.add(d)
    ctx.db.flush()
    issued = []
    for p in body.picks:
        m = ctx.get(M.Material, p.material_id)
        r = next((x for x in on_hand(ctx, m.id)
                  if x["batch"] == (p.batch or "") and x["stock_type"] == p.stock_type), None)
        exp = r["exp_date"] if r else None
        ctx.db.add(M.DeliveryLine(delivery_id=d.id, material_id=m.id,
                                  batch=p.batch or None, stock_type=p.stock_type,
                                  exp_date=exp, qty=p.qty))
        post_move(ctx, move_date=body.doc_date, source="GI", doc_no=doc_no,
                  material=m, stock_type=p.stock_type, qty=-Decimal(str(p.qty)),
                  batch=p.batch or None, exp=exp, so_id=o.id, party=o.customer.name)
        issued.append({"material": m.code, "batch": p.batch,
                       "stock_type": p.stock_type, "qty": float(p.qty)})
    ctx.db.commit()
    ctx.db.refresh(o)
    return {"id": d.id, "doc_no": doc_no, "issued": issued,
            "order_status": so_status(ctx, o)}


@router.get("/deliveries")
def list_del(ctx: Ctx = Depends(need("del"))):
    require_trading(ctx)
    out = []
    for d in ctx.db.execute(ctx.scope(select(M.Delivery), M.Delivery)
                            .order_by(M.Delivery.doc_date.desc())).scalars():
        for l in d.lines:
            out.append({"doc_no": d.doc_no, "doc_date": d.doc_date,
                        "so_no": d.so.doc_no, "customer": d.so.customer.name,
                        "ship_to": d.ship_to, "code": l.material.code,
                        "descr": l.material.descr, "batch": l.batch,
                        "stock_type": l.stock_type, "exp_date": l.exp_date,
                        "qty": float(l.qty)})
    return out
