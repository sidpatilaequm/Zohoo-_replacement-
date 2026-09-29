"""v4.2: employees, invoices and employees attached to bank transactions,
and a card statement marked company or personal as it is uploaded."""
from tests.test_api import mat, cust, vend

BANK_CSV = (b"Date,Narration,Withdrawal,Deposit,Balance\n"
            b"02/08/2026,NEFT CR CUSTOMER C001,,14750.00,114750.00\n"
            b"05/08/2026,NEFT DR VENDOR V001,11800.00,,102950.00\n"
            b"28/08/2026,SALARY AUG ASHA,55000.00,,47950.00\n"
            b"29/08/2026,REIMB TRAVEL ASHA,2500.00,,45450.00\n")

CARD_CSV = (b"Date,Description,Amount\n"
            b"03/08/2026,AMAZON WEB SERVICES,4200.00\n"
            b"09/08/2026,INDIGO AIRLINES,8900.00\n"
            b"20/08/2026,PAYMENT RECEIVED THANK YOU,-13100.00\n")


def emp(c, code="E001", first="Asha", last="Rao", email="asha@aequm.in"):
    r = c.post("/api/employees", json={"emp_code": code, "first_name": first,
                                        "last_name": last, "email": email})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def bank(c, csv=BANK_CSV):
    a = c.post("/api/statements/accounts", json={"kind": "BANK", "label": "HDFC Current"}).json()
    r = c.post(f"/api/statements/accounts/{a['id']}/upload?period=2026-08",
               files={"file": ("aug.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    rows = c.get(f"/api/statements/accounts/{a['id']}/txns?period=2026-08").json()
    return a["id"], {t["descr"]: t for t in rows}


def invoices(c):
    m = mat(c, price=1250, cost=1000); cid = cust(c); vid = vend(c)
    inv = c.post("/api/invoices", json={"doc_date": "2026-08-01", "customer_id": cid,
                 "lines": [{"material_id": m, "qty": 10}]}).json()
    vi = c.post("/api/vendor-invoices", json={"doc_no": "V/1", "doc_date": "2026-08-01",
                "vendor_id": vid, "lines": [{"material_id": m, "qty": 10, "price": 1000}]})
    assert vi.status_code == 201, vi.text
    return inv, vi.json()


# ------------------------------------------------------------ employees
def test_employee_master_holds_id_names_and_email(org):
    a = org()
    emp(a)
    r = a.get("/api/employees").json()
    assert r[0]["emp_code"] == "E001" and r[0]["name"] == "Asha Rao"
    assert r[0]["email"] == "asha@aequm.in"


def test_employee_id_and_email_are_unique_within_the_organisation(org):
    a = org()
    emp(a)
    assert a.post("/api/employees", json={"emp_code": "E001", "first_name": "B",
        "last_name": "C", "email": "b@aequm.in"}).status_code == 409
    assert a.post("/api/employees", json={"emp_code": "E002", "first_name": "B",
        "last_name": "C", "email": "ASHA@aequm.in"}).status_code == 409


def test_employee_email_must_be_valid(org):
    a = org()
    r = a.post("/api/employees", json={"emp_code": "E9", "first_name": "X",
        "last_name": "Y", "email": "not-an-email"})
    assert r.status_code == 422


def test_employees_are_scoped_to_their_organisation(org):
    a = org(name="One", email="one@x.co"); b = org(name="Two", email="two@x.co")
    emp(a); emp(b)          # same ID and e-mail are fine in another organisation
    assert len(a.get("/api/employees").json()) == 1


# ------------------------------------------------------------ bank links
def test_customer_invoice_attaches_to_a_credit(org):
    a = org(); inv, _ = invoices(a); aid, t = bank(a)
    cr = t["NEFT CR CUSTOMER C001"]
    opts = a.get(f"/api/statements/txns/{cr['id']}/attachables").json()
    assert opts["side"] == "CREDIT" and opts["customer_invoices"][0]["exact"]
    r = a.post(f"/api/statements/txns/{cr['id']}/links",
               json={"link_type": "CUST_INV", "ref_id": inv["id"]})
    assert r.status_code == 201, r.text
    assert r.json()["amount"] == 14750.0 and r.json()["ref"] == inv["doc_no"]
    row = [x for x in a.get(f"/api/statements/accounts/{aid}/txns?period=2026-08").json()
           if x["id"] == cr["id"]][0]
    assert row["unattached"] == 0 and row["links"][0]["link_type"] == "CUST_INV"


def test_customer_invoice_cannot_go_on_a_debit_nor_vendor_invoice_on_a_credit(org):
    a = org(); inv, vi = invoices(a); _, t = bank(a)
    dr, cr = t["NEFT DR VENDOR V001"], t["NEFT CR CUSTOMER C001"]
    r = a.post(f"/api/statements/txns/{dr['id']}/links",
               json={"link_type": "CUST_INV", "ref_id": inv["id"]})
    assert r.status_code == 422 and "credit" in r.text
    r = a.post(f"/api/statements/txns/{cr['id']}/links",
               json={"link_type": "VEND_INV", "ref_id": vi["id"]})
    assert r.status_code == 422 and "debit" in r.text


def test_vendor_invoice_attaches_to_a_debit(org):
    a = org(); _, vi = invoices(a); _, t = bank(a)
    dr = t["NEFT DR VENDOR V001"]
    opts = a.get(f"/api/statements/txns/{dr['id']}/attachables").json()
    assert opts["side"] == "DEBIT" and opts["vendor_invoices"][0]["doc_no"] == "V/1"
    r = a.post(f"/api/statements/txns/{dr['id']}/links",
               json={"link_type": "VEND_INV", "ref_id": vi["id"]})
    assert r.status_code == 201 and r.json()["amount"] == 11800.0


def test_attached_amounts_never_exceed_the_transaction(org):
    a = org(); inv, _ = invoices(a); _, t = bank(a)
    cr = t["NEFT CR CUSTOMER C001"]
    r = a.post(f"/api/statements/txns/{cr['id']}/links",
               json={"link_type": "CUST_INV", "ref_id": inv["id"], "amount": 20000})
    assert r.status_code == 422


def test_an_invoice_is_not_attached_beyond_its_total(org):
    a = org(); m = mat(a, price=1250); cid = cust(a)
    inv = a.post("/api/invoices", json={"doc_date": "2026-08-01", "customer_id": cid,
                 "lines": [{"material_id": m, "qty": 1}]}).json()   # 1475.00
    csv = (b"Date,Narration,Withdrawal,Deposit,Balance\n"
           b"02/08/2026,PART ONE,,1000.00,1000.00\n"
           b"03/08/2026,PART TWO,,1000.00,2000.00\n")
    _, t = bank(a, csv)
    r1 = a.post(f"/api/statements/txns/{t['PART ONE']['id']}/links",
                json={"link_type": "CUST_INV", "ref_id": inv["id"]})
    assert r1.json()["amount"] == 1000.0
    r2 = a.post(f"/api/statements/txns/{t['PART TWO']['id']}/links",
                json={"link_type": "CUST_INV", "ref_id": inv["id"]})
    assert r2.json()["amount"] == 475.0       # only what was still open


def test_salary_and_expense_attach_to_an_employee_and_reach_the_ledger(org):
    a = org(); e = emp(a); _, t = bank(a)
    sal, reimb = t["SALARY AUG ASHA"], t["REIMB TRAVEL ASHA"]
    r = a.post(f"/api/statements/txns/{sal['id']}/links",
               json={"link_type": "EMPLOYEE", "ref_id": e})
    assert r.status_code == 422 and "salary or an expense" in r.text
    assert a.post(f"/api/statements/txns/{sal['id']}/links", json={
        "link_type": "EMPLOYEE", "ref_id": e, "purpose": "SALARY"}).status_code == 201
    h = a.post("/api/expense-heads", json={"exp_code": "EXP001", "name": "Travel"}).json()["id"]
    assert a.post(f"/api/statements/txns/{reimb['id']}/links", json={
        "link_type": "EMPLOYEE", "ref_id": e, "purpose": "EXPENSE",
        "expense_id": h}).status_code == 201
    L = a.get("/api/statements/ledger?period=2026-08").json()
    assert L["employee_salary"] == 55000.0 and L["employee_expense"] == 2500.0
    # an employee with bank history cannot be deleted, only made inactive
    assert a.delete(f"/api/employees/{e}").status_code == 409


def test_removing_an_attachment_frees_the_amount(org):
    a = org(); inv, _ = invoices(a); _, t = bank(a)
    cr = t["NEFT CR CUSTOMER C001"]
    lid = a.post(f"/api/statements/txns/{cr['id']}/links",
                 json={"link_type": "CUST_INV", "ref_id": inv["id"]}).json()["id"]
    assert a.delete(f"/api/statements/links/{lid}").status_code == 204
    opts = a.get(f"/api/statements/txns/{cr['id']}/attachables").json()
    assert opts["remaining"] == 14750.0


def test_upload_with_attachments_cannot_be_deleted(org):
    a = org(); inv, _ = invoices(a); aid, t = bank(a)
    cr = t["NEFT CR CUSTOMER C001"]
    a.post(f"/api/statements/txns/{cr['id']}/links",
           json={"link_type": "CUST_INV", "ref_id": inv["id"]})
    up = a.get(f"/api/statements/accounts/{aid}/uploads").json()[0]
    assert a.delete(f"/api/statements/uploads/{up['id']}").status_code == 409


# ------------------------------------------------------------ card upload
def _card(c):
    return c.post("/api/statements/accounts", json={"kind": "CARD", "label": "RBL Platinum",
                  "holder": "Alok"}).json()["id"]


def test_card_statement_can_be_marked_company_as_it_is_uploaded(org):
    a = org(); cid = _card(a)
    r = a.post(f"/api/statements/accounts/{cid}/upload?period=2026-08"
               "&default_allocation=COMPANY&default_category=Travel",
               files={"file": ("card.csv", CARD_CSV, "text/csv")})
    assert r.status_code == 200, r.text
    rows = a.get(f"/api/statements/accounts/{cid}/txns?period=2026-08").json()
    spends = [x for x in rows if x["debit"] > 0]
    assert {x["allocation"] for x in spends} == {"COMPANY"}
    assert {x["category"] for x in spends} == {"Travel"}
    assert [x["allocation"] for x in rows if x["debit"] == 0] == ["NA"]   # the payment
    rec = a.get("/api/statements/reconcile?period=2026-08").json()[0]
    assert rec["company"] == 13100.0 and rec["unallocated"] == 0


def test_card_statement_can_be_marked_personal_as_it_is_uploaded(org):
    a = org(); cid = _card(a)
    a.post(f"/api/statements/accounts/{cid}/upload?period=2026-08&default_allocation=PERSONAL",
           files={"file": ("card.csv", CARD_CSV, "text/csv")})
    rec = a.get("/api/statements/reconcile?period=2026-08").json()[0]
    assert rec["personal"] == 13100.0 and rec["company"] == 0


def test_company_upload_needs_a_category_and_bank_uploads_take_no_marking(org):
    a = org(); cid = _card(a)
    r = a.post(f"/api/statements/accounts/{cid}/upload?period=2026-08&default_allocation=COMPANY",
               files={"file": ("card.csv", CARD_CSV, "text/csv")})
    assert r.status_code == 422 and "category" in r.text
    b = a.post("/api/statements/accounts", json={"kind": "BANK", "label": "HDFC"}).json()["id"]
    r = a.post(f"/api/statements/accounts/{b}/upload?period=2026-08&default_allocation=PERSONAL",
               files={"file": ("b.csv", BANK_CSV, "text/csv")})
    assert r.status_code == 422


def test_a_single_spend_can_still_be_changed_after_a_marked_upload(org):
    a = org(); cid = _card(a)
    a.post(f"/api/statements/accounts/{cid}/upload?period=2026-08&default_allocation=PERSONAL",
           files={"file": ("card.csv", CARD_CSV, "text/csv")})
    t = [x for x in a.get(f"/api/statements/accounts/{cid}/txns?period=2026-08").json()
         if x["descr"] == "AMAZON WEB SERVICES"][0]
    r = a.put(f"/api/statements/txns/{t['id']}/allocate",
              json={"allocation": "COMPANY", "category": "Software and subscriptions"})
    assert r.status_code == 200
    rec = a.get("/api/statements/reconcile?period=2026-08").json()[0]
    assert rec["company"] == 4200.0 and rec["personal"] == 8900.0


def test_unallocated_spends_can_be_marked_in_one_go(org):
    a = org(); cid = _card(a)
    a.post(f"/api/statements/accounts/{cid}/upload?period=2026-08",
           files={"file": ("card.csv", CARD_CSV, "text/csv")})
    r = a.put(f"/api/statements/accounts/{cid}/allocate-all?period=2026-08",
              json={"allocation": "COMPANY", "category": "Other"})
    assert r.status_code == 200 and r.json()["updated"] == 2
