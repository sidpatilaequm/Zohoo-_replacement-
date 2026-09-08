"""Attributes, goods receipt, discrepancy, physical count, stock and ordering."""
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from .. import models as M, schemas as S
from ..deps import Ctx, current, need
from ..service import build_lines
from ..inventory import (D0, TOL, expiry_from, require_trading, on_hand, post_move,
                         invoiceable, delivered_on, so_status, suggest_picks, pick_order)

router = APIRouter(tags=["inventory"])


# ============================================================ attributes
def _attr_out(a):
    return {"id": a.id, "code": a.code, "name": a.name, "attr_type": a.attr_type,
            "values": [v.value for v in a.values]}


@router.get("/attributes")
def list_attributes(ctx: Ctx = Depends(current)):
    rows = ctx.db.execute(select(M.Attribute).order_by(M.Attribute.code)).scalars().all()
    out = []
    for a in rows:
        used = ctx.db.execute(select(func.count()).select_from(M.MaterialAttribute)
                              .where(M.MaterialAttribute.attribute_id == a.id)).scalar_one()
        out.append({**_attr_out(a), "used_on": used})
    return out


@router.post("/attributes", status_code=201)
def add_attribute(body: S.AttributeIn, ctx: Ctx = Depends(need("attrs"))):
    code = body.code.strip().upper()
    if ctx.db.execute(select(M.Attribute).where(M.Attribute.code == code)).scalar_one_or_none():
        raise HTTPException(409, f"Attribute code {code} already exists")
    a = M.Attribute(code=code, name=body.name.strip(), attr_type=body.attr_type)
    ctx.db.add(a)
    ctx.db.flush()
    for v in dict.fromkeys(body.values):
        ctx.db.add(M.AttributeValue(attribute_id=a.id, value=v))
    ctx.db.commit()
    ctx.db.refresh(a)
    return _attr_out(a)


@router.put("/attributes/{aid}")
def edit_attribute(aid: int, body: S.AttributeIn, ctx: Ctx = Depends(need("attrs"))):
    a = ctx.db.get(M.Attribute, aid)
    if not a:
        raise HTTPException(404, "No such attribute")
    a.code, a.name, a.attr_type = body.code.strip().upper(), body.name.strip(), body.attr_type
    for v in list(a.values):
        ctx.db.delete(v)
    ctx.db.flush()
    for v in dict.fromkeys(body.values):
        ctx.db.add(M.AttributeValue(attribute_id=a.id, value=v))
    ctx.db.commit()
    ctx.db.refresh(a)
    return _attr_out(a)


@router.delete("/attributes/{aid}", status_code=204)
def del_attribute(aid: int, ctx: Ctx = Depends(need("attrs"))):
    a = ctx.db.get(M.Attribute, aid)
    if not a:
        raise HTTPException(404, "No such attribute")
    used = ctx.db.execute(select(func.count()).select_from(M.MaterialAttribute)
                          .where(M.MaterialAttribute.attribute_id == aid)).scalar_one()
    if used:
        raise HTTPException(409, f"That attribute is set on {used} material(s)")
    ctx.db.delete(a)
    ctx.db.commit()


# ========================================================= goods receipt
@router.get("/grn/open-pos")
def open_pos(ctx: Ctx = Depends(need("grn"))):
    require_trading(ctx)
    out = []
    for po in ctx.db.execute(ctx.scope(select(M.PurchaseOrder), M.PurchaseOrder)).scalars():
        lines = []
        for l in po.lines:
            got = ctx.db.execute(select(func.coalesce(func.sum(M.StockLedger.qty), 0)).where(
                M.StockLedger.tenant_id == ctx.tenant.id, M.StockLedger.po_id == po.id,
                M.StockLedger.material_id == l.material_id,
                M.StockLedger.source == "GRN")).scalar_one()
            open_qty = Decimal(str(l.qty)) - Decimal(str(got))
            if open_qty > TOL:
                lines.append({"material_id": l.material_id, "code": l.material.code,
                              "descr": l.material.descr, "uom": l.material.uom,
                              "batch_managed": l.material.batch_managed,
                              "shelf_life_days": l.material.shelf_life_days,
                              "ordered": float(l.qty), "received": float(got),
                              "open": float(open_qty)})
        if lines:
            out.append({"id": po.id, "doc_no": po.doc_no, "doc_date": po.doc_date,
                        "vendor": po.vendor.name, "ship_addr": po.ship_addr, "lines": lines})
    return out


