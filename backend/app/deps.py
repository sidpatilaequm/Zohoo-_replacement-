"""Request context: who is calling, for which tenant, and may they.

Every business query goes through Ctx.scope(), which adds the tenant filter.
Nothing reads the tenant from the request body — it comes from the signed
token, so a client cannot ask for another organisation's rows.
"""
from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException, Request
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
    read_only: bool = False

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


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current(request: Request,
            authorization: str | None = Header(None),
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
    ro = bool(getattr(role.group, "read_only", False))
    # A screen permission grants the screen, not the verb. Without this, a group
    # given the Customers screen so it could read customers could also create
    # them. A read-only group is refused anything that is not a read.
    if ro and request.method not in SAFE_METHODS:
        raise HTTPException(403,
            f"{role.group.name} is a view-only group. It can open every screen it "
            "is given but cannot create, change or delete anything.")
    return Ctx(db=db, user=user, tenant=tenant, perms=perms, read_only=ro)


def need(perm: str):
    def _dep(ctx: Ctx = Depends(current)) -> Ctx:
        ctx.require(perm)
        return ctx
    return _dep


def need_any(*perms: str):
    """Allow the request if the group holds ANY of these.

    Some data is shared by several screens. A period list is wanted by
    Reports, Registers and GST Returns alike, and tying it to one of them
    means a group that can open a screen cannot load it.
    """
    def _dep(ctx: Ctx = Depends(current)) -> Ctx:
        if not any(p in ctx.perms for p in perms):
            raise HTTPException(403,
                "Your group does not have access to " + " or ".join(perms))
        return ctx
    return _dep


def seats_used(db, tenant_id: int) -> int:
    """A seat is a role in a company set, not a person.

    Counting roles is deliberate: someone holding a role in two organisations
    occupies a seat in each, because they can sign in to each.
    """
    from . import models as M
    from sqlalchemy import func, select as _select
    return db.execute(_select(func.count()).select_from(M.UserRole)
                      .where(M.UserRole.tenant_id == tenant_id)).scalar_one()


def check_seat(db, tenant, adding: int = 1):
    """Refuse the seat rather than allow an unlicensed sign-in."""
    used = seats_used(db, tenant.id)
    limit = tenant.user_limit or 2
    if used + adding > limit:
        raise HTTPException(409,
            f"{tenant.name} is licensed for {limit} user"
            f"{'' if limit == 1 else 's'} and {used} "
            f"{'is' if used == 1 else 'are'} already assigned. "
            "Remove someone's access first, or ask for more licences.")
    return used, limit
