"""Contacts, bank details, PAN, MSME, the HSN master, registers and GST reconciliation."""


def desig(api_db):
    pass


def mk_customer(c, **over):
    body = {"code": "C1", "name": "Apollo", "party_type": "B2B", "bill_addr": "MG Rd",
            "bill_city": "Bengaluru", "bill_state": "29",
            "gstins": [{"gstin": "29AAACT1234N1Z2", "is_default": True}]}
    body.update(over)
    return c.post("/api/customers", json=body)


def mk_vendor(c, **over):
    body = {"code": "V1", "name": "Redington", "party_type": "B2B", "addr": "x",
            "city": "Chennai", "state_code": "33",
            "gstins": [{"gstin": "33AAACR1234K1Z5", "is_default": True}]}
    body.update(over)
    return c.post("/api/vendors", json=body)


# ------------------------------------------------------------- contacts
def test_customer_carries_a_contact_person(org, seed_ref):
    c = org(); d = seed_ref(c)
    r = mk_customer(c, contacts=[{"first_name": "Ravi", "middle_name": "K",
        "last_name": "Iyer", "designation_id": d["designation"],
        "phone": "9840012345", "email": "ravi@x.in", "is_primary": True}])
    assert r.status_code == 201, r.text
    ct = r.json()["contacts"][0]
    assert (ct["first_name"], ct["middle_name"], ct["last_name"]) == ("Ravi", "K", "Iyer")
    assert ct["designation"] == "Director" and ct["phone"] == "9840012345"


def test_vendor_carries_the_same_contact_shape(org, seed_ref):
    c = org(); d = seed_ref(c)
    r = mk_vendor(c, contacts=[{"first_name": "Suresh", "designation_id": d["designation"],
        "phone": "9000000000"}])
    assert r.status_code == 201
    assert r.json()["contacts"][0]["designation"] == "Director"


def test_contact_needs_a_first_name(org, seed_ref):
    c = org(); seed_ref(c)
    r = mk_customer(c, contacts=[{"first_name": "  ", "phone": "1"}])
    assert r.status_code == 422


def test_unknown_designation_is_refused(org, seed_ref):
    c = org(); seed_ref(c)
    r = mk_customer(c, contacts=[{"first_name": "Ravi", "designation_id": 9999}])
    assert r.status_code == 422 and "designation" in r.text.lower()


# ------------------------------------------------------- bank, PAN, MSME
def test_bank_is_three_separate_fields(org, seed_ref):
    c = org(); seed_ref(c)
    r = mk_customer(c, bank_name="HDFC Bank", bank_ifsc="HDFC0000123",
                    bank_account="50100099112233")
    j = r.json()
    assert (j["bank_name"], j["bank_ifsc"], j["bank_account"]) == \
           ("HDFC Bank", "HDFC0000123", "50100099112233")


def test_bad_ifsc_is_refused(org, seed_ref):
    c = org(); seed_ref(c)
    r = mk_customer(c, bank_name="HDFC Bank", bank_ifsc="HDFC123", bank_account="50100099112233")
    assert r.status_code == 422 and "IFSC" in r.text


def test_bank_details_need_the_bank_name(org, seed_ref):
    c = org(); seed_ref(c)
    r = mk_customer(c, bank_ifsc="HDFC0000123", bank_account="50100099112233")
    assert r.status_code == 422 and "bank name" in r.text.lower()


def test_msme_flag_needs_a_registration_number(org, seed_ref):
    c = org(); seed_ref(c)
    assert mk_customer(c, msme_registered=True).status_code == 422
    r = mk_customer(c, msme_registered=True, msme_number="UDYAM-KA-01-0001")
    assert r.status_code == 201 and r.json()["msme_number"] == "UDYAM-KA-01-0001"


def test_pan_is_checked_for_shape(org, seed_ref):
    c = org(); seed_ref(c)
    assert mk_customer(c, pan="TOOSHORT").status_code == 422
    assert mk_customer(c, pan="AAACT1234N").status_code == 201


def test_vendor_tds_rate_needs_a_section(org, seed_ref):
    c = org(); seed_ref(c)
    assert mk_vendor(c, tds_rate=2).status_code == 422
    r = mk_vendor(c, tds_section="194C", tds_rate=2)
    assert r.status_code == 201 and r.json()["tds_section"] == "194C"


