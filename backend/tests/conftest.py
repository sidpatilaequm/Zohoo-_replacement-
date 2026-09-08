import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api():
    from app.db import engine, SessionLocal
    from app import models as M
    from app.main import app
    M.Base.metadata.drop_all(engine)
    M.Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add_all([M.State(code=c, name=n) for c, n in
                [("29", "Karnataka"), ("33", "Tamil Nadu"), ("27", "Maharashtra")]])
    db.add_all([M.Uom(code=c, name=c) for c in ["NOS", "LIC", "HRS", "BOX", "USR"]])
    db.commit(); db.close()
    with TestClient(app) as c:
        yield c


class Client:
    """Wraps TestClient with a bearer token and tenant header."""
    def __init__(self, api, token, tenant_id):
        self.api, self.token, self.tid = api, token, tenant_id

    def _h(self):
        return {"Authorization": f"Bearer {self.token}", "X-Tenant-Id": str(self.tid)}

    def get(self, p, **kw):    return self.api.get(p, headers=self._h(), **kw)
    def post(self, p, **kw):   return self.api.post(p, headers=self._h(), **kw)
    def put(self, p, **kw):    return self.api.put(p, headers=self._h(), **kw)
    def delete(self, p, **kw): return self.api.delete(p, headers=self._h(), **kw)


@pytest.fixture
def org(api):
    """A fresh organisation with an administrator signed in."""
    def _make(name="Aequm India", email="admin@aequm.in", gstin=None, state="29"):
        r = api.post("/api/auth/signup", json={
            "name": "Admin", "email": email, "password": "correct horse",
            "mode": "new", "org_name": name, "org_gstin": gstin, "org_state": state})
        assert r.status_code == 201, r.text
        d = r.json()
        return Client(api, d["token"], d["tenant_id"])
    return _make


@pytest.fixture
def seed_ref():
    """Seed the shared designation and bank masters, and hand back their ids."""
    def _seed(client):
        from app.db import SessionLocal
        from app import models as M
        db = SessionLocal()
        if not db.query(M.Designation).first():
            db.add_all([M.Designation(name=n) for n in
                        ["Director", "Accounts Manager", "Purchase Manager"]])
        if not db.query(M.Bank).first():
            db.add_all([M.Bank(name="HDFC Bank", short_code="HDFC"),
                        M.Bank(name="State Bank of India", short_code="SBIN")])
        db.commit()
        d = db.query(M.Designation).filter_by(name="Director").one().id
        b = db.query(M.Bank).filter_by(name="HDFC Bank").one().id
        db.close()
        return {"designation": d, "bank": b}
    return _seed