@router.post("/grn", status_code=201)
def post_grn(body: S.GrnIn, ctx: Ctx = Depends(need("grn"))):
    require_trading(ctx)
    po = ctx.get(M.PurchaseOrder, body.po_id)
    if not po:
        raise HTTPException(422, "No such purchase order in this organisation")
    if ctx.db.execute(ctx.scope(select(M.StockLedger), M.StockLedger)
                      .where(M.StockLedger.doc_no == body.doc_no,
                             M.StockLedger.source == "GRN")).first():
        raise HTTPException(409, f"Receipt {body.doc_no} has already been used")
    po_line = {l.material_id: l for l in po.lines}
    made = []
    touched = set()
    for i, li in enumerate(body.lines, 1):
        if li.qty <= 0:
            continue
        pl = po_line.get(li.material_id)
        if not pl:
            raise HTTPException(422, f"Line {i}: that material is not on the order")
        m = pl.material
        # everything already received for this line, plus what this receipt adds so far
        already = ctx.db.execute(select(func.coalesce(func.sum(M.StockLedger.qty), 0)).where(
            M.StockLedger.tenant_id == ctx.tenant.id, M.StockLedger.po_id == po.id,
            M.StockLedger.material_id == m.id, M.StockLedger.source == "GRN")).scalar_one()
        taken = sum((Decimal(str(x["qty"])) for x in made if x["material_id"] == m.id), D0)
        open_qty = Decimal(str(pl.qty)) - Decimal(str(already)) - taken
        if Decimal(str(li.qty)) > open_qty + TOL:
            raise HTTPException(422,
                f"Line {i}: only {open_qty} of {m.code} remain open on the order")
        if m.batch_managed and not (li.batch or "").strip():
            raise HTTPException(422,
                f"Line {i}: {m.code} is batch managed, so a batch number is required")
        exp = li.exp_date
        if m.batch_managed and m.shelf_life_days and li.mfg_date:
            exp = expiry_from(li.mfg_date, m.shelf_life_days)   # shelf life wins
        if exp and li.mfg_date and exp < li.mfg_date:
            raise HTTPException(422, f"Line {i}: expiry cannot be before the manufacturing date")
        post_move(ctx, move_date=body.doc_date, source="GRN", doc_no=body.doc_no,
                  material=m, stock_type=li.stock_type, qty=Decimal(str(li.qty)),
                  batch=(li.batch or "").strip() if m.batch_managed else None,
                  mfg=li.mfg_date if m.batch_managed else None,
                  exp=exp if m.batch_managed else None,
                  po_id=po.id, party=po.vendor.name)
        made.append({"material_id": m.id, "material": m.code, "qty": float(li.qty),
                     "stock_type": li.stock_type, "batch": li.batch, "exp_date": exp})
        touched.add(m.id)

    if not made:
        raise HTTPException(422, "Enter a received quantity on at least one line")
    ctx.db.flush()

    # One discrepancy per order line, not per receipt line: the question is
    # whether the total delivered against the order matches what was ordered.
    discrepancies = []
    for mid in touched:
        pl = po_line[mid]
        delivered = ctx.db.execute(select(func.coalesce(func.sum(M.StockLedger.qty), 0)).where(
            M.StockLedger.tenant_id == ctx.tenant.id, M.StockLedger.po_id == po.id,
            M.StockLedger.material_id == mid, M.StockLedger.source == "GRN")).scalar_one()
        delivered = Decimal(str(delivered))
        ordered = Decimal(str(pl.qty))
        existing = ctx.db.execute(ctx.scope(select(M.Discrepancy), M.Discrepancy).where(
            M.Discrepancy.po_id == po.id,
            M.Discrepancy.material_id == mid)).scalar_one_or_none()
        if abs(delivered - ordered) <= TOL:
            if existing:                       # a later receipt made it good
                ctx.db.delete(existing)
            continue
        if existing:
            existing.received_qty = delivered
            existing.grn_no, existing.grn_date = body.doc_no, body.doc_date
        else:
            existing = M.Discrepancy(tenant_id=ctx.tenant.id, grn_no=body.doc_no,
                grn_date=body.doc_date, po_id=po.id, material_id=mid,
                ordered_qty=ordered, received_qty=delivered, status="HELD")
            ctx.db.add(existing)
        discrepancies.append({"material": pl.material.code, "ordered": float(ordered),
                              "received": float(delivered),
                              "difference": float(delivered - ordered)})
    po.status = "INVOICED"
    ctx.db.commit()
    return {"doc_no": body.doc_no,
            "lines": [{k: v for k, v in x.items() if k != "material_id"} for x in made],
            "discrepancies": discrepancies,
            "note": ("Held until released — the vendor cannot invoice these lines yet."
                     if discrepancies else "Everything matched the order.")}


