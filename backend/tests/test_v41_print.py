"""v4.1: what the tax invoice print-out shows for the item description, the
payment line and the place of supply."""
import io
import pdfplumber
from tests.test_api import cust


def mat(c, code, descr, price):
    r = c.post("/api/materials", json={"code": code, "descr": descr, "price": price, "cost": price,
        "hsn": "998314", "stock_qty": 1000, "uom": "LIC", "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _text(c, iid):
    r = c.get(f"/api/print/invoices/{iid}.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF", r.text
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def _item_cell(c, iid):
    """The Item & Description cell as one string. pdfplumber reads a wrapped
    cell as several page lines with the numeric columns spliced into the
    first, so the words are gathered back from that region."""
    t = _text(c, iid)
    region = t[t.find("% Amt"):t.find("Total In Words")]
    words = [w for w in region.replace("\n", " ").split()
             if not (w.replace(",", "").replace(".", "").replace("%", "").isdigit())]
    return " ".join(words)


def _invoice(c, m, cid, **line):
    r = c.post("/api/invoices", json={"doc_date": "2026-09-09", "customer_id": cid,
                                      "lines": [{"material_id": m, "qty": 10, **line}]})
    assert r.status_code == 201, r.text
    return r.json()


def test_item_prints_description_and_description_2_together(org):
    c = org(gstin="29AABCA1234F1Z5")
    m = mat(c, code="M002", descr="Microsoft office Basic plan", price=1400)
    cid = cust(c, state="33", gstin="33AAACE1234R1Z9")
    inv = _invoice(c, m, cid, descr2="Annual subscription October to September")
    # the two descriptions are one line in the Item & Description column
    assert "Microsoft office Basic plan Annual subscription October to September" in _item_cell(c, inv["id"])
    # and a line without a second description prints the master description alone
    inv2 = _invoice(c, m, cid)
    assert "Microsoft office Basic plan M002" in _item_cell(c, inv2["id"])


def test_new_invoice_prints_nil_payment_and_full_balance(org):
    c = org(gstin="29AABCA1234F1Z5")
    m = mat(c, code="M002", descr="Microsoft office Basic plan", price=1400)
    cid = cust(c, state="33", gstin="33AAACE1234R1Z9")
    inv = _invoice(c, m, cid)
    t = _text(c, inv["id"])
    assert "Total Rs. 16,520.00" in t
    assert "Payment Made (-) 0.00" in t
    assert "Balance Due Rs. 16,520.00" in t
    # the payment line only moves once a receipt is recorded against the invoice
    r = c.post("/api/receipts", json={"pay_type": "REC", "invoice_id": inv["id"],
                                      "pay_date": "2026-09-10", "amount": 6520, "mode": "NEFT"})
    assert r.status_code == 201, r.text
    t = _text(c, inv["id"])
    assert "Payment Made (-) 6,520.00" in t and "Balance Due Rs. 10,000.00" in t


def test_place_of_supply_follows_the_customer_not_the_supplier(org):
    """Aequm is in Karnataka (29). A Tamil Nadu customer is an inter-state supply:
    the place of supply printed is the customer's state and IGST is charged.
    Only when the customer is also in Karnataka does it read Karnataka, and
    then CGST and SGST replace IGST."""
    c = org(gstin="29AABCA1234F1Z5")
    m = mat(c, code="M002", descr="Microsoft office Basic plan", price=1400)
    tn = cust(c, state="33", gstin="33AAACE1234R1Z9")
    ka = cust(c, code="C002", state="29", gstin="29AAACE1234R1Z9")
    t = _text(c, _invoice(c, m, tn)["id"])
    assert "Place Of Supply : Tamil Nadu (33)" in t and "IGST" in t
    t = _text(c, _invoice(c, m, ka)["id"])
    assert "Place Of Supply : Karnataka (29)" in t and "CGST" in t and "SGST" in t


def test_import_carries_description_2_and_old_files_still_load(org):
    c = org(gstin="29AABCA1234F1Z5")
    mat(c, code="M002", descr="Microsoft office Basic plan", price=1400)
    cust(c, code="C900", state="33", gstin="33AAACE1234R1Z9")
    hdr = ("Invoice Number,Invoice Date,Due Date,Customer Code,Recipient GSTIN,Place of Supply,"
           "PO Number,PO Date,Reverse Charge,Material Code,Description 2,Quantity,Unit Price\n")
    row = "INV/900,2026-09-09,,C900,33AAACE1234R1Z9,33,,,N,M002,Annual subscription,10,1400\n"
    r = c.post("/api/templates/customer-invoices/import",
               files={"file": ("inv.csv", hdr + row, "text/csv")})
    assert r.status_code == 200, r.text
    iid = next(i["id"] for i in c.get("/api/invoices").json() if i["doc_no"] == "INV/900")
    assert "Microsoft office Basic plan Annual subscription" in _item_cell(c, iid)
    # a file made from the v4 template, without the new column, is still accepted
    old = ("Invoice Number,Invoice Date,Due Date,Customer Code,Recipient GSTIN,Place of Supply,"
           "PO Number,PO Date,Reverse Charge,Material Code,Quantity,Unit Price\n"
           "INV/901,2026-09-09,,C900,33AAACE1234R1Z9,33,,,N,M002,10,1400\n")
    r = c.post("/api/templates/customer-invoices/import",
               files={"file": ("inv.csv", old, "text/csv")})
    assert r.status_code == 200, r.text
