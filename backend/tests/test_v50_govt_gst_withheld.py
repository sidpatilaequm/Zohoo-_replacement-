"""v5.0: government filings on bank debits (GST, TDS, PF, ESI, other statutory
payments), GST withheld (GST TDS, CGST Act s.51) alongside TDS when an
invoice does not tally, several payments against one invoice at once, vendor
invoices paid from the bank showing on Vendor Payments, and the financial year.

The customer invoice from invoices() is 10 x 1,250 = 12,500 taxable + 18% IGST
= 14,750. A government customer keeps back TDS at 10% (1,250) and GST TDS at
2% (250) and pays 13,250, here in two parts: 6,000 + 7,250."""
from datetime import date

from tests.test_v42_bank_links import bank, invoices

CSV = (b"Date,Narration,Withdrawal,Deposit,Balance\n"
       b"02/08/2026,NEFT CR DEPT PART 1,,6000.00,106000.00\n"
       b"09/08/2026,NEFT CR DEPT PART 2,,7250.00,113250.00\n"
       b"10/08/2026,GST CHALLAN CPIN 2608,18000.00,,95250.00\n"
       b"11/08/2026,TDS CHALLAN ITNS281,5000.00,,90250.00\n"
       b"12/08/2026,EPFO PF ECR JUL,24000.00,,66250.00\n"
       b"13/08/2026,ESIC CHALLAN JUL,3000.00,,63250.00\n"
       b"14/08/2026,PROF TAX KAR,2500.00,,60750.00\n"
       b"20/08/2026,NEFT DR VENDOR PART,6000.00,,54750.00\n"
       b"21/08/2026,NEFT DR VENDOR REST,5564.00,,49186.00\n")


def link(c, txn, **body):
    return c.post(f"/api/statements/txns/{txn['id']}/links", json=body)


def receipts_for(c, doc_no):
    return [r for r in c.get("/api/receipts").json() if r["doc"] == doc_no]