# ---------------------------------------------------------- HSN master
def test_hsn_rates_default_onto_the_material(org):
    c = org()
    c.post("/api/hsn", json={"code": "998314", "descr": "IT services", "kind": "SAC",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    r = c.post("/api/materials", json={"code": "SRV", "descr": "Consulting", "price": 5000,
        "hsn": "998314", "uom": "NOS"})
    assert r.status_code == 201, r.text
    j = r.json()
    assert (j["sgst_pct"], j["cgst_pct"], j["igst_pct"]) == (9.0, 9.0, 18.0)


def test_hsn_split_must_equal_igst(org):
    c = org()
    r = c.post("/api/hsn", json={"code": "3004", "descr": "x",
        "sgst_pct": 6, "cgst_pct": 6, "igst_pct": 18})
    assert r.status_code == 422 and "does not equal" in r.text


def test_hsn_code_is_unique_per_organisation(org):
    a = org(name="One", email="one@x.co")
    b = org(name="Two", email="two@x.co")
    body = {"code": "998314", "descr": "IT", "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18}
    assert a.post("/api/hsn", json=body).status_code == 201
    assert a.post("/api/hsn", json=body).status_code == 409
    assert b.post("/api/hsn", json=body).status_code == 201    # a different organisation


# ----------------------------------------------------------- registers
def test_the_three_registers_respond(org):
    c = org()
    for path in ("/api/registers/invoices", "/api/registers/gst", "/api/registers/tds"):
        assert c.get(path).status_code == 200


def test_templates_cover_every_requested_entity(org):
    c = org()
    keys = {t["key"] for t in c.get("/api/templates").json()}
    assert keys == {"customers", "vendors", "materials", "customer-estimates",
                    "customer-invoices", "vendor-estimates", "vendor-invoices"}


def test_template_csv_has_a_header_row(org):
    c = org()
    r = c.get("/api/templates/customers.csv")
    assert r.status_code == 200
    head = r.text.splitlines()[0].lower()
    assert "name" in head and "gstin" in head


def _month_of_trade(c, seed_ref):
    """One sale, one purchase and one TDS deduction inside August 2026."""
    seed_ref(c)
    c.post("/api/hsn", json={"code": "998314", "descr": "IT services", "kind": "SAC",
        "sgst_pct": 9, "cgst_pct": 9, "igst_pct": 18})
    m = c.post("/api/materials", json={"code": "SRV", "descr": "Consulting",
        "price": 100000, "cost": 50000, "hsn": "998314", "uom": "NOS",
        "stock_qty": 999}).json()["id"]
    cu = mk_customer(c, pan="AAACT1234N").json()["id"]
    v = mk_vendor(c, pan="AAACR1234K", tds_section="194C", tds_rate=2).json()["id"]
    c.post("/api/invoices", json={"doc_date": "2026-08-10", "customer_id": cu,
        "lines": [{"material_id": m, "qty": 1, "price": 100000}]})
    po = c.post("/api/purchase-orders", json={"doc_date": "2026-08-01", "vendor_id": v,
        "lines": [{"material_id": m, "qty": 1, "price": 50000}]}).json()["id"]
    vi = c.post("/api/vendor-invoices", json={"doc_no": "RED/1",
        "doc_date": "2026-08-05", "po_id": po}).json()["id"]
    c.post("/api/vendor-payments", json={"pay_type": "PAY", "vinv_id": vi,
        "pay_date": "2026-08-20", "amount": 57000, "tds": 1000, "mode": "NEFT"})
    return m


def test_invoice_register_carries_pan_and_gstin(org, seed_ref):
    c = org(); _month_of_trade(c, seed_ref)
    rows = c.get("/api/registers/invoices?period=2026-08").json()
    assert rows and rows[0]["pan"] == "AAACT1234N"
    assert rows[0]["gstin"] == "29AAACT1234N1Z2"


def test_tds_register_works_the_rate_back_from_what_was_paid(org, seed_ref):
    c = org(); _month_of_trade(c, seed_ref)
    reg = c.get("/api/registers/tds?period=2026-08").json()
    row = reg["rows"][0]
    assert row["tds"] == 1000.0 and row["implied_rate_pct"] == 2.0
    assert reg["total_tds"] == 1000.0


def test_gstr3b_upload_agrees_with_the_books(org, seed_ref):
    c = org(); _month_of_trade(c, seed_ref)
    c.post("/api/registers/gstr3b", json={"period": "2026-08", "out_taxable": 100000,
        "out_cgst": 9000, "out_sgst": 9000, "out_igst": 0,
        "itc_igst": 9000, "itc_cgst": 0, "itc_sgst": 0})
    cmp = c.get("/api/registers/gstr3b/compare?period=2026-08").json()
    assert all(r["agrees"] for r in cmp["rows"])


def test_gstr3b_upload_catches_a_wrong_figure(org, seed_ref):
    c = org(); _month_of_trade(c, seed_ref)
    c.post("/api/registers/gstr3b", json={"period": "2026-08", "out_taxable": 100000,
        "out_cgst": 8000, "out_sgst": 9000, "out_igst": 0,
        "itc_igst": 9000, "itc_cgst": 0, "itc_sgst": 0})
    cmp = c.get("/api/registers/gstr3b/compare?period=2026-08").json()
    bad = [r for r in cmp["rows"] if not r["agrees"]]
    assert len(bad) == 1
    assert bad[0]["field"] == "out_cgst" and bad[0]["difference"] == -1000.0
