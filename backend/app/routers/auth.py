from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import smtplib
from email.message import EmailMessage

from .. import models as M, schemas as S
from ..db import get_db
from ..deps import Ctx, current, seats_used
from ..security import hash_password, verify_password, make_token

router = APIRouter(prefix="/auth", tags=["auth"])

DEFAULT_GROUPS = {
    "Administrator": M.PERMS,
    "Accounts": ["invoice","saved","po","vinv","so","del","grn","disc","phys","stock",
                 "crec","vpay","reports","registers","gstr","customers","vendors",
                 "materials","attrs","hsn","data"],
    "Sales": ["invoice","saved","so","del","customers","materials","stock","reports"],
    # The auditor sees everything and changes nothing. Every permission here is
    # a read-only screen; none of them can raise, alter or post a document.
    "Auditor": ["saved","po","vinv","stock","crec","vpay","reports","registers",
                "gstr","audit","customers","vendors","materials","hsn"],
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
        g = M.Group(tenant_id=tenant_id, name=name,
                    read_only=name in ("Auditor", "Read only"))
        db.add(g)
        db.flush()
        for p in perms:
            db.add(M.GroupPerm(group_id=g.id, perm=p))
        made[name] = g
    return made

RESET_TOKEN_MINUTES = 30


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _send_reset_email(user: M.User, tenant: M.Tenant, token: str) -> None:
    if not tenant.smtp_host or not tenant.smtp_port or not tenant.smtp_from_email:
        raise RuntimeError("SMTP is not configured for this organisation")

    reset_url = (
        "https://billing.nexdaequmsupport.com/"
        f"reset-password?token={token}"
    )

    msg = EmailMessage()
    msg["Subject"] = "Reset your Aequm Billing password"
    msg["From"] = (
        f"{tenant.smtp_from_name} <{tenant.smtp_from_email}>"
        if tenant.smtp_from_name
        else tenant.smtp_from_email
    )
    msg["To"] = user.email

    if tenant.smtp_reply_to:
        msg["Reply-To"] = tenant.smtp_reply_to

    if tenant.smtp_bcc:
        msg["Bcc"] = tenant.smtp_bcc

    msg.set_content(
        f"""Hello {user.name},

We received a request to reset your Aequm Billing password.

Use the link below to choose a new password:

{reset_url}

This link expires in {RESET_TOKEN_MINUTES} minutes and can only be used once.

If you did not request a password reset, you can safely ignore this email.

Regards,
Aequm Billing
"""
    )

    encryption = tenant.smtp_encryption or "STARTTLS"

    if encryption == "SSL":
        smtp = smtplib.SMTP_SSL(
            tenant.smtp_host,
            tenant.smtp_port,
            timeout=20,
        )
    else:
        smtp = smtplib.SMTP(
            tenant.smtp_host,
            tenant.smtp_port,
            timeout=20,
        )

    try:
        if encryption == "STARTTLS":
            smtp.starttls()

        if tenant.smtp_username:
            smtp.login(
                tenant.smtp_username,
                tenant.smtp_password or "",
            )

        smtp.send_message(msg)
    finally:
        smtp.quit()

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
        t = M.Tenant(name=body.org_name.strip(), gstin=body.org_gstin or None,
                     pan=(body.org_gstin[2:12] if body.org_gstin else None),
                     state_code=body.org_state, inv_prefix="INV/", po_prefix="PO/")
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

@router.post("/forgot-password")
def forgot_password(body: S.ForgotPasswordIn, db: Session = Depends(get_db)):
    """
    Always return the same response so the endpoint does not reveal
    whether an email address belongs to an account.
    """
    generic = {
        "message": "If an account exists for that email, a password reset link has been sent."
    }

    user = db.execute(
        select(M.User).where(M.User.email == body.email.lower())
    ).scalar_one_or_none()

    if not user or user.status != "ACTIVE":
        return generic

    # Prefer an active organisation with working SMTP configuration.
    tenant = None
    for role in user.roles:
        t = role.tenant
        if (
            t.smtp_host
            and t.smtp_port
            and t.smtp_from_email
        ):
            tenant = t
            break

    if tenant is None:
        return generic

    # Invalidate outstanding tokens for this user.
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for old in db.execute(
        select(M.PasswordResetToken).where(
            M.PasswordResetToken.user_id == user.id,
            M.PasswordResetToken.used_at.is_(None),
        )
    ).scalars():
        old.used_at = now

    raw_token = secrets.token_urlsafe(48)

    reset = M.PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_reset_token(raw_token),
        expires_at=now + timedelta(minutes=RESET_TOKEN_MINUTES),
    )

    db.add(reset)
    db.commit()

    try:
        _send_reset_email(user, tenant, raw_token)
    except Exception:
        # Do not expose SMTP details to the caller.
        db.delete(reset)
        db.commit()
        return generic

    return generic


@router.post("/reset-password")
def reset_password(body: S.ResetPasswordIn, db: Session = Depends(get_db)):
    token_hash = _hash_reset_token(body.token)

    reset = db.execute(
        select(M.PasswordResetToken).where(
            M.PasswordResetToken.token_hash == token_hash
        )
    ).scalar_one_or_none()

    if not reset:
        raise HTTPException(400, "This password reset link is invalid or has expired")

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if reset.used_at is not None or reset.expires_at <= now:
        raise HTTPException(400, "This password reset link is invalid or has expired")

    user = db.get(M.User, reset.user_id)

    if not user or user.status != "ACTIVE":
        raise HTTPException(400, "This password reset link is invalid or has expired")

    user.pwd_hash = hash_password(body.password)
    reset.used_at = now

    db.commit()

    return {"message": "Your password has been reset. You can now sign in."}

@router.get("/me")
def me(ctx: Ctx = Depends(current)):
    t = ctx.tenant
    return {"user": {"id": ctx.user.id, "name": ctx.user.name, "email": ctx.user.email},
            "tenant": {"id": t.id, "name": t.name, "gstin": t.gstin, "logo": t.logo,
                       "state_code": t.state_code, "company_type": t.company_type},
            "perms": sorted(ctx.perms),
            "licence": {"limit": t.user_limit or 2,
                        "used": seats_used(ctx.db, t.id)},
            "tenants": [{"id": r.tenant_id, "name": r.tenant.name, "group": r.group.name,
                         "perms": sorted(p.perm for p in r.group.perms)} for r in ctx.user.roles]}