# =========================================================== discrepancy
@router.get("/discrepancies")
def list_disc(status: str | None = None, ctx: Ctx = Depends(need("disc"))):
    require_trading(ctx)
    q = ctx.scope(select(M.Discrepancy), M.Discrepancy).order_by(M.Discrepancy.grn_date.desc())
    if status:
        q = q.where(M.Discrepancy.status == status)
    out = []
    for d in ctx.db.execute(q).scalars():
        po = ctx.db.get(M.PurchaseOrder, d.po_id)
        diff = Decimal(str(d.received_qty)) - Decimal(str(d.ordered_qty))
        out.append({"id": d.id, "grn_no": d.grn_no, "grn_date": d.grn_date,
                    "po_no": po.doc_no if po else None, "vendor": po.vendor.name if po else None,
                    "material": d.material.code, "descr": d.material.descr,
                    "ordered": float(d.ordered_qty), "received": float(d.received_qty),
                    "difference": float(diff),
                    "kind": "Short delivery" if diff < 0 else "Over delivery",
                    "status": d.status, "released_on": d.released_on,
                    "released_by": d.released_by})
    return out


@router.post("/discrepancies/{did}/release")
def release_disc(did: int, ctx: Ctx = Depends(need("disc"))):
    d = ctx.get(M.Discrepancy, did)
    if not d:
        raise HTTPException(404, "No such discrepancy")
    d.status = "RELEASED"
    d.released_on = date.today()
    d.released_by = ctx.user.name
    ctx.db.commit()
    inv = invoiceable(ctx, d.po_id, d.material_id)
    return {"status": "RELEASED",
            "invoiceable_now": float(inv["invoiceable"]),
            "note": "The received quantity is now what the vendor may invoice, not the ordered quantity."}


@router.post("/discrepancies/{did}/hold")
def hold_disc(did: int, ctx: Ctx = Depends(need("disc"))):
    d = ctx.get(M.Discrepancy, did)
    if not d:
        raise HTTPException(404, "No such discrepancy")
    d.status, d.released_on, d.released_by = "HELD", None, None
    ctx.db.commit()
    return {"status": "HELD"}


@router.get("/discrepancies/invoiceable")
def disc_invoiceable(ctx: Ctx = Depends(need("disc"))):
    require_trading(ctx)
    seen, out = set(), []
    for r in ctx.db.execute(ctx.scope(select(M.StockLedger), M.StockLedger)
                            .where(M.StockLedger.source == "GRN")).scalars():
        key = (r.po_id, r.material_id)
        if key in seen or not r.po_id:
            continue
        seen.add(key)
        po = ctx.db.get(M.PurchaseOrder, r.po_id)
        ordered = sum((Decimal(str(l.qty)) for l in po.lines
                       if l.material_id == r.material_id), D0)
        inv = invoiceable(ctx, r.po_id, r.material_id)
        out.append({"po_no": po.doc_no, "vendor": po.vendor.name,
                    "material": r.material.code, "descr": r.material.descr,
                    "ordered": float(ordered), "delivered": float(inv["delivered"]),
                    "held": float(inv["held"]), "invoiceable": float(inv["invoiceable"])})
    return out


# ===================================================== physical inventory
@router.get("/physical/sheet")
def count_sheet(ctx: Ctx = Depends(need("phys"))):
    require_trading(ctx)
    out = []
    for r in on_hand(ctx):
        m = ctx.db.get(M.Material, r["material_id"])
        out.append({"material_id": m.id, "code": m.code, "descr": m.descr, "uom": m.uom,
                    "batch": r["batch"], "stock_type": r["stock_type"],
                    "exp_date": r["exp_date"], "book_qty": float(r["qty"])})
    return sorted(out, key=lambda x: (x["code"], x["batch"], x["stock_type"]))


@router.post("/physical", status_code=201)
def post_count(body: S.PhysIn, ctx: Ctx = Depends(need("phys"))):
    require_trading(ctx)
    if ctx.db.execute(ctx.scope(select(M.PhysicalCount), M.PhysicalCount)
                      .where(M.PhysicalCount.doc_no == body.doc_no)).first():
        raise HTTPException(409, f"Count document {body.doc_no} has already been used")
    book = {(r["material_id"], r["batch"], r["stock_type"]): r for r in on_hand(ctx)}
    posted = []
    for li in body.lines:
        key = (li.material_id, li.batch or "", li.stock_type)
        cur = book.get(key)
        if cur is None:
            raise HTTPException(422,
                "That material, batch and stock type combination holds no stock")
        diff = Decimal(str(li.counted_qty)) - cur["qty"]
        if abs(diff) <= TOL:
            continue                                  # agrees, nothing to post
        m = ctx.db.get(M.Material, li.material_id)
        post_move(ctx, move_date=body.count_date, source="PI", doc_no=body.doc_no,
                  material=m, stock_type=li.stock_type, qty=diff,
                  batch=li.batch or None, exp=cur["exp_date"], party="Physical count")
        ctx.db.add(M.PhysicalCount(tenant_id=ctx.tenant.id, doc_no=body.doc_no,
            count_date=body.count_date, counted_by=body.counted_by, reason=body.reason,
            material_id=m.id, batch=li.batch or None, stock_type=li.stock_type,
            book_qty=cur["qty"], counted_qty=li.counted_qty, diff_qty=diff))
        posted.append({"material": m.code, "batch": li.batch, "stock_type": li.stock_type,
                       "book": float(cur["qty"]), "counted": float(li.counted_qty),
                       "difference": float(diff)})
    if not posted:
        raise HTTPException(422, "Nothing counted differs from the book, so there is nothing to post")
    ctx.db.commit()
    return {"doc_no": body.doc_no, "posted": posted}


