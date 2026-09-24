"""Two licensed seats per company set, and what the auditor can do with one."""


def seats(c):
    return c.get("/api/licence").json()


def make_user(c, email, group):
    gid = [g for g in c.get("/api/groups").json() if g["name"] == group][0]["id"]
    return c.post("/api/users", json={"name": email.split("@")[0], "email": email,
                                      "password": "correct horse", "group_id": gid})


def signin(c, email):
    return c.api.post("/api/auth/signin",
                      json={"email": email, "password": "correct horse"}).json()


# --------------------------------------------------------- the licence
def test_a_new_organisation_starts_with_one_seat_of_two(org):
    c = org()
    s = seats(c)
    assert s["limit"] == 2 and s["used"] == 1 and s["free"] == 1


def test_the_second_seat_can_be_filled(org):
    c = org()
    assert make_user(c, "auditor@x.co", "Auditor").status_code == 201
    assert seats(c)["used"] == 2 and seats(c)["free"] == 0


def test_the_third_user_is_refused(org):
    c = org()
    make_user(c, "auditor@x.co", "Auditor")
    r = make_user(c, "third@x.co", "Accounts")
    assert r.status_code == 409
    assert "licensed for 2" in r.text and "2 are already assigned" in r.text


def test_the_auditor_occupies_a_seat_like_anyone_else(org):
    """The point of the limit is who can sign in, not who can change things."""
    c = org()
    make_user(c, "auditor@x.co", "Auditor")
    assert seats(c)["used"] == 2
    assert "auditor counts as one" in seats(c)["note"]


def test_freeing_a_seat_lets_another_in(org):
    c = org()
    make_user(c, "auditor@x.co", "Auditor")
    assert make_user(c, "third@x.co", "Accounts").status_code == 409
    uid = [u for u in c.get("/api/users").json()
           if u["email"] == "auditor@x.co"][0]["id"]
    c.put(f"/api/users/{uid}/role", json={"user_id": uid, "group_id": None})
    assert seats(c)["used"] == 1
    assert make_user(c, "third@x.co", "Accounts").status_code == 201


def test_changing_someones_group_does_not_take_a_new_seat(org):
    c = org()
    make_user(c, "auditor@x.co", "Auditor")
    uid = [u for u in c.get("/api/users").json()
           if u["email"] == "auditor@x.co"][0]["id"]
    acc = [g for g in c.get("/api/groups").json() if g["name"] == "Accounts"][0]["id"]
    assert c.put(f"/api/users/{uid}/role",
                 json={"user_id": uid, "group_id": acc}).status_code == 200
    assert seats(c)["used"] == 2


def test_approving_a_join_request_needs_a_free_seat(api, org):
    c = org(name="Aequm", email="admin@aequm.in")
    make_user(c, "auditor@x.co", "Auditor")           # both seats now taken
    tid = c.tid
    api.post("/api/auth/signup", json={"name": "New", "email": "new@aequm.in",
        "password": "correct horse", "mode": "join", "join_tenant_id": tid})
    pend = [u for u in c.get("/api/users").json() if u["pending"]][0]
    gid = [g for g in c.get("/api/groups").json() if g["name"] == "Sales"][0]["id"]
    r = c.put(f"/api/users/{pend['id']}/role",
              json={"user_id": pend["id"], "group_id": gid})
    assert r.status_code == 409 and "licensed for 2" in r.text


# ---------------------------------------------------------- the auditor
def test_the_auditor_can_see_every_kind_of_document(org, seed_ref):
    c = org(); seed_ref(c)
    make_user(c, "auditor@x.co", "Auditor")
    tok = signin(c, "auditor@x.co")["token"]
    h = {"Authorization": f"Bearer {tok}", "X-Tenant-Id": str(c.tid)}
    for p in ("/api/invoices", "/api/purchase-orders", "/api/vendor-invoices",
              "/api/receipts", "/api/vendor-payments", "/api/registers/invoices",
              "/api/registers/gst", "/api/registers/tds", "/api/customers",
              "/api/vendors", "/api/audit/transactions", "/api/audit/reconcile"):
        assert c.api.get(p, headers=h).status_code == 200, p


