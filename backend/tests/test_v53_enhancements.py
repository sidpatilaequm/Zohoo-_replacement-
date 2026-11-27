"""v5.3 enhancements:
1. Settle both credits and debits with Government Agencies on bank statements.
2. Attach payment to vendor without purchase invoice (vendor advances / unbilled payments).
3. TDS register reporting monthly breakdown of TDS deducted while paying.
"""
from decimal import Decimal
from tests.test_v42_bank_links import bank, invoices

CSV = (b"Date,Narration,Withdrawal,Deposit,Balance\n"
       b"01/08/2026,GST REFUND ORDER 2026,,15000.00,115000.00\n"
       b"02/08/2026,GST CHALLAN 2608,20000.00,,95000.00\n"
       b"03/08/2026,ADVANCE TO VENDOR PART,12000.00,,83000.00\n"
       b"04/08/2026,VENDOR REFUND OF ADVANCE,,2000.00,85000.00\n")


def link(c, txn, **body):
    return c.post(f"/api/statements/txns/{txn['id']}/links", json=body)


def test_government_credit_and_debit_settlement(org):
    a = org()
    _, t = bank(a, CSV)

    # 1. Debit: statutory payment
    r_dr = link(a, t["GST CHALLAN 2608"], link_type="GOVT", govt_kind="GST", govt_period="2026-07",
                challan_ref="CPIN2608")
    assert r_dr.status_code == 201, r_dr.text
    assert "payment" in r_dr.json()["ref"]
    assert "Government Agencies" in r_dr.json()["party"]

    # 2. Credit: statutory refund / receipt
    r_cr = link(a, t["GST REFUND ORDER 2026"], link_type="GOVT", govt_kind="GST", govt_period="2026-07",
                challan_ref="ARN20260801", govt_descr="GST Refund for Exports")
    assert r_cr.status_code == 201, r_cr.text
    assert "refund" in r_cr.json()["ref"]
    assert "Government Agencies" in r_cr.json()["party"]

    # 3. Report reflects both debits and credits and net
    reg = a.get("/api/statements/govt-payments?period=FY2026-27").json()
    assert reg["total_payments"] == 20000.0
    assert reg["total_refunds"] == 15000.0
    assert reg["net_paid"] == 5000.0
    assert len(reg["rows"]) == 2
    cr_row = next(r for r in reg["rows"] if r["side"] == "REFUND")
    dr_row = next(r for r in reg["rows"] if r["side"] == "PAYMENT")
    assert cr_row["amount"] == 15000.0
    assert dr_row["amount"] == 20000.0


def test_attach_vendor_advance_without_invoice(org):
    a = org()
    _, vi = invoices(a)
    _, t = bank(a, CSV)
    vendor_id = a.get("/api/vendors").json()[0]["id"]

    # 1. Attach debit directly to vendor without invoice
    r = link(a, t["ADVANCE TO VENDOR PART"], link_type="VEND_ADV", ref_id=vendor_id)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["ref_id"] == vendor_id
    assert "Advance" in data["ref"]
    assert data["payment_id"] is not None

    # 2. Shows on Vendor Payments
    pays = a.get("/api/vendor-payments").json()
    adv_pay = next(p for p in pays if p["id"] == data["payment_id"])
    assert adv_pay["amount"] == 12000.0
    assert adv_pay["doc"] == "Advance / On Account"
    assert adv_pay["from_bank"] is True

    # 3. Deleting link deletes the payment
    assert a.delete(f"/api/statements/links/{data['id']}").status_code == 204
    pays_after = a.get("/api/vendor-payments").json()
    assert data["payment_id"] not in [p["id"] for p in pays_after]


def test_vendor_advance_direct_api(org):
    a = org()
    _, vi = invoices(a)
    vendor_id = a.get("/api/vendors").json()[0]["id"]

    # Record advance payment directly via /api/vendor-payments
    r = a.post("/api/vendor-payments", json={
        "pay_type": "PAY", "vendor_id": vendor_id, "pay_date": "2026-08-10",
        "amount": 7500.0, "mode": "NEFT", "narration": "Direct advance"
    })
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    pays = a.get("/api/vendor-payments").json()
    p = next(x for x in pays if x["id"] == pid)
    assert p["amount"] == 7500.0
    assert p["doc"] == "Advance / On Account"


def test_tds_register_monthly_breakdown(org):
    a = org()
    _, vi = invoices(a)
    # Record payment with TDS
    a.post("/api/vendor-payments", json={
        "pay_type": "PAY", "vinv_id": vi["id"], "pay_date": "2026-08-15",
        "amount": 10000.0, "tds": 1000.0, "mode": "NEFT"
    })

    reg = a.get("/api/registers/tds?period=FY2026-27").json()
    assert reg["total_tds"] >= 1000.0
    assert "by_month" in reg
    assert len(reg["by_month"]) >= 1
    m = next(x for x in reg["by_month"] if x["month"] == "2026-08")
    assert m["count"] >= 1
    assert m["tds"] >= 1000.0
    assert m["due_date"] == "2026-09-07"
    assert m["status"] in ("Due", "Overdue")
