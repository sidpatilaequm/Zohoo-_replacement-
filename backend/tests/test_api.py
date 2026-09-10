"""End to end through HTTP, including the tenant isolation guarantees."""


def mat(c, code="MCSP-001", price=1250, cost=975, stock=1000):
    r = c.post("/api/materials", json={"code": code, "descr": code, "price": price,
        "cost": cost, "hsn": "998314", "stock_qty": stock, "uom": "LIC",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def cust(c, code="C001", state="33", gstin="33AABCK1234M1Z8", ptype="B2B"):
    r = c.post("/api/customers", json={"code": code, "name": f"Customer {code}",
        "party_type": ptype, "bill_addr": "St", "bill_city": "City", "bill_state": state,
        "gstins": [] if ptype == "B2C" else [{"gstin": gstin, "is_default": True}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def vend(c, code="V001", state="33", gstin="33AAACR1234K1Z5", ptype="B2B"):
    r = c.post("/api/vendors", json={"code": code, "name": f"Vendor {code}",
        "party_type": ptype, "addr": "St", "city": "City", "state_code": state,
        "gstins": [] if ptype == "B2C" else [{"gstin": gstin, "is_default": True}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --------------------------------------------------------------- auth
def test_signup_creates_an_organisation_and_signs_you_in(api):
    r = api.post("/api/auth/signup", json={"name": "Alok", "email": "a@b.co",
        "password": "correct horse", "mode": "new", "org_name": "Acme", "org_state": "29"})
    assert r.status_code == 201 and r.json()["status"] == "active" and r.json()["token"]


def test_signup_rejects_a_short_password(api):
    r = api.post("/api/auth/signup", json={"name": "A", "email": "a@b.co",
        "password": "short", "mode": "new", "org_name": "Acme", "org_state": "29"})
    assert r.status_code == 422 and "at least 8" in r.text


def test_duplicate_email_is_refused(api, org):
    org(email="dup@aequm.in")
    r = api.post("/api/auth/signup", json={"name": "B", "email": "dup@aequm.in",
        "password": "correct horse", "mode": "new", "org_name": "Other", "org_state": "29"})
    assert r.status_code == 409


def test_join_request_is_pending_until_approved(api, org):
    a = org(name="Aequm", email="admin@aequm.in")
    tid = api.get("/api/auth/tenants").json()[0]["id"]
    r = api.post("/api/auth/signup", json={"name": "New", "email": "new@aequm.in",
        "password": "correct horse", "mode": "join", "join_tenant_id": tid})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert api.post("/api/auth/signin", json={"email": "new@aequm.in",
        "password": "correct horse"}).status_code == 403
    pend = [u for u in a.get("/api/users").json() if u["pending"]]
    assert len(pend) == 1
    gid = [g for g in a.get("/api/groups").json() if g["name"] == "Sales"][0]["id"]
    assert a.put(f"/api/users/{pend[0]['id']}/role", json={"user_id": pend[0]["id"],
        "group_id": gid}).status_code == 200
    assert api.post("/api/auth/signin", json={"email": "new@aequm.in",
        "password": "correct horse"}).status_code == 200


def test_wrong_password_is_refused(api, org):
    org(email="x@aequm.in")
    assert api.post("/api/auth/signin", json={"email": "x@aequm.in",
        "password": "not it"}).status_code == 401


def test_no_token_means_no_access(api):
    assert api.get("/api/customers").status_code == 401


def test_signup_seeds_four_groups(org):
    a = org()
    names = sorted(g["name"] for g in a.get("/api/groups").json())
    assert names == ["Accounts", "Administrator", "Read only", "Sales"]


# ------------------------------------------------- tenant isolation
def test_two_organisations_may_reuse_the_same_codes(org):
    a = org(name="One", email="one@x.co")
    b = org(name="Two", email="two@x.co")
    assert mat(a) and mat(b)                       # same material code, both succeed
    assert cust(a) and cust(b, gstin="33AABCK9999M1Z1")


def test_one_organisation_cannot_read_anothers_data(org):
    a = org(name="One", email="one@x.co")
    b = org(name="Two", email="two@x.co")
    mat(a, code="ONLY-IN-A")
    assert [m["code"] for m in a.get("/api/materials").json()] == ["ONLY-IN-A"]
    assert b.get("/api/materials").json() == []


def test_one_organisation_cannot_reach_anothers_row_by_id(org):
    a = org(name="One", email="one@x.co")
    b = org(name="Two", email="two@x.co")
    mid = mat(a)
    cid = cust(b, gstin="33AABCK9999M1Z1")
    # b tries to invoice using a material that belongs to a
    r = b.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cid,
        "lines": [{"material_id": mid, "qty": 1}]})
    assert r.status_code == 422 and "does not exist in this organisation" in r.text


def test_a_user_cannot_switch_to_a_tenant_they_lack(api, org):
    a = org(name="One", email="one@x.co")
    b = org(name="Two", email="two@x.co")
    other = b.tid
    r = api.get("/api/customers", headers={"Authorization": f"Bearer {a.token}",
                                           "X-Tenant-Id": str(other)})
    assert r.status_code == 403


# ------------------------------------------------------ permissions
def test_a_group_without_a_menu_is_refused_that_endpoint(api, org):
    a = org(name="One", email="admin@x.co")
    gid = [g for g in a.get("/api/groups").json() if g["name"] == "Sales"][0]["id"]
    a.post("/api/users", json={"name": "Sales", "email": "s@x.co",
        "password": "correct horse", "group_id": gid})
    tok = api.post("/api/auth/signin", json={"email": "s@x.co",
        "password": "correct horse"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}", "X-Tenant-Id": str(a.tid)}
    assert api.get("/api/customers", headers=h).status_code == 200      # Sales has it
    assert api.get("/api/users", headers=h).status_code == 403          # Sales does not
    assert api.get("/api/vendor-payments", headers=h).status_code == 403


def test_an_admin_cannot_lock_themselves_out(org):
    a = org()
    g = [x for x in a.get("/api/groups").json() if x["name"] == "Administrator"][0]
    r = a.put(f"/api/groups/{g['id']}", json={"name": "Administrator",
        "perms": ["invoice", "saved"]})
    assert r.status_code == 422 and "your own access" in r.text


# --------------------------------------------------------- invoicing
def test_intra_and_inter_state_tax(org):
    a = org(state="29")
    m = mat(a)
    c29 = cust(a, "C29", "29", "29AAACT1234N1Z2")
    c33 = cust(a, "C33", "33", "33AABCK1234M1Z8")
    i1 = a.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": c29,
        "lines": [{"material_id": m, "qty": 10}]}).json()
    i2 = a.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": c33,
        "lines": [{"material_id": m, "qty": 10}]}).json()
    assert i1["totals"]["cgst"] == 1125.0 and i1["totals"]["igst"] == 0
    assert i2["totals"]["igst"] == 2250.0 and i2["totals"]["cgst"] == 0


def test_stock_moves_on_a_tax_invoice_but_not_a_proforma(org):
    a = org(trading=True); m = mat(a, stock=100); c = cust(a)
    a.post("/api/invoices", json={"doc_date": "2026-08-10", "doc_type": "PRO",
        "customer_id": c, "lines": [{"material_id": m, "qty": 10}]})
    assert a.get("/api/materials").json()[0]["stock_qty"] == 100
    a.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": c,
        "lines": [{"material_id": m, "qty": 10}]})
    assert a.get("/api/materials").json()[0]["stock_qty"] == 90


def test_proforma_converts_and_then_moves_stock(org):
    a = org(trading=True); m = mat(a, stock=100); c = cust(a)
    iid = a.post("/api/invoices", json={"doc_date": "2026-08-10", "doc_type": "PRO",
        "customer_id": c, "lines": [{"material_id": m, "qty": 10}]}).json()["id"]
    assert a.post(f"/api/invoices/{iid}/convert").status_code == 200
    assert a.get("/api/materials").json()[0]["stock_qty"] == 90


def test_b2c_invoice_cannot_carry_a_gstin(org):
    a = org(); m = mat(a); c = cust(a, "C9", "29", ptype="B2C")
    r = a.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": c,
        "gstin": "29AAACT1234N1Z2", "lines": [{"material_id": m, "qty": 1}]})
    assert r.status_code == 422


