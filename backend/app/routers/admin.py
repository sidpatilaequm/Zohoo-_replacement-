"""Users, groups and organisation membership, all scoped to the current tenant."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from .. import models as M, schemas as S
from ..deps import Ctx, need
from ..security import hash_password

router = APIRouter(tags=["admin"])


def _group_out(g):
    return {"id": g.id, "name": g.name, "perms": sorted(p.perm for p in g.perms)}


@router.get("/perms")
def perms():
    return M.PERMS


@router.get("/groups")
def list_groups(ctx: Ctx = Depends(need("users"))):
    rows = ctx.db.execute(select(M.Group).where(M.Group.tenant_id == ctx.tenant.id)
                          .order_by(M.Group.name)).scalars().all()
    out = []
    for g in rows:
        n = ctx.db.execute(select(M.UserRole).where(M.UserRole.group_id == g.id)).scalars().all()
        out.append({**_group_out(g), "users": len(n)})
    return out


@router.post("/groups", status_code=201)
def add_group(body: S.GroupIn, ctx: Ctx = Depends(need("users"))):
    if ctx.db.execute(select(M.Group).where(M.Group.tenant_id == ctx.tenant.id,
                                            M.Group.name == body.name)).scalar_one_or_none():
        raise HTTPException(409, "A group with that name already exists here")
    g = M.Group(tenant_id=ctx.tenant.id, name=body.name.strip())
    ctx.db.add(g)
    ctx.db.flush()
    for p in body.perms:
        ctx.db.add(M.GroupPerm(group_id=g.id, perm=p))
    ctx.db.commit()
    ctx.db.refresh(g)
    return _group_out(g)


@router.put("/groups/{gid}")
def edit_group(gid: int, body: S.GroupIn, ctx: Ctx = Depends(need("users"))):
    g = ctx.db.get(M.Group, gid)
    if not g or g.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "No such group")
    mine = ctx.db.execute(select(M.UserRole).where(
        M.UserRole.user_id == ctx.user.id,
        M.UserRole.tenant_id == ctx.tenant.id)).scalar_one_or_none()
    if mine and mine.group_id == gid and "users" not in body.perms:
        raise HTTPException(422, "That would remove your own access to user administration")
    g.name = body.name.strip()
    for p in list(g.perms):
        ctx.db.delete(p)
    ctx.db.flush()
    for p in body.perms:
        ctx.db.add(M.GroupPerm(group_id=g.id, perm=p))
    ctx.db.commit()
    ctx.db.refresh(g)
    return _group_out(g)


@router.delete("/groups/{gid}", status_code=204)
def del_group(gid: int, ctx: Ctx = Depends(need("users"))):
    g = ctx.db.get(M.Group, gid)
    if not g or g.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "No such group")
    if ctx.db.execute(select(M.UserRole).where(M.UserRole.group_id == gid)).first():
        raise HTTPException(409, "That group is in use")
    ctx.db.delete(g)
    ctx.db.commit()


@router.get("/users")
def list_users(ctx: Ctx = Depends(need("users"))):
    """Members of this organisation, plus anyone waiting to join it."""
    members = ctx.db.execute(select(M.UserRole).where(
        M.UserRole.tenant_id == ctx.tenant.id)).scalars().all()
    out = [{"id": r.user.id, "name": r.user.name, "email": r.user.email,
            "status": r.user.status, "group_id": r.group_id, "group": r.group.name,
            "perms": sorted(p.perm for p in r.group.perms), "pending": False}
           for r in members]
    waiting = ctx.db.execute(select(M.User).where(
        M.User.status == "PENDING",
        M.User.requested_tenant == ctx.tenant.id)).scalars().all()
    out += [{"id": u.id, "name": u.name, "email": u.email, "status": u.status,
             "group_id": None, "group": None, "perms": [], "pending": True} for u in waiting]
    return out


@router.post("/users", status_code=201)
def add_user(body: dict, ctx: Ctx = Depends(need("users"))):
    import re
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    gid = body.get("group_id")
    pw = body.get("password") or ""
    if not name:
        raise HTTPException(422, "Enter a name")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(422, "Enter a valid email address")
    if len(pw) < 8:
        raise HTTPException(422, "Set a password of at least 8 characters")
    g = ctx.db.get(M.Group, gid)
    if not g or g.tenant_id != ctx.tenant.id:
        raise HTTPException(422, "Choose a group in this organisation")
    u = ctx.db.execute(select(M.User).where(M.User.email == email)).scalar_one_or_none()
    if u:
        if ctx.db.execute(select(M.UserRole).where(
                M.UserRole.user_id == u.id,
                M.UserRole.tenant_id == ctx.tenant.id)).scalar_one_or_none():
            raise HTTPException(409, "That person is already a member here")
    else:
        u = M.User(name=name, email=email, pwd_hash=hash_password(pw), status="ACTIVE")
        ctx.db.add(u)
        ctx.db.flush()
    u.status = "ACTIVE"
    ctx.db.add(M.UserRole(user_id=u.id, tenant_id=ctx.tenant.id, group_id=gid))
    ctx.db.commit()
    return {"id": u.id, "name": u.name, "email": u.email}


@router.put("/users/{uid}/role")
def set_role(uid: int, body: S.UserRoleIn, ctx: Ctx = Depends(need("users"))):
    if uid == ctx.user.id and body.group_id is None:
        raise HTTPException(422, "You cannot remove your own access to this organisation")
    u = ctx.db.get(M.User, uid)
    if not u:
        raise HTTPException(404, "No such user")
    role = ctx.db.execute(select(M.UserRole).where(
        M.UserRole.user_id == uid, M.UserRole.tenant_id == ctx.tenant.id)).scalar_one_or_none()
    if body.group_id is None:
        if role:
            ctx.db.delete(role)
        ctx.db.commit()
        return {"status": "removed"}
    g = ctx.db.get(M.Group, body.group_id)
    if not g or g.tenant_id != ctx.tenant.id:
        raise HTTPException(422, "Choose a group in this organisation")
    if role:
        role.group_id = g.id
    else:
        ctx.db.add(M.UserRole(user_id=uid, tenant_id=ctx.tenant.id, group_id=g.id))
    if u.status == "PENDING":
        u.status = "ACTIVE"
        u.requested_tenant = None
    ctx.db.commit()
    return {"status": "ok", "group": g.name}


@router.delete("/users/{uid}/pending", status_code=204)
def reject_pending(uid: int, ctx: Ctx = Depends(need("users"))):
    u = ctx.db.get(M.User, uid)
    if not u or u.status != "PENDING" or u.requested_tenant != ctx.tenant.id:
        raise HTTPException(404, "No such request")
    ctx.db.delete(u)
    ctx.db.commit()
