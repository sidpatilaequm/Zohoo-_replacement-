from unittest.mock import patch

from app import models as M
from app.db import SessionLocal


def _create_user_with_access(email="user@aequm.in"):
    db = SessionLocal()

    tenant = M.Tenant(
        name="Test Organisation",
        state_code="29",
    )
    db.add(tenant)
    db.flush()

    user = M.User(
        name="Test User",
        email=email.lower(),
        pwd_hash="dummy",
        status="ACTIVE",
    )
    db.add(user)
    db.flush()

    group = M.Group(
    tenant_id=tenant.id,
    name="Administrators",
    )
    db.add(group)

    read_only = M.Group(
        tenant_id=tenant.id,
        name="Read only",
    )
    db.add(read_only)

    db.flush()

    role = M.UserRole(
        user_id=user.id,
        tenant_id=tenant.id,
        group_id=group.id,
    )
    db.add(role)

    db.commit()

    user_id = user.id
    db.close()

    return user_id


def _test_handoff(db, user, tenant_id):
    import hashlib
    import secrets
    from datetime import datetime, timedelta, timezone

    raw = secrets.token_urlsafe(48)

    db.add(
        M.AuthHandoff(
            id=9999,
            code_hash=hashlib.sha256(
                raw.encode("utf-8")
            ).hexdigest(),
            user_id=user.id,
            tenant_id=tenant_id,
            expires_at=(
                datetime.now(timezone.utc).replace(tzinfo=None)
                + timedelta(minutes=2)
            ),
        )
    )

    db.commit()

    return raw


def _callback(api, claims):
    with patch(
        "app.microsoft_auth.verify_flow",
        return_value={"dummy": "flow"},
    ), patch(
        "app.microsoft_auth.finish_flow",
        return_value={"id_token_claims": claims},
    ), patch(
        "app.microsoft_auth.TENANT_ID",
        "test-tenant",
    ), patch(
        "app.routers.auth._create_microsoft_handoff",
        side_effect=_test_handoff,
    ):
        return api.get(
            "/api/auth/microsoft/callback",
            cookies={"aequm_ms_flow": "valid-flow"},
            follow_redirects=False,
        )


def test_first_microsoft_login_links_existing_user(api):
    user_id = _create_user_with_access(
        "user@aequm.in"
    )

    response = _callback(
        api,
        {
            "tid": "test-tenant",
            "oid": "microsoft-object-123",
            "preferred_username": "user@aequm.in",
        },
    )

    assert response.status_code == 302
    assert "/auth?microsoft_code=" in response.headers["location"]

    db = SessionLocal()
    user = db.get(M.User, user_id)

    assert user.entra_tenant_id == "test-tenant"
    assert user.entra_object_id == "microsoft-object-123"

    db.close()


def test_unknown_microsoft_user_is_provisioned(api):
    # Create an organisation so the new Microsoft user has somewhere to belong.
    existing_user_id = _create_user_with_access(
        "existing@aequm.in"
    )

    db = SessionLocal()
    existing_user = db.get(M.User, existing_user_id)
    tenant_id = existing_user.roles[0].tenant_id
    db.close()

    response = _callback(
        api,
        {
            "tid": "test-tenant",
            "oid": "microsoft-object-999",
            "preferred_username": "unknown@aequm.in",
            "name": "Unknown Microsoft User",
        },
    )

    assert response.status_code == 302
    assert "/auth?microsoft_code=" in response.headers["location"]

    db = SessionLocal()

    user = (
        db.query(M.User)
        .filter(M.User.email == "unknown@aequm.in")
        .one()
    )

    assert user.name == "Unknown Microsoft User"
    assert user.status == "ACTIVE"
    assert user.entra_tenant_id == "test-tenant"
    assert user.entra_object_id == "microsoft-object-999"

    roles = list(user.roles)
    assert len(roles) == 1
    assert roles[0].tenant_id == tenant_id
    assert roles[0].group.name == "Read only"

    db.close()


def test_wrong_microsoft_tenant_is_rejected(api):
    _create_user_with_access(
        "user@aequm.in"
    )

    response = _callback(
        api,
        {
            "tid": "wrong-tenant",
            "oid": "microsoft-object-456",
            "preferred_username": "user@aequm.in",
        },
    )

    assert response.status_code == 403
    assert "unauthorized tenant" in response.json()["detail"].lower()


def test_existing_linked_microsoft_user_can_sign_in(api):
    user_id = _create_user_with_access(
        "user@aequm.in"
    )

    db = SessionLocal()
    user = db.get(M.User, user_id)

    user.entra_tenant_id = "test-tenant"
    user.entra_object_id = "microsoft-object-existing"

    db.commit()
    db.close()

    response = _callback(
        api,
        {
            "tid": "test-tenant",
            "oid": "microsoft-object-existing",
            "preferred_username": "user@aequm.in",
        },
    )

    assert response.status_code == 302
    assert "/auth?microsoft_code=" in response.headers["location"]