@router.get("/physical")
def list_counts(ctx: Ctx = Depends(need("phys"))):
    rows = ctx.db.execute(ctx.scope(select(M.PhysicalCount), M.PhysicalCount)
                          .order_by(M.PhysicalCount.count_date.desc())).scalars()
    return [{"doc_no": p.doc_no, "count_date": p.count_date, "counted_by": p.counted_by,
             "reason": p.reason, "material": p.material.code, "descr": p.material.descr,
             "batch": p.batch, "stock_type": p.stock_type, "book": float(p.book_qty),
             "counted": float(p.counted_qty), "difference": float(p.diff_qty)} for p in rows]


# ========================================================== stock report
@router.get("/stock/summary")
def stock_summary(ctx: Ctx = Depends(need("stock"))):
    require_trading(ctx)
    rows = on_hand(ctx)
    mats = {}
    for r in rows:
        m = mats.setdefault(r["material_id"], {t: D0 for t in M.STOCK_TYPES})
        m[r["stock_type"]] += r["qty"]
    out = []
    for mid, byType in mats.items():
        m = ctx.db.get(M.Material, mid)
        inQ = ctx.db.execute(select(func.coalesce(func.sum(M.StockLedger.qty), 0)).where(
            M.StockLedger.tenant_id == ctx.tenant.id, M.StockLedger.material_id == mid,
            M.StockLedger.qty > 0)).scalar_one()
        outQ = ctx.db.execute(select(func.coalesce(func.sum(M.StockLedger.qty), 0)).where(
            M.StockLedger.tenant_id == ctx.tenant.id, M.StockLedger.material_id == mid,
            M.StockLedger.qty < 0)).scalar_one()
        owned = sum((v for k, v in byType.items() if k in M.OWNED_TYPES), D0)
        out.append({"material_id": mid, "code": m.code, "descr": m.descr, "uom": m.uom,
                    "batch_managed": m.batch_managed,
                    "received": float(inQ), "issued": float(-Decimal(str(outQ))),
                    **{t.lower(): float(byType[t]) for t in M.STOCK_TYPES},
                    "owned": float(owned)})
    return sorted(out, key=lambda x: x["code"])


@router.get("/stock/batches")
def stock_batches(ctx: Ctx = Depends(need("stock"))):
    require_trading(ctx)
    today = date.today()
    out = []
    for r in pick_order(on_hand(ctx)):
        m = ctx.db.get(M.Material, r["material_id"])
        d = (r["exp_date"] - today).days if r["exp_date"] else None
        out.append({"code": m.code, "descr": m.descr, "batch": r["batch"],
                    "stock_type": r["stock_type"], "exp_date": r["exp_date"],
                    "days_left": d, "qty": float(r["qty"]),
                    "owned": r["stock_type"] in M.OWNED_TYPES})
    return out


@router.get("/stock/movements")
def stock_movements(ctx: Ctx = Depends(need("stock"))):
    require_trading(ctx)
    rows = ctx.db.execute(ctx.scope(select(M.StockLedger), M.StockLedger)
        .order_by(M.StockLedger.move_date, M.StockLedger.id)).scalars().all()
    label = {"GRN": "Goods receipt", "GI": "Goods issue", "PI": "Count adjustment"}
    run, out = D0, []
    for r in rows:
        q = Decimal(str(r.qty))
        run += q
        ref = None
        if r.po_id:
            po = ctx.db.get(M.PurchaseOrder, r.po_id)
            ref = po.doc_no if po else None
        elif r.so_id:
            so = ctx.db.get(M.SalesOrder, r.so_id)
            ref = so.doc_no if so else None
        out.append({"move_date": r.move_date, "doc_no": r.doc_no, "source": r.source,
                    "movement": label[r.source], "reference": ref,
                    "code": r.material.code, "descr": r.material.descr,
                    "batch": r.batch, "stock_type": r.stock_type, "party": r.party,
                    "in_qty": float(q) if q > 0 else 0.0,
                    "out_qty": float(-q) if q < 0 else 0.0,
                    "balance": float(run)})
    return out
