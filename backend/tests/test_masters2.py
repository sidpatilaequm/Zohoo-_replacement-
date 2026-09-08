"""Contacts, bank, PAN, MSME, HSN master, registers, templates and GSTR-3B."""
import io


def csvfile(text):
    return {"file": ("f.csv", io.BytesIO(text.encode()), "text/csv")}


def hsn(c, code="30049099", ig=12):
    return c.post("/api/hsn", json={"code": code, "descr": "Medicaments", "kind": "HSN",
        "sgst_pct": ig / 2, "cgst_pct": ig / 2, "igst_pct": ig}).json()


# ------------------------------------------------------ party details
def test_customer_carries_pan_msme_bank_and_a_contact(org):
    c = org()
    # signup seeds the shared designation list, so pick from it
    d = [x for x in c.get("/api/designations").json()
         if x["name"] == "Accounts Manager"][0]
    r = c.post("/api/customers", json={"code": "C1", "name": "Acme", "party_type": "B2B",
        "bill_addr": "St", "bill_city": "C", "bill_state": "29",
        "pan": "AAPCA3382B", "msme_registered": True, "msme_number": "UDYAM-KR-03-1",
        "bank_name": "State Bank of India", "bank_ifsc": "SBIN0040807",
        "bank_account": "38600386525",
        "gstins": [{"gstin": "29AAACT1234N1Z2", "is_default": True}],
        "contacts": [{"first_name": "Anita", "middle_name": "K", "last_name": "Rao",
                      "designation_id": d["id"], "phone": "+91 98450 12345",
                      "email": "anita@acme.co", "is_primary": True}]})
    assert r.status_code == 201, r.text
    got = c.get("/api/customers").json()[0]
    assert got["pan"] == "AAPCA3382B" and got["msme_registered"] is True
    assert got["bank_ifsc"] == "SBIN0040807"
    assert got["contacts"][0]["designation"] == "Accounts Manager"
    assert got["contacts"][0]["first_name"] == "Anita"


def test_signup_seeds_the_shared_designation_and_bank_lists(org):
    c = org()
    names = [d["name"] for d in c.get("/api/designations").json()]
    assert "Accounts Manager" in names and "Director" in names
    banks = [b["name"] for b in c.get("/api/banks").json()]
    assert "State Bank of India" in banks and len(banks) > 15


def test_bad_ifsc_is_refused(org):
    c = org()
    r = c.post("/api/vendors", json={"code": "V1", "name": "V", "party_type": "B2B",
        "addr": "a", "city": "b", "state_code": "33",
        "bank_name": "HDFC Bank", "bank_ifsc": "HDFC123", "bank_account": "1234567",
        "gstins": [{"gstin": "33AAACR1234K1Z5"}]})
    assert r.status_code == 422 and "not a valid IFSC" in r.text


def test_msme_flag_needs_a_number(org):
    c = org()
    r = c.post("/api/vendors", json={"code": "V1", "name": "V", "party_type": "B2B",
        "addr": "a", "city": "b", "state_code": "33", "msme_registered": True,
        "gstins": [{"gstin": "33AAACR1234K1Z5"}]})
    assert r.status_code == 422 and "Udyam" in r.text


