"""Cancelling an invoice reverses GST, TDS and stock; GSTR-1 portal files; A - B."""
import io, json
from tests.test_api import mat, cust, vend


def _books(org, trading=False):
    c = org(gstin="29AABCA1234F1Z5", trading=trading)
    m = mat(c, code="MAT-1", price=1000, cost=800, stock=100)
    cid = cust(c, state="27", gstin="27AAACE1234R1Z9")
    vid = vend(c, state="29", gstin="29AAACR1234K1Z5")
    inv = c.post("/api/invoices", json={"doc_date": "2026-09-01", "customer_id": cid,
                                        "lines": [{"material_id": m, "qty": 10}]}).json()
    inv2 = c.post("/api/invoices", json={"doc_date": "2026-09-02", "customer_id": cid,
                                         "lines": [{"material_id": m, "qty": 5}]}).json()
    vi = c.post("/api/vendor-invoices", json={"doc_no": "V/1", "doc_date": "2026-09-03",
                                              "vendor_id": vid,
                                              "lines": [{"material_id": m, "qty": 20, "price": 800}]})
    assert vi.status_code == 201, vi.text
    return c, m, cid, inv, inv2


def test_cancel_reverses_gst_tds_and_stock(org):
    c, m, cid, inv, inv2 = _books(org, trading=True)
    # customer paid part, deducting TDS
    r = c.post("/api/receipts", json={"pay_type": "REC", "invoice_id": inv["id"],
                                      "pay_date": "2026-09-05", "amount": 5000, "tds": 100,
                                      "mode": "NEFT", "bank_ref": "UTR1"})
    assert r.status_code == 201, r.text
    before = c.get("/api/returns/gstr1?period=2026-09").json()["totals"]
    stock_before = [x for x in c.get("/api/materials").json() if x["id"] == m][0]["stock_qty"]
    r = c.post(f"/api/invoices/{inv['id']}/cancel", json={"reason": "Goods returned by customer"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "CANCELLED" and d["gst_reversed"]["igst"] == 1800
    assert d["tds_reversed"] == 100 and len(d["receipts_reversed"]) == 1
    # GST: the invoice is out of GSTR-1, GSTR-3B, GST register and A-B
    after = c.get("/api/returns/gstr1?period=2026-09").json()
    assert after["totals"]["taxable"] == before["taxable"] - 10000
    assert after["totals"]["igst"] == before["igst"] - 1800
    assert [x["doc_no"] for x in after["cancelled"]] == [inv["doc_no"]]
    assert c.get("/api/returns/gstr3b?period=2026-09").json()["outward"]["documents"] == 1
    reg = c.get("/api/registers/gst?period=2026-09").json()
    assert [o["doc_no"] for o in reg["outward"]] == [inv2["doc_no"]]
    # TDS / receipts: a contra entry nets the receipt and the TDS to nil
    recs = c.get("/api/receipts").json()
    rev = [p for p in recs if p["reverses_id"]]
    assert len(rev) == 1 and rev[0]["amount"] == -5000 and rev[0]["tds"] == -100
    lst = [x for x in c.get("/api/invoices").json() if x["id"] == inv["id"]][0]
    assert lst["status"] == "CANCELLED" and lst["received"] == 0 and lst["outstanding"] is None
    assert all(x["doc_no"] != inv["doc_no"] for x in c.get("/api/returns/reports/receivables").json())
    # stock comes back
    stock_after = [x for x in c.get("/api/materials").json() if x["id"] == m][0]["stock_qty"]
    assert stock_after == stock_before + 10
    # cannot cancel twice, cannot cancel a proforma, cannot receipt a cancelled invoice
    assert c.post(f"/api/invoices/{inv['id']}/cancel", json={"reason": "again"}).status_code == 409
    pro = c.post("/api/invoices", json={"doc_date": "2026-09-04", "doc_type": "PRO",
                                        "customer_id": cid, "lines": [{"material_id": m, "qty": 1}]}).json()
    assert c.post(f"/api/invoices/{pro['id']}/cancel", json={"reason": "not needed"}).status_code == 409
    # document number still on file, counted as cancelled in table 13
    docs = c.get("/api/returns/gstr1/docs.csv?period=2026-09").text
    assert docs.strip().endswith(",1")
    # the register still lists it, marked cancelled
    row = [x for x in c.get("/api/registers/invoices").json() if x["doc_no"] == inv["doc_no"]][0]
    assert row["status"] == "CANCELLED" and row["cancel_reason"] == "Goods returned by customer"


def test_cancelled_invoice_prints_with_watermark_and_any_invoice_prints_as_proforma(org):
    import pdfplumber
    c, m, cid, inv, inv2 = _books(org)
    c.post(f"/api/invoices/{inv['id']}/cancel", json={"reason": "duplicate"})
    r = c.get(f"/api/print/invoices/{inv['id']}.pdf")
    assert r.status_code == 200
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = pdf.pages[0].extract_text()
    assert "Cancelled" in text and "duplicate" in text
    r = c.get(f"/api/print/invoices/{inv2['id']}.pdf?as=PRO")
    assert r.status_code == 200 and "proforma" in r.headers["content-disposition"]
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = pdf.pages[0].extract_text()
    assert "PROFORMA" in text and inv2["doc_no"] in text
    assert c.get(f"/api/print/invoices/{inv2['id']}.pdf?as=XX").status_code == 422


def test_gstr1_portal_json_and_excel(org):
    c, m, cid, inv, inv2 = _books(org)
    c.post(f"/api/invoices/{inv2['id']}/cancel", json={"reason": "wrong rate"})
    r = c.get("/api/returns/gstr1/portal.json?period=2026-09")
    assert r.status_code == 200 and "GSTR1_092026.json" in r.headers["content-disposition"]
    d = json.loads(r.text)
    assert d["gstin"] == "29AABCA1234F1Z5" and d["fp"] == "092026"
    assert d["b2b"][0]["ctin"] == "27AAACE1234R1Z9"
    i = d["b2b"][0]["inv"][0]
    assert i["inum"] == inv["doc_no"] and i["idt"] == "01-09-2026" and i["val"] == 11800
    assert i["itms"][0]["itm_det"] == {"rt": 18.0, "txval": 10000.0, "iamt": 1800.0, "csamt": 0}
    assert d["hsn"]["data"][0]["hsn_sc"] == "998314" and d["hsn"]["data"][0]["txval"] == 10000
    dd = d["doc_issue"]["doc_det"][0]["docs"][0]
    assert dd["totnum"] == 2 and dd["cancel"] == 1 and dd["net_issue"] == 1
    r = c.get("/api/returns/gstr1/portal.xlsx?period=2026-09")
    assert r.status_code == 200
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["b2b", "b2cl", "b2cs", "hsn", "docs"]
    rows = list(wb["b2b"].iter_rows(values_only=True))
    assert rows[0][0] == "GSTIN/UIN of Recipient" and rows[1][2] == inv["doc_no"] and rows[1][11] == 10000
    assert list(wb["docs"].iter_rows(values_only=True))[1][4] == 1


def test_gstr3b_json_upload_and_a_minus_b(org):
    c, m, cid, inv, inv2 = _books(org)
    # before anything is uploaded B falls back to the books and agrees
    ab = c.get("/api/returns/reconciliation/ab?period=2026-09").json()
    assert ab["b_source"] == "books" and ab["all_agree"]
    # upload a portal-style 3B JSON that under-reports outward IGST by 500
    portal = {"gstin": "29AABCA1234F1Z5", "ret_period": "092026",
              "sup_details": {"osup_det": {"txval": 15000, "iamt": 2200, "camt": 0, "samt": 0, "csamt": 0}},
              "itc_elg": {"itc_avl": [{"ty": "OTH", "iamt": 0, "camt": 1440, "samt": 1440, "csamt": 0}],
                          "itc_net": {"iamt": 0, "camt": 1440, "samt": 1440, "csamt": 0}}}
    r = c.post("/api/registers/gstr3b/upload-json?period=2026-09",
               files={"file": ("gstr3b.json", json.dumps(portal).encode(), "application/json")})
    assert r.status_code == 200, r.text
    assert r.json()["filed"]["out_igst"] == 2200 and r.json()["read_from"]["portal_period"] == "092026"
    ab = c.get("/api/returns/reconciliation/ab?period=2026-09").json()
    assert ab["b_source"] == "uploaded" and not ab["all_agree"]
    row = [x for x in ab["rows"] if x["head"] == "Outward IGST"][0]
    assert row["a"] == 2700 and row["b"] == 2200 and row["a_minus_b"] == 500
    assert all(x["agrees"] for x in ab["rows"] if x["section"] == "Input credit")
    assert c.post("/api/registers/gstr3b/upload-json?period=2026-09",
                  files={"file": ("x.json", b"{}", "application/json")}).status_code == 422
