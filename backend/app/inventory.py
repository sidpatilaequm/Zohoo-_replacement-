"""Stock, discrepancy and ordering rules.

Two decisions shape everything here.

**The ledger is append-only and signed.** A receipt writes a positive row, a
goods issue a negative one, a count adjustment either. Stock on hand is always
the sum of the ledger, never a stored running total, so a movement cannot be
lost by an edit going wrong.

**Consignment is not ours.** It sits on our premises but belongs to the vendor
until consumed, so it is reported separately and never raises the quantity the
material master says is available to sell.
"""
from datetime import date, timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from . import models as M

D0 = Decimal("0")
TOL = Decimal("0.0001")


def expiry_from(mfg: date | None, shelf_days: int) -> date | None:
    """Expiry is the manufacturing date plus the shelf life, nothing cleverer."""
    if not mfg or not shelf_days:
        return None
    return mfg + timedelta(days=int(shelf_days))


def require_trading(ctx):
    if ctx.tenant.company_type != "TRADING":
        raise HTTPException(409,
            "This organisation is set as non-trading, so it does not hold stock. "
            "Change the business type under Company Information first.")


def on_hand(ctx, material_id=None):
    """Balance per material, batch and stock type."""
    q = select(M.StockLedger.material_id,
               func.coalesce(M.StockLedger.batch, "").label("batch"),
               M.StockLedger.stock_type,
               func.max(M.StockLedger.exp_date).label("exp_date"),
               func.sum(M.StockLedger.qty).label("qty")
        ).where(M.StockLedger.tenant_id == ctx.tenant.id)
    if material_id:
        q = q.where(M.StockLedger.material_id == material_id)
    q = q.group_by(M.StockLedger.material_id,
                   func.coalesce(M.StockLedger.batch, ""),
                   M.StockLedger.stock_type)
    rows = []
    for r in ctx.db.execute(q):
        qty = Decimal(str(r.qty))
        if abs(qty) <= TOL:
            continue
        rows.append({"material_id": r.material_id, "batch": r.batch or "",
                     "stock_type": r.stock_type, "exp_date": r.exp_date, "qty": qty})
    return rows


def sellable(ctx, material_id) -> Decimal:
    """What can actually go out of the door: owned stock, normal type."""
    return sum((r["qty"] for r in on_hand(ctx, material_id)
                if r["stock_type"] == "NORMAL"), D0)


def pick_order(rows):
    """Earliest expiry first, so the oldest batch leaves before it dies."""
    return sorted(rows, key=lambda r: (r["exp_date"] or date(9999, 12, 31), r["batch"]))


def post_move(ctx, *, move_date, source, doc_no, material, stock_type, qty,
              batch=None, mfg=None, exp=None, po_id=None, so_id=None, party=None):
    """Write one ledger row and keep the material's sellable figure in step."""
    if qty == 0:
        return None
    row = M.StockLedger(tenant_id=ctx.tenant.id, move_date=move_date, source=source,
                        doc_no=doc_no, material_id=material.id, stock_type=stock_type,
                        batch=batch or None, mfg_date=mfg, exp_date=exp,
                        qty=qty, po_id=po_id, so_id=so_id, party=party)
    ctx.db.add(row)
    if stock_type in M.OWNED_TYPES:
        material.stock_qty = Decimal(str(material.stock_qty)) + qty
    return row


# ------------------------------------------------------------ discrepancy
def received_on(ctx, po_id, material_id) -> Decimal:
    q = select(func.coalesce(func.sum(M.StockLedger.qty), 0)).where(
        M.StockLedger.tenant_id == ctx.tenant.id,
        M.StockLedger.po_id == po_id,
        M.StockLedger.material_id == material_id,
        M.StockLedger.source == "GRN")
    return Decimal(str(ctx.db.execute(q).scalar_one()))


def held_on(ctx, po_id, material_id) -> Decimal:
    q = select(func.coalesce(func.sum(M.Discrepancy.received_qty), 0)).where(
        M.Discrepancy.tenant_id == ctx.tenant.id,
        M.Discrepancy.po_id == po_id,
        M.Discrepancy.material_id == material_id,
        M.Discrepancy.status == "HELD")
    return Decimal(str(ctx.db.execute(q).scalar_one()))


def invoiceable(ctx, po_id, material_id) -> dict:
    """What the vendor may bill: delivered, less anything still held."""
    delivered = received_on(ctx, po_id, material_id)
    held = held_on(ctx, po_id, material_id)
    return {"delivered": delivered, "held": held,
            "invoiceable": max(D0, delivered - held)}


# --------------------------------------------------------------- ordering
def delivered_on(ctx, so_id, material_id) -> Decimal:
    q = select(func.coalesce(func.sum(M.DeliveryLine.qty), 0)).join(
        M.Delivery, M.Delivery.id == M.DeliveryLine.delivery_id).where(
        M.Delivery.tenant_id == ctx.tenant.id,
        M.Delivery.so_id == so_id,
        M.DeliveryLine.material_id == material_id)
    return Decimal(str(ctx.db.execute(q).scalar_one()))


def so_status(ctx, so) -> str:
    done = all(delivered_on(ctx, so.id, l.material_id) >= Decimal(str(l.qty)) - TOL
               for l in so.lines)
    if done:
        return "DELIVERED"
    any_ = any(delivered_on(ctx, so.id, l.material_id) > TOL for l in so.lines)
    return "PARTIAL" if any_ else "OPEN"


def suggest_picks(ctx, material_id, want: Decimal):
    """Allocate from the earliest-expiring normal stock first."""
    out, need = [], Decimal(str(want))
    for r in pick_order([x for x in on_hand(ctx, material_id)
                         if x["stock_type"] == "NORMAL" and x["qty"] > 0]):
        if need <= TOL:
            break
        take = min(need, r["qty"])
        if take > TOL:
            out.append({"batch": r["batch"], "stock_type": r["stock_type"],
                        "exp_date": r["exp_date"], "qty": take})
            need -= take
    return out