# ------------------------------------------------------------ GST withheld
def test_tds_and_gst_withheld_close_an_invoice_paid_in_two_parts(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    assert link(a, t["NEFT CR DEPT PART 1"], link_type="CUST_INV", ref_id=inv["id"]).status_code == 201
    att = a.get(f"/api/statements/txns/{t['NEFT CR DEPT PART 2']['id']}/attachables").json()
    row = next(x for x in att["customer_invoices"] if x["id"] == inv["id"])
    assert row["open"] == 8750 and row["taxable"] == 12500       # the shortfall shows against the taxable value
    r = link(a, t["NEFT CR DEPT PART 2"], link_type="CUST_INV", ref_id=inv["id"],
             amount=7250, tds=1250, gst_tds=250)
    assert r.status_code == 201, r.text
    assert r.json()["tds"] == 1250 and r.json()["gst_tds"] == 250 and r.json()["invoice_open"] == 0
    # the receipt on Customer Payments carries both, and the invoice is paid
    recs = receipts_for(a, inv["doc_no"])
    assert sorted((x["amount"], x["tds"], x["gst_tds"]) for x in recs) == [(6000, 0, 0), (7250, 1250, 250)]
    assert all(x["from_bank"] for x in recs)
    reg = a.get("/api/registers/gst-tds?period=FY2026-27").json()
    assert reg["customer_total"] == 250 and reg["customers"][0]["implied_rate_pct"] == 2
    tds = a.get("/api/registers/tds?period=FY2026-27").json()
    assert tds["customer_total_tds"] == 1250
    # nothing left open, so the invoice is not offered again
    att = a.get(f"/api/statements/txns/{t['NEFT CR DEPT PART 1']['id']}/attachables").json()
    assert inv["id"] not in [x["id"] for x in att["customer_invoices"]]


def test_money_plus_tds_plus_gst_withheld_cannot_exceed_what_is_open(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    r = link(a, t["NEFT CR DEPT PART 2"], link_type="CUST_INV", ref_id=inv["id"],
             amount=7250, tds=7000, gst_tds=1000)
    assert r.status_code == 422 and "GST withheld" in r.json()["detail"]


def test_gst_withheld_can_be_set_after_the_fact_and_the_rest_booked_as_tds(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    link(a, t["NEFT CR DEPT PART 1"], link_type="CUST_INV", ref_id=inv["id"])
    l2 = link(a, t["NEFT CR DEPT PART 2"], link_type="CUST_INV", ref_id=inv["id"]).json()
    assert l2["invoice_open"] == 1500
    r = a.put(f"/api/statements/links/{l2['id']}/tds", json={"gst_tds": 250})
    assert r.status_code == 200 and r.json()["gst_tds"] == 250 and r.json()["invoice_open"] == 1250
    r = a.put(f"/api/statements/links/{l2['id']}/tds", json={})     # the rest as TDS
    assert (r.json()["tds"], r.json()["gst_tds"], r.json()["invoice_open"]) == (1250, 250, 0)
    rec = next(x for x in receipts_for(a, inv["doc_no"]) if x["amount"] == 7250)
    assert (rec["tds"], rec["gst_tds"]) == (1250, 250)
    assert a.put(f"/api/statements/links/{l2['id']}/tds", json={"gst_tds": 400}).status_code == 422


def test_a_receipt_entered_by_hand_can_carry_gst_withheld(org):
    a = org()
    inv, _ = invoices(a)
    r = a.post("/api/receipts", json={"pay_type": "REC", "pay_date": "2026-08-05", "invoice_id": inv["id"],
                                      "amount": 13250, "tds": 1250, "gst_tds": 250, "mode": "NEFT"})
    assert r.status_code == 201, r.text
    assert r.json()["outstanding_after"] == 0
    assert a.post("/api/receipts", json={"pay_type": "REC", "pay_date": "2026-08-05", "invoice_id": inv["id"],
                                         "amount": 1, "gst_tds": 1, "mode": "NEFT"}).status_code == 422


# ------------------------------------------------------------ several payments at once
def test_an_invoice_shows_every_payment_with_tds_and_gst_withheld(org):
    a = org()
    inv, _ = invoices(a)
    a.post("/api/receipts", json={"pay_type": "REC", "pay_date": "2026-08-01", "invoice_id": inv["id"],
                                  "amount": 1500, "mode": "UPI"})
    _, t = bank(a, CSV)
    link(a, t["NEFT CR DEPT PART 1"], link_type="CUST_INV", ref_id=inv["id"])
    s = a.get(f"/api/statements/invoice-payments?link_type=CUST_INV&id={inv['id']}").json()
    assert (s["total"], s["taxable"], s["gst"], s["paid"], s["open"]) == (14750, 12500, 2250, 7500, 7250)
    assert [(p["amount"], p["from_bank"]) for p in s["payments"]] == [(1500, False), (6000, True)]
    assert s["payments"][1]["source"].startswith("Bank statement")
    # the credit still to attach is offered, the exact amount first
    assert s["can_attach"] and s["candidates"][0]["descr"] == "NEFT CR DEPT PART 2"
    assert s["candidates"][0]["exact"] is True


def test_several_bank_lines_attach_to_one_invoice_at_once_with_the_withholding(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    r = a.post("/api/statements/invoice-payments", json={
        "link_type": "CUST_INV", "ref_id": inv["id"], "tds": 1250, "gst_tds": 250,
        "items": [{"txn_id": t["NEFT CR DEPT PART 1"]["id"]}, {"txn_id": t["NEFT CR DEPT PART 2"]["id"]}]})
    assert r.status_code == 201, r.text
    s = r.json()
    assert (s["paid"], s["tds"], s["gst_tds"], s["open"]) == (13250, 1250, 250, 0)
    assert len(receipts_for(a, inv["doc_no"])) == 2


def test_attaching_several_lines_is_all_or_nothing(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    r = a.post("/api/statements/invoice-payments", json={
        "link_type": "CUST_INV", "ref_id": inv["id"],
        "items": [{"txn_id": t["NEFT CR DEPT PART 1"]["id"]}, {"txn_id": t["GST CHALLAN CPIN 2608"]["id"]}]})
    assert r.status_code == 422 and "nothing was attached" in r.json()["detail"]
    assert receipts_for(a, inv["doc_no"]) == []
    assert a.get(f"/api/statements/invoice-payments?link_type=CUST_INV&id={inv['id']}").json()["paid"] == 0


# ------------------------------------------------------------ vendor side synchronised
def test_a_vendor_invoice_paid_from_the_bank_shows_on_vendor_payments_and_payables(org):
    a = org()
    _, vi = invoices(a)
    _, t = bank(a, CSV)
    att = a.get(f"/api/statements/txns/{t['NEFT DR VENDOR PART']['id']}/attachables").json()
    total = next(x for x in att["vendor_invoices"] if x["id"] == vi["id"])["total"]
    l1 = link(a, t["NEFT DR VENDOR PART"], link_type="VEND_INV", ref_id=vi["id"]).json()
    pays = [p for p in a.get("/api/vendor-payments").json() if p["doc"] == vi["doc_no"]]
    assert [(p["amount"], p["from_bank"]) for p in pays] == [(6000, True)]
    # a payment entered by hand on Vendor Payments now counts on the statement too
    a.post("/api/vendor-payments", json={"pay_type": "PAY", "pay_date": "2026-08-20", "vinv_id": vi["id"],
                                         "amount": 100, "tds": 0, "mode": "UPI"})
    att = a.get(f"/api/statements/txns/{t['NEFT DR VENDOR REST']['id']}/attachables").json()
    row = next(x for x in att["vendor_invoices"] if x["id"] == vi["id"])
    assert row["open"] == round(total - 6100, 2) and row["payments"] == 100
    rest = round(total - 6100, 2)
    r = link(a, t["NEFT DR VENDOR REST"], link_type="VEND_INV", ref_id=vi["id"],
             amount=min(5564, rest), tds=round(rest - min(5564, rest), 2) or None)
    assert r.status_code == 201, r.text
    payables = a.get("/api/returns/reports/payables").json()
    assert vi["doc_no"] not in [p["doc_no"] for p in payables]
    # the bank-posted payment goes only with its attachment
    pid = next(p["id"] for p in a.get("/api/vendor-payments").json() if p["amount"] == 6000)
    assert a.delete(f"/api/payments/{pid}").status_code == 409
    assert a.delete(f"/api/statements/links/{l1['id']}").status_code == 204
    assert 6000 not in [p["amount"] for p in a.get("/api/vendor-payments").json()]


# ------------------------------------------------------------ government filings
def test_government_payments_are_attached_to_debits_and_listed_by_kind(org):
    a = org()
    _, t = bank(a, CSV)
    for descr, kind in [("GST CHALLAN CPIN 2608", "GST"), ("TDS CHALLAN ITNS281", "TDS"),
                        ("EPFO PF ECR JUL", "PF"), ("ESIC CHALLAN JUL", "ESI")]:
        r = link(a, t[descr], link_type="GOVT", govt_kind=kind, govt_period="2026-07",
                 challan_ref=descr.split()[-1])
        assert r.status_code == 201, r.text
    # "Others" needs to say what it was for
    assert link(a, t["PROF TAX KAR"], link_type="GOVT", govt_kind="OTHER").status_code == 422
    r = link(a, t["PROF TAX KAR"], link_type="GOVT", govt_kind="OTHER", govt_descr="Professional tax")
    assert r.status_code == 201 and r.json()["ref"] == "Other statutory payment"
    assert "Professional tax" in r.json()["party"]
    # money received is not a government payment
    assert link(a, t["NEFT CR DEPT PART 1"], link_type="GOVT", govt_kind="GST").status_code == 422
    assert link(a, t["NEFT DR VENDOR REST"], link_type="GOVT").status_code == 422    # kind missing
    reg = a.get("/api/statements/govt-payments?period=FY2026-27").json()
    by = {k["kind"]: k["amount"] for k in reg["by_kind"]}
    assert by == {"GST": 18000, "TDS": 5000, "PF": 24000, "ESI": 3000, "OTHER": 2500}
    assert reg["total"] == 52500 and reg["rows"][0]["for_month"] == "2026-07"
    assert a.get("/api/statements/govt-payments?period=FY2025-26").json()["rows"] == []
    # GST withheld cannot be booked on a government payment
    assert link(a, t["NEFT DR VENDOR PART"], link_type="GOVT", govt_kind="GST", gst_tds=10).status_code == 422


# ------------------------------------------------------------ financial year
def test_financial_years_include_the_current_one_and_follow_the_company_year(org):
    a = org()
    invoices(a)                         # dated August 2026
    fys = a.get("/api/returns/financial-years").json()
    labels = [f["label"] for f in fys]
    assert "2026-27" in labels
    cur = [f for f in fys if f["current"]]
    assert len(cur) == 1
    today = date.today()
    y = today.year if today.month >= 4 else today.year - 1
    assert cur[0]["label"] == f"{y}-{str(y + 1)[-2:]}" and cur[0]["start"] == f"{y}-04-01"
    f26 = next(f for f in fys if f["label"] == "2026-27")
    assert (f26["start"], f26["end"]) == ("2026-04-01", "2027-03-31")


def test_bank_statement_lines_can_be_read_for_a_financial_year(org):
    a = org()
    aid, _ = bank(a, CSV)
    assert len(a.get(f"/api/statements/accounts/{aid}/txns?period=FY2026-27").json()) == 9
    assert a.get(f"/api/statements/accounts/{aid}/txns?period=FY2025-26").json() == []
    assert a.get("/api/statements/director-loans?period=FY2026-27").status_code == 200
    assert a.get("/api/statements/ledger?period=FY2026-27").status_code == 200
    assert a.get(f"/api/statements/accounts/{aid}/txns?period=nonsense").status_code == 422