def test_the_auditor_cannot_change_anything(org, seed_ref):
    c = org(); seed_ref(c)
    make_user(c, "auditor@x.co", "Auditor")
    tok = signin(c, "auditor@x.co")["token"]
    h = {"Authorization": f"Bearer {tok}", "X-Tenant-Id": str(c.tid)}
    assert c.api.post("/api/customers", headers=h, json={"code": "X", "name": "X",
        "party_type": "B2C", "bill_addr": "a", "bill_city": "b",
        "bill_state": "29"}).status_code == 403
    assert c.api.post("/api/invoices", headers=h, json={"doc_date": "2026-08-10",
        "customer_id": 1, "lines": []}).status_code == 403
    assert c.api.get("/api/users", headers=h).status_code == 403
    assert c.api.put("/api/org", headers=h, json={"name": "X",
        "state_code": "29"}).status_code == 403


def test_reconcile_is_clean_when_the_books_agree(org, seed_ref):
    c = org(); seed_ref(c)
    r = c.get("/api/audit/reconcile").json()
    assert r["clean"] is True and r["issue_count"] == 0
    assert "Nothing to look at" in r["note"]


def test_reconcile_notices_a_missing_gstr3b(org, seed_ref):
    c = org(); seed_ref(c)
    c.post("/api/hsn", json={"code": "998314", "descr": "IT", "kind": "SAC",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    m = c.post("/api/materials", json={"code": "SRV", "descr": "S", "price": 1000,
        "hsn": "998314", "uom": "NOS", "stock_qty": 99}).json()["id"]
    cu = c.post("/api/customers", json={"code": "C1", "name": "A", "party_type": "B2B",
        "bill_addr": "a", "bill_city": "b", "bill_state": "29",
        "gstins": [{"gstin": "29AAACT1234N1Z2", "is_default": True}]}).json()["id"]
    c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1000}]})
    r = c.get("/api/audit/reconcile?period=2026-08").json()
    assert any("No GSTR-3B has been uploaded" in i for i in r["gst"]["issues"])


def test_reconcile_catches_a_gstr3b_that_disagrees(org, seed_ref):
    c = org(); seed_ref(c)
    c.post("/api/hsn", json={"code": "998314", "descr": "IT", "kind": "SAC",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    m = c.post("/api/materials", json={"code": "SRV", "descr": "S", "price": 1000,
        "hsn": "998314", "uom": "NOS", "stock_qty": 99}).json()["id"]
    cu = c.post("/api/customers", json={"code": "C1", "name": "A", "party_type": "B2B",
        "bill_addr": "a", "bill_city": "b", "bill_state": "29",
        "gstins": [{"gstin": "29AAACT1234N1Z2", "is_default": True}]}).json()["id"]
    c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 100000}]})
    c.post("/api/registers/gstr3b", json={"period": "2026-08", "out_taxable": 100000,
        "out_cgst": 8000, "out_sgst": 9000, "out_igst": 0,
        "itc_igst": 0, "itc_cgst": 0, "itc_sgst": 0})
    r = c.get("/api/audit/reconcile?period=2026-08").json()
    assert r["clean"] is False
    assert any("CGST" in i and "differ" in i for i in r["gst"]["issues"])


def test_reconcile_checks_tds_against_the_vendor_master(org, seed_ref):
    c = org(); seed_ref(c)
    c.post("/api/hsn", json={"code": "998314", "descr": "IT", "kind": "SAC",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    m = c.post("/api/materials", json={"code": "SRV", "descr": "S", "price": 1000,
        "cost": 1000, "hsn": "998314", "uom": "NOS", "stock_qty": 99}).json()["id"]
    v = c.post("/api/vendors", json={"code": "V1", "name": "Redington",
        "party_type": "B2B", "addr": "a", "city": "Chennai", "state_code": "33",
        "tds_section": "194C", "tds_rate": 2,
        "gstins": [{"gstin": "33AAACR1234K1Z5", "is_default": True}]}).json()["id"]
    po = c.post("/api/purchase-orders", json={"doc_date": "2026-08-01", "vendor_id": v,
        "lines": [{"material_id": m, "qty": 100, "price": 1000}]}).json()["id"]
    vi = c.post("/api/vendor-invoices", json={"doc_no": "RED/1",
        "doc_date": "2026-08-05", "po_id": po}).json()["id"]
    # 194C at 2% on 100,000 is 2,000. Deduct 500 instead.
    c.post("/api/vendor-payments", json={"pay_type": "PAY", "vinv_id": vi,
        "pay_date": "2026-08-20", "amount": 50000, "tds": 500, "mode": "NEFT"})
    r = c.get("/api/audit/reconcile?period=2026-08").json()
    row = r["tds"]["rows"][0]
    assert row["expected_tds"] == 2000.0 and row["actual_tds"] == 500.0
    assert row["difference"] == -1500.0 and row["agrees"] is False
    assert any("No PAN on file" in f for f in row["flags"])
