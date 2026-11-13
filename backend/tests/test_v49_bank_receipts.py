"""v4.9: attaching a customer invoice to a bank credit records the receipt on
Customer Payments, so the invoice shows as paid; removing the attachment (or
the statement or account) takes the receipt away again."""
from tests.test_v42_bank_links import bank, invoices
from tests.test_v48_bank_credits_tds import CSV, link

# invoices() makes a customer invoice of 14,750 (12,500 + 18% IGST).
CSV_UPI = (b"Date,Narration,Withdrawal,Deposit,Balance\n"
           b"03/08/2026,UPI/CR/CUSTOMER FULL,,14750.00,114750.00\n")


def invoice_row(c, iid):
    return [v for v in c.get("/api/invoices").json() if v["id"] == iid][0]


def test_attaching_an_invoice_posts_the_receipt_and_marks_it_paid(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV_UPI)
    assert invoice_row(a, inv["id"])["outstanding"] == 14750
    r = link(a, t["UPI/CR/CUSTOMER FULL"], link_type="CUST_INV", ref_id=inv["id"])
    assert r.status_code == 201, r.text
    v = invoice_row(a, inv["id"])
    assert v["received"] == 14750 and v["outstanding"] == 0
    rec = a.get("/api/receipts").json()
    assert len(rec) == 1
    p = rec[0]
    assert (p["doc"], p["amount"], p["mode"], str(p["pay_date"])) == (
        inv["doc_no"], 14750, "UPI", "2026-08-03")
    assert p["from_bank"] is True and p["bank_acct"] == "HDFC Current"
    # the receivables list no longer carries it
    assert all(x.get("doc_no") != inv["doc_no"] for x in a.get("/api/receivables").json()
               if isinstance(x, dict))