def test_stock_cannot_go_negative(org):
    a = org(trading=True); m = mat(a, stock=5); c = cust(a)
    r = a.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": c,
        "lines": [{"material_id": m, "qty": 10}]})
    assert r.status_code == 422 and "exceeds stock" in r.text


# ------------------------------------------------ purchase and payment
def test_po_prices_at_cost_and_vendor_invoice_shows_variance(org):
    a = org(); m = mat(a, price=1250, cost=975); v = vend(a)
    po = a.post("/api/purchase-orders", json={"doc_date": "2026-08-01", "vendor_id": v,
        "lines": [{"material_id": m, "qty": 20}]}).json()
    assert po["totals"]["taxable"] == 19500.0
    r = a.post("/api/vendor-invoices", json={"doc_no": "RED/1", "doc_date": "2026-08-05",
        "po_id": po["id"], "lines": [{"material_id": m, "qty": 18, "price": 990}]})
    assert r.json()["variance"]["difference"] == -1680.0


def test_unregistered_vendor_gives_no_input_credit(org):
    a = org(); m = mat(a); v = vend(a, "V9", "29", ptype="B2C")
    po = a.post("/api/purchase-orders", json={"doc_date": "2026-08-01", "vendor_id": v,
        "lines": [{"material_id": m, "qty": 10}]}).json()
    assert po["totals"]["tax"] == 0.0


