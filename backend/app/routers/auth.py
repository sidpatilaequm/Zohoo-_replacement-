from urllib import response

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import smtplib
import base64
import json
import hmac
from .. import microsoft_auth
from email.message import EmailMessage

from .. import models as M, schemas as S
from ..db import get_db
from ..deps import Ctx, current, seats_used
from ..security import hash_password, verify_password, make_token
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


MICROSOFT_FLOW_COOKIE = "aequm.microsoft.flow"

HANDOFF_MINUTES = 2

def _create_microsoft_handoff(
    db: Session,
    user: M.User,
    tenant_id: int,
) -> str:
    raw = secrets.token_urlsafe(48)
    code_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    db.add(M.AuthHandoff(
        code_hash=code_hash,
        user_id=user.id,
        tenant_id=tenant_id,
        expires_at=now + timedelta(minutes=HANDOFF_MINUTES),
    ))
    db.commit()

    return raw

def _consume_microsoft_handoff(
    db: Session,
    raw_code: str,
):
    code_hash = hashlib.sha256(raw_code.encode("utf-8")).hexdigest()

    handoff = db.execute(
        select(M.AuthHandoff).where(
            M.AuthHandoff.code_hash == code_hash
        )
    ).scalar_one_or_none()

    if not handoff:
        raise HTTPException(
            400,
            "This Microsoft sign-in code is invalid."
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if handoff.used_at is not None:
        raise HTTPException(
            400,
            "This Microsoft sign-in code has already been used."
        )

    if handoff.expires_at <= now:
        raise HTTPException(
            400,
            "This Microsoft sign-in code has expired."
        )

    handoff.used_at = now
    db.commit()

    user = db.get(M.User, handoff.user_id)

    if not user or user.status != "ACTIVE":
        raise HTTPException(
            403,
            "That Aequm account is not active."
        )

    return user, handoff.tenant_id

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/microsoft/login")
def microsoft_login():
    if not microsoft_auth.configured():
        raise HTTPException(
            503,
            "Microsoft sign-in is not configured.",
        )

    microsoft_auth.validate_redirect_uri()

    flow = microsoft_auth.start_flow()
    signed_flow = microsoft_auth.sign_flow(flow)

    response = RedirectResponse(
        url=flow["auth_uri"],
        status_code=302,
    )

    response.set_cookie(
        key="aequm_ms_flow",
        value=signed_flow,
        max_age=600,
        httponly=True,
        secure=microsoft_auth.REDIRECT_URI.startswith("https://"),
        samesite="lax",
        path="/",
    )

    return response


@router.get("/microsoft/callback")
def microsoft_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    flow_cookie = request.cookies.get("aequm_ms_flow")

    if not flow_cookie:
        raise HTTPException(
            400,
            "Microsoft sign-in session is missing or expired.",
        )

    try:
        flow = microsoft_auth.verify_flow(flow_cookie)
    except RuntimeError as exc:
        raise HTTPException(
            400,
            str(exc),
        ) from exc

    auth_response = dict(request.query_params)

    result = microsoft_auth.finish_flow(
        flow,
        auth_response,
    )

    if "error" in result:
        raise HTTPException(
            400,
            result.get(
                "error_description",
                "Microsoft sign-in failed.",
            ),
        )

    claims = result.get("id_token_claims") or {}
    entra_tenant_id = str(
        claims.get("tid") or ""
    ).strip()

    entra_object_id = str(
        claims.get("oid") or ""
    ).strip()

    microsoft_email = str(
        claims.get("preferred_username")
        or claims.get("email")
        or ""
    ).strip().lower()

    if not entra_tenant_id or not entra_object_id:
        raise HTTPException(
            400,
            "Microsoft account identity information is missing.",
        )

    configured_tenant = microsoft_auth.TENANT_ID.strip()

    if (
        not configured_tenant
        or entra_tenant_id != configured_tenant
    ):
        raise HTTPException(
            403,
            "This Microsoft account belongs to an unauthorized tenant.",
        )

    user = db.execute(
        select(M.User).where(
            M.User.entra_tenant_id == entra_tenant_id,
            M.User.entra_object_id == entra_object_id,
        )
    ).scalar_one_or_none()

    if not user:
        if not microsoft_email:
            raise HTTPException(
                403,
                "Microsoft account email information is missing.",
            )

        user = db.execute(
            select(M.User).where(
                func.lower(M.User.email) == microsoft_email.lower(),
            )
        ).scalar_one_or_none()

        if not user:
            tenant = db.execute(
                select(M.Tenant).order_by(M.Tenant.id)
            ).scalars().first()

            if not tenant:
                raise HTTPException(
                    403,
                    "No Aequm organisation is available for Microsoft sign-in.",
                )

            limit = tenant.user_limit or 5

            if seats_used(db, tenant.id) >= limit:
                raise HTTPException(
                    409,
                    "This organisation has reached its licensed user limit.",
                )

            display_name = str(
                claims.get("name") or microsoft_email.split("@")[0]
            ).strip()

            user = M.User(
                name=display_name,
                email=microsoft_email.lower(),
                pwd_hash="!",
                status="ACTIVE",
                entra_tenant_id=entra_tenant_id,
                entra_object_id=entra_object_id,
            )
            db.add(user)
            db.flush()

            read_only = db.execute(
                select(M.Group).where(
                    M.Group.tenant_id == tenant.id,
                    M.Group.name == "Read only",
                )
            ).scalar_one_or_none()

            if not read_only:
                raise HTTPException(
                    500,
                    "Default Microsoft user group is not configured.",
                )

            db.add(
                M.UserRole(
                    user_id=user.id,
                    tenant_id=tenant.id,
                    group_id=read_only.id,
                )
            )

            db.commit()
            db.refresh(user)

        else:
            if user.status != "ACTIVE":
                raise HTTPException(
                    403,
                    "That Aequm account is not active.",
                )

            user.entra_tenant_id = entra_tenant_id
            user.entra_object_id = entra_object_id
            db.commit()
            db.refresh(user)

    if user.status != "ACTIVE":
        raise HTTPException(
            403,
            "That Aequm account is not active.",
        )

    roles = list(user.roles)

    if not roles:
        raise HTTPException(
            403,
            "That Aequm account has no tenant access.",
        )

    tenant_id = roles[0].tenant_id

    code = _create_microsoft_handoff(
        db,
        user,
        tenant_id,
    )

    response = RedirectResponse(
        url=f"/auth?microsoft_code={code}",
        status_code=302,
    )

    response.delete_cookie(
        key="aequm_ms_flow",
        path="/",
    )

    return response


@router.post("/microsoft/exchange")
def microsoft_exchange(
    payload: dict,
    db: Session = Depends(get_db),
):
    code = str(
        payload.get("code") or ""
    ).strip()

    if not code:
        raise HTTPException(
            400,
            "Microsoft sign-in code is required.",
        )

    user, tenant_id = _consume_microsoft_handoff(
        db,
        code,
    )

    roles = list(user.roles)

    tenants = [
        {
            "tenant_id": role.tenant_id,
            "group_id": role.group_id,
        }
        for role in roles
    ]

    return {
        "token": make_token(
            user.id,
            tenant_id,
        ),
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
        },
        "tenants": tenants,
        "tenant_id": tenant_id,
    }


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