# ------------------------------------------------------------ HSN master
def test_hsn_rates_default_onto_a_material(org):
    c = org()
    hsn(c, "30049099", 12)
    r = c.post("/api/materials", json={"code": "M1", "descr": "Tablet", "price": 148,
        "hsn": "30049099", "uom": "NOS", "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    assert r.status_code == 201
    m = c.get("/api/materials").json()[0]
    assert m["igst_pct"] == 12 and m["sgst_pct"] == 6      # the HSN won, not the 18 sent


def test_material_can_override_the_hsn_rate(org):
    c = org()
    hsn(c, "30049099", 12)
    c.post("/api/materials", json={"code": "M1", "descr": "Tablet", "price": 148,
        "hsn": "30049099", "uom": "NOS", "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18,
        "use_hsn_rates": False})
    assert c.get("/api/materials").json()[0]["igst_pct"] == 18


def test_hsn_split_must_reconcile(org):
    c = org()
    r = c.post("/api/hsn", json={"code": "9983", "descr": "Services", "kind": "SAC",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 20})
    assert r.status_code == 422 and "does not equal" in r.text


def test_hsn_in_use_cannot_be_deleted(org):
    c = org()
    h = hsn(c)
    c.post("/api/materials", json={"code": "M1", "descr": "x", "price": 1,
        "hsn": "30049099", "uom": "NOS", "sgst_pct": 6, "cgst_pct": 6, "igst_pct": 12})
    assert c.delete(f"/api/hsn/{h['id']}").status_code == 409


def test_attributes_readable_without_the_attrs_permission(api, org):
    """The material screen needs the definitions; a Sales user has no attrs menu."""
    a = org(name="One", email="admin@x.co")
    a.post("/api/attributes", json={"code": "BRAND", "name": "Brand",
        "attr_type": "LIST", "values": ["Abbott"]})
    gid = [g for g in a.get("/api/groups").json() if g["name"] == "Sales"][0]["id"]
    a.post("/api/users", json={"name": "S", "email": "s@x.co",
        "password": "correct horse", "group_id": gid})
    tok = api.post("/api/auth/signin", json={"email": "s@x.co",
        "password": "correct horse"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}", "X-Tenant-Id": str(a.tid)}
    assert api.get("/api/attributes", headers=h).status_code == 200
    assert api.get("/api/hsn", headers=h).status_code == 200


# ------------------------------------------------------------ registers
def _seed_docs(c):
    hsn(c, "30049099", 12)
    m = c.post("/api/materials", json={"code": "M1", "descr": "Tablet", "price": 148,
        "cost": 112, "hsn": "30049099", "stock_qty": 1000, "uom": "NOS",
        "sgst_pct": 6, "cgst_pct": 6, "igst_pct": 12}).json()["id"]
    cu = c.post("/api/customers", json={"code": "C1", "name": "Apollo", "party_type": "B2B",
        "bill_addr": "a", "bill_city": "b", "bill_state": "29", "pan": "AAACA1111A",
        "gstins": [{"gstin": "29AAACT1234N1Z2", "is_default": True}]}).json()["id"]
    v = c.post("/api/vendors", json={"code": "V1", "name": "Redington", "party_type": "B2B",
        "addr": "a", "city": "b", "state_code": "33", "pan": "AAACR2222B",
        "msme_registered": True, "msme_number": "UDYAM-TN-1",
        "gstins": [{"gstin": "33AAACR1234K1Z5", "is_default": True}]}).json()["id"]
    inv = c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 100}]}).json()
    po = c.post("/api/purchase-orders", json={"doc_date": "2026-08-01", "vendor_id": v,
        "lines": [{"material_id": m, "qty": 200, "price": 112}]}).json()["id"]
    vi = c.post("/api/vendor-invoices", json={"doc_no": "SUP/1", "doc_date": "2026-08-05",
        "po_id": po}).json()
    c.post("/api/vendor-payments", json={"pay_type": "PAY", "pay_date": "2026-08-20",
        "vinv_id": vi["id"], "amount": 24000, "tds": 224, "mode": "NEFT",
        "bank_ref": "UTR9"})
    return m, cu, v, inv, vi


def test_invoice_register(org):
    c = org(); _seed_docs(c)
    r = c.get("/api/registers/invoices", params={"period": "2026-08"}).json()
    assert len(r) == 1 and r[0]["taxable"] == 14800.0
    assert r[0]["supply"] == "Intra-state" and r[0]["pan"] == "AAACA1111A"


def test_gst_register_nets_outward_against_credit(org):
    c = org(); _seed_docs(c)
    d = c.get("/api/registers/gst", params={"period": "2026-08"}).json()
    assert d["totals"]["outward"]["cgst"] == 888.0        # 14,800 at 6%
    assert d["totals"]["input_credit"]["igst"] == 2688.0  # 22,400 at 12%, inter-state
    assert d["totals"]["net_payable"]["cgst"] == 888.0


def test_tds_register_shows_the_deduction_and_flags_missing_pan(org):
    c = org(); _seed_docs(c)
    d = c.get("/api/registers/tds", params={"period": "2026-08"}).json()
    assert d["total_tds"] == 224.0
    row = d["rows"][0]
    assert row["vendor"] == "Redington" and row["pan"] == "AAACR2222B"
    assert row["msme"] is True and row["gross"] == 24224.0
    assert d["vendors_without_pan"] == []