def test_part_payment_then_final_payment_with_tds(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    link(a, t["NEFT CR CUSTOMER PART 1"], link_type="CUST_INV", ref_id=inv["id"])
    v = invoice_row(a, inv["id"])
    assert (v["received"], v["outstanding"]) == (6000, 8750)          # part paid
    link(a, t["NEFT CR CUSTOMER PART 2"], link_type="CUST_INV", ref_id=inv["id"],
         amount=7500, tds=1250)
    v = invoice_row(a, inv["id"])
    assert v["outstanding"] == 0                                      # paid
    rec = sorted(a.get("/api/receipts").json(), key=lambda p: p["amount"])
    assert [(p["amount"], p["tds"]) for p in rec] == [(6000, 0), (7500, 1250)]
    # TDS is counted once in the register, though it sits on the receipt and the link
    reg = a.get("/api/registers/tds").json()
    assert reg["customer_total_tds"] == 1250 and len(reg["customers"]) == 1
    assert reg["customers"][0]["source"] == "Bank statement"
    assert a.get("/api/registers/tds-report").json()["customers"]["total"] == 1250


def test_tds_booked_later_updates_the_receipt(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    link(a, t["NEFT CR CUSTOMER PART 1"], link_type="CUST_INV", ref_id=inv["id"])
    l2 = link(a, t["NEFT CR CUSTOMER PART 2"], link_type="CUST_INV", ref_id=inv["id"]).json()
    assert invoice_row(a, inv["id"])["outstanding"] == 1250
    assert l2["invoice_open"] == 1250
    r = a.put(f"/api/statements/links/{l2['id']}/tds", json={})
    assert r.status_code == 200 and r.json()["tds"] == 1250
    assert invoice_row(a, inv["id"])["outstanding"] == 0
    assert a.get("/api/registers/tds").json()["customer_total_tds"] == 1250


def test_removing_the_attachment_removes_the_receipt(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV_UPI)
    l = link(a, t["UPI/CR/CUSTOMER FULL"], link_type="CUST_INV", ref_id=inv["id"]).json()
    assert a.delete(f"/api/statements/links/{l['id']}").status_code == 204
    assert a.get("/api/receipts").json() == []
    assert invoice_row(a, inv["id"])["outstanding"] == 14750


def test_a_bank_receipt_cannot_be_deleted_from_customer_payments(org):
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV_UPI)
    link(a, t["UPI/CR/CUSTOMER FULL"], link_type="CUST_INV", ref_id=inv["id"])
    pid = a.get("/api/receipts").json()[0]["id"]
    r = a.delete(f"/api/payments/{pid}")
    assert r.status_code == 409 and "Bank Statements" in r.json()["detail"]
    assert invoice_row(a, inv["id"])["outstanding"] == 0


def test_receipts_entered_by_hand_count_against_what_can_be_attached(org):
    a = org()
    inv, _ = invoices(a)
    a.post("/api/receipts", json={"pay_type": "REC", "pay_date": "2026-08-01",
                                  "invoice_id": inv["id"], "amount": 10000})
    _, t = bank(a, CSV)
    att = a.get(f"/api/statements/txns/{t['NEFT CR CUSTOMER PART 2']['id']}/attachables").json()
    row = att["customer_invoices"][0]
    assert row["open"] == 4750 and row["receipts"] == 10000
    r = link(a, t["NEFT CR CUSTOMER PART 2"], link_type="CUST_INV", ref_id=inv["id"])
    assert r.status_code == 201 and r.json()["amount"] == 4750      # capped at what is open
    assert invoice_row(a, inv["id"])["outstanding"] == 0
    # now fully paid, it is not offered or accepted again
    att = a.get(f"/api/statements/txns/{t['NEFT CR CUSTOMER PART 1']['id']}/attachables").json()
    assert att["customer_invoices"] == []
    assert link(a, t["NEFT CR CUSTOMER PART 1"], link_type="CUST_INV",
                ref_id=inv["id"]).status_code == 409


def test_older_attachments_without_a_receipt_are_not_settled_twice(org):
    """An attachment made before v4.9 has no receipt. It still counts against
    the invoice, so the same money cannot be attached again."""
    a = org()
    inv, _ = invoices(a)
    _, t = bank(a, CSV)
    from app.db import SessionLocal
    from app import models as M
    db = SessionLocal()
    tx = db.get(M.StmtTxn, t["NEFT CR CUSTOMER PART 1"]["id"])
    db.add(M.StmtTxnLink(tenant_id=tx.tenant_id, txn_id=tx.id, link_type="CUST_INV",
                         invoice_id=inv["id"], amount=6000, tds=0))
    db.commit(); db.close()
    att = a.get(f"/api/statements/txns/{t['NEFT CR CUSTOMER PART 2']['id']}/attachables").json()
    assert att["customer_invoices"][0]["open"] == 8750
    # booking TDS on the older attachment gives it its receipt
    old = a.get(f"/api/statements/accounts/{tx_account(a)}/txns?period=2026-08").json()
    lid = [x for x in old if x["descr"] == "NEFT CR CUSTOMER PART 1"][0]["links"][0]["id"]
    link(a, t["NEFT CR CUSTOMER PART 2"], link_type="CUST_INV", ref_id=inv["id"], amount=7500)
    assert a.put(f"/api/statements/links/{lid}/tds", json={}).json()["tds"] == 1250
    assert invoice_row(a, inv["id"])["outstanding"] == 0
    assert len(a.get("/api/receipts").json()) == 2


def tx_account(c):
    return c.get("/api/statements/accounts").json()[0]["id"]


def test_deleting_the_account_removes_its_receipts(org):
    a = org()
    inv, _ = invoices(a)
    aid, t = bank(a, CSV_UPI)
    link(a, t["UPI/CR/CUSTOMER FULL"], link_type="CUST_INV", ref_id=inv["id"])
    imp = a.get(f"/api/statements/accounts/{aid}/impact").json()
    assert imp["recorded_payments"] == 1
    r = a.delete(f"/api/statements/accounts/{aid}?confirm=HDFC%20Current")
    assert r.status_code == 200, r.text
    assert r.json()["payments_removed"] == 1
    assert a.get("/api/receipts").json() == []
    assert invoice_row(a, inv["id"])["outstanding"] == 14750


def test_deleting_the_upload_removes_its_receipts(org):
    b = org()
    inv2, _ = invoices(b)
    aid2, t2 = bank(b, CSV_UPI)
    link(b, t2["UPI/CR/CUSTOMER FULL"], link_type="CUST_INV", ref_id=inv2["id"])
    up = b.get(f"/api/statements/accounts/{aid2}/uploads").json()[0]
    r = b.delete(f"/api/statements/uploads/{up['id']}?force=true")
    assert r.status_code == 200, r.text
    assert b.get("/api/receipts").json() == []
    assert invoice_row(b, inv2["id"])["outstanding"] == 14750
