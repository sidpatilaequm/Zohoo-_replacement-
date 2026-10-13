"""v4.5 — directors' signature images printed on tax and proforma invoices."""
import base64, io
import pytest
from PIL import Image, ImageDraw
from .test_api import mat, cust


def _sig(paper=(238, 234, 224), ink=(30, 45, 140), fmt="JPEG", size=(1200, 600)):
    """A signature photographed on off-white paper."""
    im = Image.new("RGB", size, paper)
    d = ImageDraw.Draw(im)
    d.line([(300, 380), (500, 200), (650, 400), (820, 210), (950, 390)], fill=ink, width=12)
    b = io.BytesIO(); im.save(b, fmt)
    mime = "jpeg" if fmt == "JPEG" else fmt.lower()
    return f"data:image/{mime};base64," + base64.b64encode(b.getvalue()).decode()


def _png(uri):
    return Image.open(io.BytesIO(base64.b64decode(uri.split("base64,")[1])))


def _add(a, name, on=False, **kw):
    r = a.post("/api/signatories", json={"name": name, "designation": "Director",
                                         "image": kw.pop("image", _sig()), "on_invoices": on, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _images_in_pdf(raw):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        pg = pdf.pages[0]
        return pg.images, " ".join((pg.extract_text() or "").split())


def _books(org):
    a = org(name="Aequm India Private Limited")
    m, c = mat(a), cust(a)
    tax = a.post("/api/invoices", json={"doc_date": "2026-10-01", "customer_id": c,
                                        "lines": [{"material_id": m, "qty": 1}]}).json()
    pro = a.post("/api/invoices", json={"doc_date": "2026-10-01", "doc_type": "PRO",
                                        "customer_id": c, "lines": [{"material_id": m, "qty": 1}]}).json()
    return a, tax, pro


# ------------------------------------------------------------ the image
def test_upload_makes_the_paper_transparent_and_trims_to_the_ink(org):
    a = org()
    s = _add(a, "Alok Sharma")
    im = _png(s["image"])
    assert im.mode == "RGBA" and im.format == "PNG"
    assert im.getpixel((0, 0))[3] == 0                         # paper is gone
    assert im.width < 900 and im.height < 300                   # trimmed and scaled
    opaque = [p for p in im.getdata() if p[3] > 200]
    assert opaque and all(p[2] > p[0] for p in opaque[:50])     # ink keeps its blue
    assert s["uploaded_by"] == "Admin"


def test_a_transparent_png_keeps_its_own_transparency(org):
    a = org()
    im = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).line([(50, 150), (350, 50)], fill=(0, 0, 0, 255), width=8)
    b = io.BytesIO(); im.save(b, "PNG")
    s = _add(a, "Priya Rao", image="data:image/png;base64," + base64.b64encode(b.getvalue()).decode())
    assert _png(s["image"]).getpixel((0, 0))[3] == 0


@pytest.mark.parametrize("image,msg", [
    ("not an image", "PNG, JPEG or WebP"),
    ("data:image/png;base64,AAAA", "not an image that can be read"),
    ("data:image/png;base64,%%%", "could not be read"),
    (None, "Upload the signature image"),
])
def test_bad_images_are_refused(org, image, msg):
    a = org()
    r = a.post("/api/signatories", json={"name": "X", "image": image})
    assert r.status_code == 422 and msg in r.text


def test_a_blank_page_is_refused(org):
    a = org()
    r = a.post("/api/signatories", json={"name": "X", "image": _sig(ink=(238, 234, 224))})
    assert r.status_code == 422 and "No signature could be found" in r.text


# ------------------------------------------------------------ who signs
def test_one_director_or_both_but_never_three(org):
    a = org()
    s1 = _add(a, "Alok Sharma", on=True)
    s2 = _add(a, "Priya Rao", on=True)
    r = a.post("/api/signatories", json={"name": "Third", "image": _sig(), "on_invoices": True})
    assert r.status_code == 409 and "At most two" in r.text
    s3 = _add(a, "Third")                                       # can be kept, not printed
    r = a.put(f"/api/signatories/{s3['id']}", json={"name": "Third", "on_invoices": True})
    assert r.status_code == 409
    a.put(f"/api/signatories/{s2['id']}", json={"name": "Priya Rao", "on_invoices": False})
    r = a.put(f"/api/signatories/{s3['id']}", json={"name": "Third", "on_invoices": True})
    assert r.status_code == 200
    # editing a printing signatory's name does not trip the limit
    r = a.put(f"/api/signatories/{s1['id']}", json={"name": "Alok K Sharma", "on_invoices": True})
    assert r.status_code == 200 and r.json()["name"] == "Alok K Sharma"


def test_replacing_the_image_keeps_the_signatory(org):
    a = org()
    s = _add(a, "Alok Sharma")
    r = a.put(f"/api/signatories/{s['id']}", json={"name": "Alok Sharma",
              "image": _sig(ink=(10, 10, 10), size=(800, 400))})
    assert r.status_code == 200 and r.json()["image"] != s["image"]
    assert a.delete(f"/api/signatories/{s['id']}").status_code == 204
    assert a.get("/api/signatories").json()["signatories"] == []


# ------------------------------------------------------------ the print-out
def test_invoices_carry_the_ticked_signatures(org):
    a, tax, pro = _books(org)
    raw = a.get(f"/api/print/invoices/{tax['id']}.pdf").content
    imgs, text = _images_in_pdf(raw)
    assert "Authorized Signature" in text and "Alok" not in text      # none yet

    _add(a, "Alok Sharma", on=True)
    _add(a, "Priya Rao", on=False)
    for d in (tax, pro):
        imgs1, text = _images_in_pdf(a.get(f"/api/print/invoices/{d['id']}.pdf").content)
        assert "For Aequm India Private Limited" in text and "Alok Sharma" in text
        assert "Priya Rao" not in text and "Authorized Signature" in text
        assert len(imgs1) == len(imgs) + 1

    s2 = a.get("/api/signatories").json()["signatories"][1]
    a.put(f"/api/signatories/{s2['id']}", json={"name": "Priya Rao", "on_invoices": True})
    imgs2, text = _images_in_pdf(a.get(f"/api/print/invoices/{tax['id']}.pdf").content)
    assert "Alok Sharma" in text and "Priya Rao" in text and "Authorized Signatories" in text
    assert len(imgs2) == len(imgs) + 2


def test_signatures_can_be_kept_off_proformas_or_tax_invoices(org):
    a, tax, pro = _books(org)
    _add(a, "Alok Sharma", on=True)
    r = a.put("/api/signatories/settings", json={"sig_on_tax": True, "sig_on_pro": False})
    assert r.status_code == 200
    assert "Alok Sharma" in _images_in_pdf(a.get(f"/api/print/invoices/{tax['id']}.pdf").content)[1]
    assert "Alok Sharma" not in _images_in_pdf(a.get(f"/api/print/invoices/{pro['id']}.pdf").content)[1]
    a.put("/api/signatories/settings", json={"sig_on_tax": False, "sig_on_pro": True})
    assert "Alok Sharma" not in _images_in_pdf(a.get(f"/api/print/invoices/{tax['id']}.pdf").content)[1]
    assert "Alok Sharma" in _images_in_pdf(a.get(f"/api/print/invoices/{pro['id']}.pdf").content)[1]
    assert a.get("/api/signatories").json()["settings"] == {"sig_on_tax": False, "sig_on_pro": True}


def test_emailed_invoice_carries_the_signature(org, monkeypatch):
    from app import mailer
    sent = []
    monkeypatch.setattr(mailer, "deliver", lambda t, msg: sent.append(msg) or {})
    a, tax, pro = _books(org)
    a.put("/api/org/smtp", json={"from_email": "accounts@aequm.in", "host": "smtp.test",
                                 "port": 587, "username": "u", "password": "p"})
    _add(a, "Alok Sharma", on=True)
    r = a.post("/api/email/send", json={"kind": "invoice", "id": pro["id"], "to": ["x@y.in"],
                                         "subject": "s", "body": "b"})
    assert r.status_code == 200, r.text
    pdf = next(p.get_payload(decode=True) for p in sent[0].walk() if p.get_filename())
    assert "Alok Sharma" in _images_in_pdf(pdf)[1]


# ------------------------------------------------------------ access
def test_signatures_are_tenant_private_and_need_the_permission(api, org):
    a = org(name="One", email="a@one.in")
    b = org(name="Two", email="b@two.in")
    s = _add(a, "Alok Sharma", on=True)
    assert b.get("/api/signatories").json()["signatories"] == []
    assert b.delete(f"/api/signatories/{s['id']}").status_code == 404
    gid = [g for g in a.get("/api/groups").json() if g["name"] == "Accounts"][0]["id"]
    a.post("/api/users", json={"name": "Acc", "email": "acc@one.in",
                               "password": "correct horse", "group_id": gid})
    tok = api.post("/api/auth/signin", json={"email": "acc@one.in",
                                              "password": "correct horse"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}", "X-Tenant-Id": str(a.tid)}
    assert api.get("/api/signatories", headers=h).status_code == 403
