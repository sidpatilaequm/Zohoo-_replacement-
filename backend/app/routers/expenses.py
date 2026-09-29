"""Expense heads (v4.3): Expense ID and Expense name.

Employee expenses paid from the bank are booked to a head, and the active
heads are the categories offered for company spends on director cards.
Reading the list is open to the two statement screens because they need it
for their pickers; changing it needs the Expenses screen.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, update
from .. import models as M
from ..deps import Ctx, need, need_any

router = APIRouter(tags=["expenses"])


class ExpenseIn(BaseModel):
    exp_code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=80)
    active: bool = True

    @field_validator("exp_code", "name")
    @classmethod
    def _strip(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("This field cannot be blank")
        return v


def _usage(ctx, head):
    links = ctx.db.execute(select(func.count()).select_from(M.StmtTxnLink).where(
        M.StmtTxnLink.tenant_id == ctx.tenant.id,
        M.StmtTxnLink.expense_id == head.id)).scalar()
    cards = ctx.db.execute(select(func.count()).select_from(M.StmtTxn).where(
        M.StmtTxn.tenant_id == ctx.tenant.id, M.StmtTxn.allocation == "COMPANY",
        M.StmtTxn.category == head.name)).scalar()
    return links, cards


def _out(ctx, h):
    links, cards = _usage(ctx, h)
    return {"id": h.id, "exp_code": h.exp_code, "name": h.name, "active": bool(h.active),
            "employee_entries": links, "card_entries": cards}


def _clash(ctx, body, skip_id=None):
    for col, val, what in ((M.ExpenseHead.exp_code, body.exp_code, "Expense ID"),
                           (M.ExpenseHead.name, body.name, "name")):
        q = ctx.scope(select(M.ExpenseHead), M.ExpenseHead).where(col == val)
        if skip_id:
            q = q.where(M.ExpenseHead.id != skip_id)
        if ctx.db.execute(q).scalars().first():
            raise HTTPException(409, f"Another expense head already has the {what} {val}")


def active_heads(ctx):
    return ctx.db.execute(ctx.scope(select(M.ExpenseHead), M.ExpenseHead)
                          .where(M.ExpenseHead.active.is_(True))
                          .order_by(M.ExpenseHead.exp_code)).scalars().all()


@router.get("/expense-heads")
def list_heads(ctx: Ctx = Depends(need_any("expenses", "bankstmt", "cardstmt"))):
    rows = ctx.db.execute(ctx.scope(select(M.ExpenseHead), M.ExpenseHead)
                          .order_by(M.ExpenseHead.exp_code)).scalars().all()
    return [_out(ctx, h) for h in rows]


@router.post("/expense-heads", status_code=201)
def add_head(body: ExpenseIn, ctx: Ctx = Depends(need("expenses"))):
    _clash(ctx, body)
    h = M.ExpenseHead(tenant_id=ctx.tenant.id, exp_code=body.exp_code,
                      name=body.name, active=body.active)
    ctx.db.add(h)
    ctx.db.commit()
    return _out(ctx, h)


@router.post("/expense-heads/standard")
def add_standard(ctx: Ctx = Depends(need("expenses"))):
    """Add the usual heads (Travel, Fuel, Meals ...) that are not there yet,
    numbered after the highest EXPnnn already in use."""
    from .statements import CARD_CATEGORIES
    have = ctx.db.execute(ctx.scope(select(M.ExpenseHead), M.ExpenseHead)).scalars().all()
    names = {h.name.lower() for h in have}
    codes = {h.exp_code for h in have}
    n, added = 1, 0
    for name in CARD_CATEGORIES:
        if name.lower() in names:
            continue
        while f"EXP{n:03d}" in codes:
            n += 1
        code = f"EXP{n:03d}"
        codes.add(code)
        ctx.db.add(M.ExpenseHead(tenant_id=ctx.tenant.id, exp_code=code, name=name))
        added += 1
    ctx.db.commit()
    return {"added": added}


@router.put("/expense-heads/{hid}")
def edit_head(hid: int, body: ExpenseIn, ctx: Ctx = Depends(need("expenses"))):
    h = ctx.get(M.ExpenseHead, hid)
    if not h:
        raise HTTPException(404, "No such expense head")
    _clash(ctx, body, skip_id=hid)
    if body.name != h.name:
        # Card spends carry the head's name; keep them with the head.
        ctx.db.execute(update(M.StmtTxn).where(
            M.StmtTxn.tenant_id == ctx.tenant.id, M.StmtTxn.category == h.name)
            .values(category=body.name))
    h.exp_code, h.name, h.active = body.exp_code, body.name, body.active
    ctx.db.commit()
    return _out(ctx, h)


@router.delete("/expense-heads/{hid}", status_code=204)
def del_head(hid: int, ctx: Ctx = Depends(need("expenses"))):
    h = ctx.get(M.ExpenseHead, hid)
    if not h:
        raise HTTPException(404, "No such expense head")
    links, cards = _usage(ctx, h)
    if links or cards:
        raise HTTPException(409, f"{h.name} is used by {links + cards} transaction(s). "
                            "Mark it inactive instead, so the history stays.")
    ctx.db.delete(h)
    ctx.db.commit()
