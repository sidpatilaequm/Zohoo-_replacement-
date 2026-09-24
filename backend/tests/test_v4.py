"""Version 4: addresses, multiple rates on a code, place of supply, payment terms."""
from datetime import date
from sqlalchemy.exc import IntegrityError

def base(c):
    c.post("/api/hsn", json={"code": "998314", "descr": "IT services", "kind": "SAC",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    m = c.post("/api/materials", json={"code": "SRV", "descr": "Consulting",
        "price": 100000, "cost": 60000, "hsn": "998314", "uom": "NOS",
        "stock_qty": 999}).json()["id"]
    cu = c.post("/api/customers", json={"code": "C1", "name": "Apollo",
        "party_type": "B2B", "bill_addr": "MG Rd", "bill_city": "Bengaluru",
        "bill_state": "29", "payment_term_days": 30, "payment_terms": "30 days net",
        "bank_name": "HDFC Bank", "bank_ifsc": "HDFC0000123",
        "bank_account": "50100099112233",
        "gstins": [{"gstin": "29AAACT1234N1Z2", "is_default": True}]}).json()["id"]
    return m, cu


# ------------------------------------------------ additional addresses
def test_customer_can_hold_several_addresses(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    a1 = c.post(f"/api/parties/customer/{cu}/addresses", json={"label": "Head office",
        "addr": "MG Rd", "city": "Bengaluru", "state_code": "29",
        "gstin": "29AAACT1234N1Z2", "is_default": True})
    a2 = c.post(f"/api/parties/customer/{cu}/addresses", json={"label": "Chennai branch",
        "addr": "Mount Rd", "city": "Chennai", "state_code": "33",
        "gstin": "33AAACT1234N1ZA"})
    assert a1.status_code == 201 and a2.status_code == 201
    rows = c.get(f"/api/parties/customer/{cu}/addresses").json()
    assert len(rows) == 2
    assert rows[0]["is_default"] is True          # default sorts first


def test_address_gstin_must_match_its_state(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    r = c.post(f"/api/parties/customer/{cu}/addresses", json={"label": "Wrong",
        "addr": "x", "city": "Chennai", "state_code": "33",
        "gstin": "29AAACT1234N1Z2"})
    assert r.status_code == 422 and "state" in r.text.lower()


def test_duplicate_address_label_refused(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    body = {"label": "Head office", "addr": "x", "city": "Bengaluru", "state_code": "29"}
    assert c.post(f"/api/parties/customer/{cu}/addresses", json=body).status_code == 201
    assert c.post(f"/api/parties/customer/{cu}/addresses", json=body).status_code == 409


def test_vendor_addresses_work_the_same_way(org, seed_ref):
    c = org(); seed_ref(c)
    v = c.post("/api/vendors", json={"code": "V1", "name": "Redington",
        "party_type": "B2B", "addr": "x", "city": "Chennai", "state_code": "33",
        "gstins": [{"gstin": "33AAACR1234K1Z5", "is_default": True}]}).json()["id"]
    r = c.post(f"/api/parties/vendor/{v}/addresses", json={"label": "Warehouse",
        "addr": "Ambattur", "city": "Chennai", "state_code": "33"})
    assert r.status_code == 201
    assert len(c.get(f"/api/parties/vendor/{v}/addresses").json()) == 1


def test_address_on_a_document_cannot_be_deleted(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    a = c.post(f"/api/parties/customer/{cu}/addresses", json={"label": "Chennai branch",
        "addr": "Mount Rd", "city": "Chennai", "state_code": "33",
        "gstin": "33AAACT1234N1ZA"}).json()["id"]
    c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "bill_addr_id": a, "lines": [{"material_id": m, "qty": 1, "price": 1000}]})
    r = c.delete(f"/api/addresses/{a}")
    assert r.status_code == 409 and "inactive" in r.text


# ---------------------------------------------- place of supply
def test_billing_address_sets_the_place_of_supply(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    a = c.post(f"/api/parties/customer/{cu}/addresses", json={"label": "Chennai branch",
        "addr": "Mount Rd", "city": "Chennai", "state_code": "33",
        "gstin": "33AAACT1234N1ZA"}).json()["id"]
    inv = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "bill_addr_id": a, "lines": [{"material_id": m, "qty": 1, "price": 1000}]}).json()
    # supplier is in 29, billed to 33, so it is inter-state
    assert inv["totals"]["igst"] > 0 and inv["totals"]["cgst"] == 0


def test_place_of_supply_can_be_overridden(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    # customer is in 29 with the supplier, so it would default to intra-state
    inv = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "pos_state": "33", "lines": [{"material_id": m, "qty": 1, "price": 1000}]}).json()
    assert inv["totals"]["igst"] > 0 and inv["totals"]["cgst"] == 0
    full = c.get(f"/api/invoices/{inv['id']}").json()
    assert full["invoice"]["pos_state"] == "33"
    assert full["pos_manual"] is True          # recorded as a deliberate override


def test_a_nonsense_place_of_supply_is_refused(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    r = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "pos_state": "ZZ", "lines": [{"material_id": m, "qty": 1, "price": 1000}]})
    assert r.status_code == 422


# ---------------------------------------------- several rates on a code
def test_a_code_can_carry_several_rates(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    h = c.get("/api/hsn").json()[0]["id"]
    r1 = c.post(f"/api/hsn/{h}/rates", json={"label": "Standard 18%",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18, "is_default": True})
    r2 = c.post(f"/api/hsn/{h}/rates", json={"label": "Concessional 5%",
        "sgst_pct": 2.5, "cgst_pct": 2.5, "igst_pct": 5,
        "condition_note": "Where input tax credit is not taken"})
    assert r1.status_code == 201 and r2.status_code == 201
    assert len(c.get(f"/api/hsn/{h}/rates").json()) == 2


def test_a_rate_whose_split_does_not_add_up_is_refused(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    h = c.get("/api/hsn").json()[0]["id"]
    r = c.post(f"/api/hsn/{h}/rates", json={"label": "Wrong",
        "sgst_pct": 6, "cgst_pct": 6, "igst_pct": 18})
    assert r.status_code == 422 and "does not equal" in r.text


def test_the_chosen_rate_is_what_the_invoice_charges(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    h = c.get("/api/hsn").json()[0]["id"]
    low = c.post(f"/api/hsn/{h}/rates", json={"label": "Concessional 5%",
        "sgst_pct": 2.5, "cgst_pct": 2.5, "igst_pct": 5}).json()["id"]
    # material default is 18%; the line picks 5%
    plain = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1000}]}).json()
    assert plain["totals"]["cgst"] == 90.0        # 9% of 1000
    picked = c.post("/api/invoices", json={"doc_date": "2026-08-11", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1000,
                   "hsn_rate_id": low}]}).json()
    assert picked["totals"]["cgst"] == 25.0       # 2.5% of 1000