def test_register_csv_downloads(org):
    c = org(); _seed_docs(c)
    for which in ("invoices", "gst", "tds"):
        r = c.get(f"/api/registers/{which}.csv", params={"period": "2026-08"})
        assert r.status_code == 200 and len(r.text.splitlines()) >= 2


# --------------------------------------------------------- GSTR-3B
def test_uploaded_3b_that_agrees_reconciles(org):
    c = org(); _seed_docs(c)
    r = c.post("/api/registers/gstr3b", json={"period": "2026-08",
        "out_taxable": 14800, "out_igst": 0, "out_cgst": 888, "out_sgst": 888,
        "itc_igst": 2688, "itc_cgst": 0, "itc_sgst": 0}).json()
    assert r["all_agree"] is True


def test_uploaded_3b_that_differs_is_reported_head_by_head(org):
    c = org(); _seed_docs(c)
    r = c.post("/api/registers/gstr3b", json={"period": "2026-08",
        "out_taxable": 15000, "out_cgst": 888, "out_sgst": 888, "itc_igst": 2688}).json()
    assert r["all_agree"] is False
    bad = [x for x in r["rows"] if not x["agrees"]]
    assert len(bad) == 1 and bad[0]["field"] == "out_taxable"
    assert bad[0]["difference"] == 200.0


def test_3b_csv_upload(org):
    c = org(); _seed_docs(c)
    body = ("field,value\nout_taxable,14800\nout_cgst,888\nout_sgst,888\nitc_igst,2688\n"
            "something_else,1\n")
    r = c.api.post("/api/registers/gstr3b/upload-csv?period=2026-08",
                   headers=c._h(), files=csvfile(body))
    assert r.status_code == 200
    d = r.json()
    assert d["all_agree"] is True and d["ignored_rows"] == ["something_else"]


def test_3b_csv_rejects_a_file_with_nothing_recognisable(org):
    c = org()
    r = c.api.post("/api/registers/gstr3b/upload-csv?period=2026-08",
                   headers=c._h(), files=csvfile("a,b\nc,1\n"))
    assert r.status_code == 422 and "No recognised rows" in r.text


# --------------------------------------------------------- templates
def test_every_template_downloads_with_a_worked_example(org):
    c = org()
    keys = [t["key"] for t in c.get("/api/templates").json()]
    assert set(keys) == {"customers", "vendors", "materials", "customer-estimates",
                         "customer-invoices", "vendor-estimates", "vendor-invoices"}
    for k in keys:
        r = c.get(f"/api/templates/{k}.csv")
        assert r.status_code == 200
        lines = r.text.strip().splitlines()
        assert len(lines) == 2                      # heading row plus the example


def test_customer_import_round_trip(org):
    c = org()
    tpl = c.get("/api/templates/customers.csv").text
    r = c.api.post("/api/templates/customers/import", headers=c._h(), files=csvfile(tpl))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["added"] == 1 and d["errors"] == []
    got = c.get("/api/customers").json()[0]
    assert got["code"] == "C900" and got["msme_registered"] is True
    assert got["contacts"][0]["designation"] == "Accounts Manager"
    assert got["bank_ifsc"] == "SBIN0040807"


def test_import_is_all_or_nothing_when_a_row_fails(org):
    c = org()
    good = c.get("/api/templates/materials.csv").text
    bad = good + "BAD-1,Broken,notanumber,0,3004,0,NOS,No,0,6,6,12\n"
    r = c.api.post("/api/templates/materials/import", headers=c._h(), files=csvfile(bad)).json()
    assert r["errors"] and r["added"] == 0 and r["committed"] is False
    assert c.get("/api/materials").json() == []      # the good row was rolled back too


def test_dry_run_writes_nothing(org):
    c = org()
    tpl = c.get("/api/templates/materials.csv").text
    r = c.api.post("/api/templates/materials/import?dry_run=true",
                   headers=c._h(), files=csvfile(tpl)).json()
    assert r["would_add"] == 1 and r["committed"] is False
    assert c.get("/api/materials").json() == []


def test_missing_columns_are_named(org):
    c = org()
    r = c.api.post("/api/templates/materials/import", headers=c._h(),
                   files=csvfile("Material Code,Description\nX,Y\n"))
    assert r.status_code == 422 and "Selling Price" in r.text
