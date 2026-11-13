"""v4.8: employees and director loans on bank credits, and TDS booked when an
invoice is settled from the bank statement (invoice less money collected)."""
from tests.test_api import mat, cust, vend
from tests.test_v42_bank_links import emp, bank, invoices, _card, CARD_CSV

# The customer invoice from invoices() is 10 x 1250 + 18% IGST = 14,750.
# It is settled by two credits (6,000 + 7,500 = 13,500); 1,250 was TDS.
CSV = (b"Date,Narration,Withdrawal,Deposit,Balance\n"
       b"02/08/2026,NEFT CR CUSTOMER PART 1,,6000.00,106000.00\n"
       b"09/08/2026,NEFT CR CUSTOMER PART 2,,7500.00,113500.00\n"
       b"12/08/2026,ADVANCE RETURNED ASHA,,3000.00,116500.00\n"
       b"15/08/2026,LOAN FROM DIRECTOR RAVI,,500000.00,616500.00\n"
       b"25/08/2026,LOAN REPAID RAVI,100000.00,,516500.00\n"
       b"26/08/2026,NEFT DR VENDOR V001,11564.00,,504936.00\n")


def director(c, name="Ravi Kumar", din="01234567", pan="ABCPK1234F"):
    r = c.post("/api/statements/directors", json={"name": name, "din": din, "pan": pan})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def link(c, txn, **body):
    return c.post(f"/api/statements/txns/{txn['id']}/links", json=body)


# ------------------------------------------------------------ employees on credits
def test_an_employee_can_be_attached_to_a_credit_as_a_refund(org):
    a = org()
    e = emp(a)
    _, t = bank(a, CSV)
    att = a.get(f"/api/statements/txns/{t['ADVANCE RETURNED ASHA']['id']}/attachables").json()
    assert [x["id"] for x in att["employees"]] == [e]
    r = link(a, t["ADVANCE RETURNED ASHA"], link_type="EMPLOYEE", ref_id=e)
    assert r.status_code == 201, r.text
    assert r.json()["purpose"] == "REFUND" and r.json()["amount"] == 3000
    led = a.get("/api/statements/ledger?period=2026-08").json()
    assert led["employee_refunds"] == 3000
    # a refund is not salary or expense
    assert led["employee_salary"] == 0 and led["employee_expense"] == 0


def test_salary_cannot_be_booked_on_a_credit(org):
    a = org()
    e = emp(a)
    _, t = bank(a, CSV)
    r = link(a, t["ADVANCE RETURNED ASHA"], link_type="EMPLOYEE", ref_id=e, purpose="SALARY")
    assert r.status_code == 422


# ------------------------------------------------------------ director loans
def test_director_master_validates_din_and_pan_and_is_unique(org):
    a = org()
    director(a)
    assert a.post("/api/statements/directors", json={"name": "ravi kumar"}).status_code == 409
    assert a.post("/api/statements/directors", json={"name": "X", "din": "12"}).status_code == 422
    assert a.post("/api/statements/directors", json={"name": "X", "pan": "BAD"}).status_code == 422


def test_loan_from_a_director_on_a_credit_and_repayment_on_a_debit(org):
    a = org()
    d = director(a)
    _, t = bank(a, CSV)
    assert link(a, t["LOAN FROM DIRECTOR RAVI"], link_type="DIRECTOR_LOAN",
                ref_id=d).status_code == 201
    assert link(a, t["LOAN REPAID RAVI"], link_type="DIRECTOR_LOAN",
                ref_id=d).status_code == 201
    loans = a.get("/api/statements/director-loans?period=2026-08").json()
    r = loans["directors"][0]
    assert (r["opening"], r["received"], r["repaid"], r["closing"]) == (0, 500000, 100000, 400000)
    assert loans["total_owed"] == 400000
    assert [e["kind"] for e in loans["entries"]] == ["RECEIVED", "REPAID"]
    # the next month opens with what is still owed
    sep = a.get("/api/statements/director-loans?period=2026-09").json()["directors"][0]
    assert sep["opening"] == 400000 and sep["closing"] == 400000
    led = a.get("/api/statements/ledger?period=2026-08").json()
    assert led["director_loans_received"] == 500000 and led["director_loans_repaid"] == 100000
    # the balance shows when choosing a director to attach
    att = a.get(f"/api/statements/txns/{t['NEFT CR CUSTOMER PART 1']['id']}/attachables").json()
    assert att["directors"][0]["balance"] == 400000


def test_director_loans_are_not_attached_to_card_spends(org):
    a = org()
    d = director(a)
    cid = _card(a)
    r = a.post(f"/api/statements/accounts/{cid}/upload?period=2026-08"
               "&default_allocation=COMPANY&default_category=Travel",
               files={"file": ("card.csv", CARD_CSV, "text/csv")})
    assert r.status_code == 200, r.text
    tx = [x for x in a.get(f"/api/statements/accounts/{cid}/txns?period=2026-08").json()
          if x["debit"] > 0][0]
    assert link(a, tx, link_type="DIRECTOR_LOAN", ref_id=d).status_code == 422