def test_the_split_still_follows_the_place_of_supply(org, seed_ref):
    """Choosing the rate must not choose the head. That stays automatic."""
    c = org(); seed_ref(c); m, cu = base(c)
    h = c.get("/api/hsn").json()[0]["id"]
    low = c.post(f"/api/hsn/{h}/rates", json={"label": "Concessional 5%",
        "sgst_pct": 2.5, "cgst_pct": 2.5, "igst_pct": 5}).json()["id"]
    intra = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1000, "hsn_rate_id": low}]}).json()
    inter = c.post("/api/invoices", json={"doc_date": "2026-08-11", "customer_id": cu,
        "pos_state": "33",
        "lines": [{"material_id": m, "qty": 1, "price": 1000, "hsn_rate_id": low}]}).json()
    assert intra["totals"]["cgst"] == 25.0 and intra["totals"]["igst"] == 0
    assert inter["totals"]["igst"] == 50.0 and inter["totals"]["cgst"] == 0
    assert intra["totals"]["tax"] == inter["totals"]["tax"]


def test_a_rate_from_another_code_is_refused(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    other = c.post("/api/hsn", json={"code": "300490", "descr": "Medicaments",
        "sgst_pct": 6, "cgst_pct": 6, "igst_pct": 12}).json()["id"]
    bad = c.post(f"/api/hsn/{other}/rates", json={"label": "12%",
        "sgst_pct": 6, "cgst_pct": 6, "igst_pct": 12}).json()["id"]
    r = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1000, "hsn_rate_id": bad}]})
    assert r.status_code == 422 and "different code" in r.text


# ---------------------------------------------- payment terms
def test_due_date_comes_from_the_payment_terms(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    inv = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1000}]}).json()
    full = c.get(f"/api/invoices/{inv['id']}").json()
    assert full["invoice"]["due_date"] == "2026-09-09"      # 10 Aug + 30 days


def test_an_explicit_due_date_still_wins(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    inv = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "due_date": "2026-08-25",
        "lines": [{"material_id": m, "qty": 1, "price": 1000}]}).json()
    full = c.get(f"/api/invoices/{inv['id']}").json()
    assert full["invoice"]["due_date"] == "2026-08-25"


def test_invoice_carries_the_bank_and_terms_for_the_footer(org, seed_ref):
    c = org(); seed_ref(c); m, cu = base(c)
    inv = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 1000}]}).json()
    pay = c.get(f"/api/invoices/{inv['id']}").json()["payment"]
    assert pay["bank_name"] == "HDFC Bank" and pay["bank_ifsc"] == "HDFC0000123"
    assert pay["bank_account"] == "50100099112233"
    assert pay["terms"] == "30 days net" and pay["term_days"] == 30


# ---------------------------------------------- the broken links
def test_reports_endpoints_need_reports_not_gstr(org, seed_ref):
    """A group with Reports but not GST Returns must be able to open Reports."""
    c = org(); seed_ref(c)
    gid = [g for g in c.get("/api/groups").json() if g["name"] == "Sales"][0]["id"]
    perms = [g for g in c.get("/api/groups").json() if g["name"] == "Sales"][0]["perms"]
    assert "reports" in perms and "gstr" not in perms
    c.post("/api/users", json={"name": "S", "email": "sales@x.co",
        "password": "correct horse", "group_id": gid})
    tok = c.api.post("/api/auth/signin", json={"email": "sales@x.co",
        "password": "correct horse"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}", "X-Tenant-Id": str(c.tid)}
    for p in ("/api/returns/reports/receivables", "/api/returns/reports/payables",
              "/api/returns/reports/margin"):
        assert c.api.get(p, headers=h).status_code == 200, p


def test_period_list_is_shared_by_the_screens_that_need_it(org, seed_ref):
    c = org(); seed_ref(c)
    gid = [g for g in c.get("/api/groups").json() if g["name"] == "Sales"][0]["id"]
    c.post("/api/users", json={"name": "S", "email": "s2@x.co",
        "password": "correct horse", "group_id": gid})
    tok = c.api.post("/api/auth/signin", json={"email": "s2@x.co",
        "password": "correct horse"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}", "X-Tenant-Id": str(c.tid)}
    assert c.api.get("/api/returns/periods", headers=h).status_code == 200
