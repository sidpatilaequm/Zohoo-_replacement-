"""Request context: who is calling, for which tenant, and may they.

Every business query goes through Ctx.scope(), which adds the tenant filter.
Nothing reads the tenant from the request body — it comes from the signed
token, so a client cannot ask for another organisation's rows.
"""
from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import models as M
from .db import get_db
from .security import read_token


@dataclass
class Ctx:
    db: Session
    user: M.User
    tenant: M.Tenant
    perms: set[str]

    def scope(self, stmt, model):
        return stmt.where(model.tenant_id == self.tenant.id)

    def get(self, model, pk):
        """Fetch by primary key, but only within this tenant."""
        obj = self.db.get(model, pk)
        if obj is None or getattr(obj, "tenant_id", None) != self.tenant.id:
            return None
        return obj

    def require(self, perm: str):
        if perm not in self.perms:
            raise HTTPException(403, f"Your group does not have access to {perm}")


def current(authorization: str | None = Header(None),
            x_tenant_id: int | None = Header(None),
            db: Session = Depends(get_db)) -> Ctx:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in first")
    payload = read_token(authorization.split(" ", 1)[1])
    if not payload:
        raise HTTPException(401, "Your session has expired. Sign in again.")
    user = db.get(M.User, payload["uid"])
    if not user or user.status != "ACTIVE":
        raise HTTPException(401, "That account is not active")
    tid = x_tenant_id or payload.get("tid")
    role = db.execute(select(M.UserRole).where(
        M.UserRole.user_id == user.id, M.UserRole.tenant_id == tid)).scalar_one_or_none()
    if not role:
        raise HTTPException(403, "You do not have access to that organisation")
    tenant = db.get(M.Tenant, tid)
    perms = {p.perm for p in role.group.perms}
    return Ctx(db=db, user=user, tenant=tenant, perms=perms)


def need(perm: str):
    def _dep(ctx: Ctx = Depends(current)) -> Ctx:
        ctx.require(perm)
        return ctx
    return _dep
