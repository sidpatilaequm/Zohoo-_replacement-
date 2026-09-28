"""Employees (v4.2).

A short master: employee ID, first name, last name and e-mail. Its purpose is
to let a bank debit for salary or a reimbursed expense be attached to the
person it was paid to, on the Bank Statements screen.

Reading the list is allowed to the Bank Statements screen as well, because
that screen needs it for the picker; changing it needs the Employees screen.
"""
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func
from .. import models as M
from ..deps import Ctx, need, need_any
from ..schemas import EMAIL

router = APIRouter(tags=["employees"])


class EmployeeIn(BaseModel):
    emp_code: str = Field(min_length=1, max_length=20)
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    email: str = Field(min_length=3, max_length=160)
    active: bool = True

    @field_validator("emp_code", "first_name", "last_name", "email")
    @classmethod
    def _strip(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("This field cannot be blank")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        if not re.match(EMAIL, v):
            raise ValueError(f"{v} is not a valid email address")
        return v.lower()


def _out(e: M.Employee, links: int = 0):
    return {"id": e.id, "emp_code": e.emp_code, "first_name": e.first_name,
            "last_name": e.last_name, "name": f"{e.first_name} {e.last_name}",
            "email": e.email, "active": bool(e.active), "links": links}


def _link_counts(ctx):
    rows = ctx.db.execute(
        select(M.StmtTxnLink.employee_id, func.count())
        .where(M.StmtTxnLink.tenant_id == ctx.tenant.id,
               M.StmtTxnLink.employee_id.is_not(None))
        .group_by(M.StmtTxnLink.employee_id)).all()
    return {eid: n for eid, n in rows}


def _clash(ctx, body: EmployeeIn, skip_id=None):
    for col, val, what in ((M.Employee.emp_code, body.emp_code, "employee ID"),
                           (M.Employee.email, body.email, "email address")):
        q = ctx.scope(select(M.Employee), M.Employee).where(col == val)
        if skip_id:
            q = q.where(M.Employee.id != skip_id)
        if ctx.db.execute(q).scalars().first():
            raise HTTPException(409, f"Another employee already has the {what} {val}")


@router.get("/employees")
def list_employees(ctx: Ctx = Depends(need_any("employees", "bankstmt"))):
    counts = _link_counts(ctx)
    rows = ctx.db.execute(ctx.scope(select(M.Employee), M.Employee)
                          .order_by(M.Employee.emp_code)).scalars().all()
    return [_out(e, counts.get(e.id, 0)) for e in rows]


@router.post("/employees", status_code=201)
def add_employee(body: EmployeeIn, ctx: Ctx = Depends(need("employees"))):
    _clash(ctx, body)
    e = M.Employee(tenant_id=ctx.tenant.id, emp_code=body.emp_code,
                   first_name=body.first_name, last_name=body.last_name,
                   email=body.email, active=body.active)
    ctx.db.add(e)
    ctx.db.commit()
    return _out(e)


@router.put("/employees/{eid}")
def edit_employee(eid: int, body: EmployeeIn, ctx: Ctx = Depends(need("employees"))):
    e = ctx.get(M.Employee, eid)
    if not e:
        raise HTTPException(404, "No such employee")
    _clash(ctx, body, skip_id=eid)
    e.emp_code, e.first_name, e.last_name = body.emp_code, body.first_name, body.last_name
    e.email, e.active = body.email, body.active
    ctx.db.commit()
    return _out(e, _link_counts(ctx).get(e.id, 0))


@router.delete("/employees/{eid}", status_code=204)
def del_employee(eid: int, ctx: Ctx = Depends(need("employees"))):
    e = ctx.get(M.Employee, eid)
    if not e:
        raise HTTPException(404, "No such employee")
    n = _link_counts(ctx).get(e.id, 0)
    if n:
        raise HTTPException(409, f"{e.first_name} {e.last_name} has {n} bank transaction(s) "
                            "attached. Mark the employee inactive instead, so the history stays.")
    ctx.db.delete(e)
    ctx.db.commit()