def test_receipt_cannot_exceed_the_outstanding(org):
    a = org(); m = mat(a); c = cust(a)
    inv = a.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": c,
        "lines": [{"material_id": m, "qty": 10}]}).json()
    r = a.post("/api/receipts", json={"pay_type": "REC", "pay_date": "2026-08-20",
        "invoice_id": inv["id"], "amount": inv["totals"]["rounded"] + 1, "mode": "NEFT"})
    assert r.status_code == 422 and "exceeds the outstanding" in r.text


def test_part_receipt_then_settlement(org):
    a = org(); m = mat(a); c = cust(a)
    inv = a.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": c,
        "lines": [{"material_id": m, "qty": 10}]}).json()
    tot = inv["totals"]["rounded"]
    a.post("/api/receipts", json={"pay_type": "REC", "pay_date": "2026-08-20",
        "invoice_id": inv["id"], "amount": 5000, "mode": "NEFT", "bank_ref": "UTR1"})
    assert a.get("/api/returns/reports/receivables").json()[0]["outstanding"] == tot - 5000
    a.post("/api/receipts", json={"pay_type": "REC", "pay_date": "2026-08-25",
        "invoice_id": inv["id"], "amount": tot - 5000, "mode": "NEFT"})
    assert a.get("/api/returns/reports/receivables").json() == []


def test_a_proforma_cannot_be_settled(org):
    a = org(); m = mat(a); c = cust(a)
    inv = a.post("/api/invoices", json={"doc_date": "2026-08-10", "doc_type": "PRO",
        "customer_id": c, "lines": [{"material_id": m, "qty": 10}]}).json()
    r = a.post("/api/receipts", json={"pay_type": "REC", "pay_date": "2026-08-20",
        "invoice_id": inv["id"], "amount": 100, "mode": "NEFT"})
    assert r.status_code == 422


# ------------------------------------------------------------ returns
def test_proforma_is_excluded_from_gstr1(org):
    a = org(); m = mat(a, stock=10000); c = cust(a)
    a.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": c,
        "lines": [{"material_id": m, "qty": 10}]})
    a.post("/api/invoices", json={"doc_date": "2026-08-12", "doc_type": "PRO",
        "customer_id": c, "lines": [{"material_id": m, "qty": 5}]})
    g = a.get("/api/returns/gstr1", params={"period": "2026-08"}).json()
    assert g["totals"]["taxable"] == 12500.0 and g["proforma_excluded"] == 1


def test_gstr1_and_gstr3b_reconcile(org):
    a = org(); m = mat(a); c = cust(a)
    a.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": c,
        "lines": [{"material_id": m, "qty": 10}]})
    assert a.get("/api/returns/reconciliation",
                 params={"period": "2026-08"}).json()["all_agree"] is True


def test_gstr3b_nets_credit_and_floors_at_zero(org):
    a = org(state="29"); m = mat(a, stock=10000)
    c = cust(a, "C29", "29", "29AAACT1234N1Z2")
    v = vend(a, "V29", "29", "29AAACI1234L1Z3")
    a.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": c,
        "lines": [{"material_id": m, "qty": 10}]})
    po = a.post("/api/purchase-orders", json={"doc_date": "2026-08-01", "vendor_id": v,
        "lines": [{"material_id": m, "qty": 20, "price": 975}]}).json()["id"]
    a.post("/api/vendor-invoices", json={"doc_no": "ING/1", "doc_date": "2026-08-02",
        "po_id": po})
    g = a.get("/api/returns/gstr3b", params={"period": "2026-08"}).json()
    assert g["outward"]["cgst"] == 1125.0 and g["itc"]["cgst"] == 1755.0
    assert g["net_payable"]["cgst"] == 0.0


# ------------------------------------------------------ org and smtp
def test_smtp_password_is_never_returned(org):
    a = org()
    a.put("/api/org/smtp", json={"from_email": "a@b.co", "host": "smtp.x.co",
        "port": 587, "encryption": "STARTTLS", "username": "u", "password": "secret"})
    body = a.get("/api/org").json()["smtp"]
    assert body["password_set"] is True and "password" not in body


def test_smtp_check_reports_what_is_missing(org):
    a = org()
    a.put("/api/org/smtp", json={"from_email": "a@b.co", "host": "smtp.x.co", "port": 25,
        "encryption": "STARTTLS"})
    r = a.post("/api/org/smtp/check").json()
    assert not r["ok"] and any("587" in p for p in r["problems"])


def test_logo_must_be_a_data_uri(org):
    a = org()
    assert a.put("/api/org/logo", json={"logo": "http://x/y.png"}).status_code == 422
    assert a.put("/api/org/logo",
                 json={"logo": "data:image/png;base64,AAA"}).status_code == 200