# ------------------------------------------------------------ TDS
def test_an_invoice_settled_by_two_credits_books_the_shortfall_as_tds(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    # first credit: part payment, no TDS yet
    r = link(a, t["NEFT CR CUSTOMER PART 1"], link_type="CUST_INV", ref_id=inv["id"])
    assert r.status_code == 201 and r.json()["amount"] == 6000 and r.json()["tds"] == 0
    assert r.json()["invoice_open"] == 8750
    # the same invoice is offered on the second credit, with what is open
    att = a.get(f"/api/statements/txns/{t['NEFT CR CUSTOMER PART 2']['id']}/attachables").json()
    row = att["customer_invoices"][0]
    assert (row["total"], row["attached"], row["open"]) == (14750, 6000, 8750)
    # last credit: the balance of 1,250 was tax deducted by the customer
    r = link(a, t["NEFT CR CUSTOMER PART 2"], link_type="CUST_INV", ref_id=inv["id"],
             amount=7500, tds=1250)
    assert r.status_code == 201, r.text
    assert r.json()["tds"] == 1250 and r.json()["invoice_open"] == 0
    # the invoice is no longer open for attaching
    att = a.get(f"/api/statements/txns/{t['ADVANCE RETURNED ASHA']['id']}/attachables").json()
    assert att["customer_invoices"] == []
    # TDS register: customers section
    reg = a.get("/api/registers/tds").json()
    assert reg["customer_total_tds"] == 1250
    c = reg["customers"][0]
    assert (c["invoice"], c["received"], c["tds"], c["source"]) == (
        inv["doc_no"], 7500, 1250, "Bank statement")
    assert c["implied_rate_pct"] == 10
    # TDS report: customer side, by quarter
    rep = a.get("/api/registers/tds-report").json()["customers"]
    assert rep["total"] == 1250 and rep["by_customer"][0]["quarter"] == "Q2 2026-27"
    # CSV carries the customer section
    csv = a.get("/api/registers/tds.csv").text
    assert "TDS deducted by customers" in csv and "1250" in csv


def test_amount_plus_tds_cannot_exceed_the_invoice(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    link(a, t["NEFT CR CUSTOMER PART 1"], link_type="CUST_INV", ref_id=inv["id"])
    r = link(a, t["NEFT CR CUSTOMER PART 2"], link_type="CUST_INV", ref_id=inv["id"],
             amount=7500, tds=1300)
    assert r.status_code == 422


def test_tds_can_be_booked_on_an_existing_attachment_from_the_balance(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    link(a, t["NEFT CR CUSTOMER PART 1"], link_type="CUST_INV", ref_id=inv["id"])
    l2 = link(a, t["NEFT CR CUSTOMER PART 2"], link_type="CUST_INV", ref_id=inv["id"]).json()
    assert l2["tds"] == 0 and l2["invoice_open"] == 1250
    r = a.put(f"/api/statements/links/{l2['id']}/tds", json={})   # book the balance
    assert r.status_code == 200 and r.json()["tds"] == 1250 and r.json()["invoice_open"] == 0
    assert a.get("/api/registers/tds").json()["customer_total_tds"] == 1250
    # cannot book more than the invoice leaves open
    assert a.put(f"/api/statements/links/{l2['id']}/tds", json={"tds": 2000}).status_code == 422
    # 0 clears it
    assert a.put(f"/api/statements/links/{l2['id']}/tds", json={"tds": 0}).json()["tds"] == 0
    assert a.get("/api/registers/tds").json()["customer_total_tds"] == 0
    # removing the attachment takes its TDS with it
    a.put(f"/api/statements/links/{l2['id']}/tds", json={})
    a.delete(f"/api/statements/links/{l2['id']}")
    assert a.get("/api/registers/tds").json()["customer_total_tds"] == 0


def test_tds_on_a_vendor_invoice_paid_from_the_bank_reaches_the_vendor_register(org):
    a = org()
    _, vi = invoices(a)                 # 10 x 1000 + 18% = 11,800; paid 11,564, TDS 236
    _, t = bank(a, CSV)
    r = link(a, t["NEFT DR VENDOR V001"], link_type="VEND_INV", ref_id=vi["id"],
             amount=11564, tds=236)
    assert r.status_code == 201, r.text
    reg = a.get("/api/registers/tds").json()
    row = [x for x in reg["rows"] if x["source"] == "Bank statement"][0]
    assert (row["vendor_invoice"], row["paid"], row["tds"], row["gross"]) == ("V/1", 11564, 236, 11800)
    rep = a.get("/api/registers/tds-report").json()["vendors"]
    assert rep["total"] == 236 and rep["by_month"][0]["month"] == "2026-08"


def test_tds_is_only_for_invoices(org):
    a = org()
    d = director(a)
    _, t = bank(a, CSV)
    r = link(a, t["LOAN FROM DIRECTOR RAVI"], link_type="DIRECTOR_LOAN", ref_id=d, tds=10)
    assert r.status_code == 422
