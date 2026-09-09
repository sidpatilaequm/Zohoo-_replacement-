from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import models as M, schemas as S
from ..db import get_db
from ..deps import Ctx, current
from ..security import hash_password, verify_password, make_token

router = APIRouter(prefix="/auth", tags=["auth"])

DEFAULT_GROUPS = {
    "Administrator": M.PERMS,
    "Accounts": ["invoice","saved","po","vinv","so","del","grn","disc","phys","stock",
                 "crec","vpay","reports","registers","gstr","customers","vendors",
                 "materials","attrs","hsn","data"],
    "Sales": ["invoice","saved","so","del","customers","materials","stock","reports"],
    "Read only": ["saved","stock","reports","registers","gstr"],
}


DESIGNATIONS = ["Proprietor","Director","Partner","Chief Executive Officer",
    "Chief Financial Officer","General Manager","Accounts Manager","Accounts Executive",
    "Purchase Manager","Sales Manager","Store Keeper","Logistics Coordinator",
    "Quality Manager","Other"]
BANKS = [("State Bank of India","SBI"),("HDFC Bank","HDFC"),("ICICI Bank","ICICI"),
    ("Axis Bank","AXIS"),("Kotak Mahindra Bank","KOTAK"),("Punjab National Bank","PNB"),
    ("Bank of Baroda","BOB"),("Canara Bank","CANARA"),("Union Bank of India","UBI"),
    ("IndusInd Bank","INDUS"),("IDFC First Bank","IDFC"),("Yes Bank","YES"),
    ("Bank of India","BOI"),("Indian Bank","INDIAN"),("Central Bank of India","CBI"),
    ("Federal Bank","FED"),("South Indian Bank","SIB"),("Karnataka Bank","KARB"),
    ("RBL Bank","RBL"),("Bandhan Bank","BANDHAN"),("Other","OTHER")]


def seed_reference(db: Session) -> None:
    """Designations and banks are shared, so they are seeded once."""
    if not db.execute(select(M.Designation)).first():
        db.add_all([M.Designation(name=n) for n in DESIGNATIONS])
    if not db.execute(select(M.Bank)).first():
        db.add_all([M.Bank(name=n, short_code=c) for n, c in BANKS])
    db.flush()


def seed_groups(db: Session, tenant_id: int) -> dict[str, M.Group]:
    made = {}
    for name, perms in DEFAULT_GROUPS.items():
        g = M.Group(tenant_id=tenant_id, name=name)
        db.add(g)
        db.flush()
        for p in perms:
            db.add(M.GroupPerm(group_id=g.id, perm=p))
        made[name] = g
    return made


@router.get("/tenants")
def open_tenants(db: Session = Depends(get_db)):
    """Organisations a new user may ask to join. Names only — nothing else is public."""
    return [{"id": t.id, "name": t.name}
            for t in db.execute(select(M.Tenant).order_by(M.Tenant.name)).scalars()]


@router.post("/signup", status_code=201)
def signup(body: S.SignUp, db: Session = Depends(get_db)):
    if db.execute(select(M.User).where(
            M.User.email == body.email.lower())).scalar_one_or_none():
        raise HTTPException(409, "That email already has an account")
    u = M.User(name=body.name.strip(), email=body.email.lower(),
               pwd_hash=hash_password(body.password))
    if body.mode == "new":
        if body.org_gstin and db.execute(select(M.Tenant).where(
                M.Tenant.gstin == body.org_gstin)).scalar_one_or_none():
            raise HTTPException(409, "That GSTIN is already registered here")
        seed_reference(db)
        state_code = body.org_gstin[:2] if body.org_gstin else body.org_state

        t = M.Tenant(
            name=body.org_name.strip(),
            gstin=body.org_gstin or None,
            pan=(body.org_gstin[2:12] if body.org_gstin else None),
            state_code=state_code,
            inv_prefix="INV/",
            po_prefix="PO/"
        )
        db.add(t)
        db.flush()
        groups = seed_groups(db, t.id)
        u.status = "ACTIVE"
        db.add(u)
        db.flush()
        db.add(M.UserRole(user_id=u.id, tenant_id=t.id, group_id=groups["Administrator"].id))
        db.commit()
        return {"status": "active", "message": f"{t.name} created. You are its administrator.",
                "token": make_token(u.id, t.id), "tenant_id": t.id}
    if not db.get(M.Tenant, body.join_tenant_id):
        raise HTTPException(422, "No such organisation")
    u.status = "PENDING"
    u.requested_tenant = body.join_tenant_id
    db.add(u)
    db.commit()
    return {"status": "pending",
            "message": "Account created. An administrator of that organisation must approve it."}


@router.post("/signin")
def signin(body: S.SignIn, db: Session = Depends(get_db)):
    u = db.execute(select(M.User).where(
        M.User.email == body.email.lower())).scalar_one_or_none()
    if not u or not verify_password(body.password, u.pwd_hash):
        raise HTTPException(401, "Email or password is wrong")
    if u.status == "PENDING":
        raise HTTPException(403, "That account is waiting for an administrator to approve it")
    if u.status != "ACTIVE":
        raise HTTPException(403, "That account is disabled")
    roles = u.roles
    if not roles:
        raise HTTPException(403, "You have not been given access to any organisation")
    first = roles[0]
    return {"token": make_token(u.id, first.tenant_id),
            "user": {"id": u.id, "name": u.name, "email": u.email},
            "tenants": [{"id": r.tenant_id, "name": r.tenant.name,
                         "group": r.group.name,
                         "perms": sorted(p.perm for p in r.group.perms)} for r in roles],
            "tenant_id": first.tenant_id}


@router.get("/me")
def me(ctx: Ctx = Depends(current)):
    t = ctx.tenant
    return {"user": {"id": ctx.user.id, "name": ctx.user.name, "email": ctx.user.email},
            "tenant": {"id": t.id, "name": t.name, "gstin": t.gstin, "logo": t.logo,
                       "state_code": t.state_code, "company_type": t.company_type},
            "perms": sorted(ctx.perms),
            "tenants": [{"id": r.tenant_id, "name": r.tenant.name, "group": r.group.name,
                         "perms": sorted(p.perm for p in r.group.perms)} for r in ctx.user.roles]}
