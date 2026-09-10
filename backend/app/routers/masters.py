from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from .. import models as M, schemas as S
from ..db import get_db
from ..deps import Ctx, current, need
from ..service import next_code
from ..fy import current_fy

router = APIRouter(tags=["masters"])


def _contacts_for(ctx, kind, pid):
    rows = ctx.db.execute(select(M.PartyContact).where(
        M.PartyContact.tenant_id == ctx.tenant.id,
        M.PartyContact.party_kind == kind,
        M.PartyContact.party_id == pid)).scalars().all()
    return [{"id": c.id, "first_name": c.first_name, "middle_name": c.middle_name,
             "last_name": c.last_name, "designation_id": c.designation_id,
             "designation": c.designation.name if c.designation else None,
             "phone": c.phone, "email": c.email, "is_primary": c.is_primary}
            for c in rows]


def _save_contacts(ctx, kind, pid, contacts):
    for c in contacts:
        if c.designation_id and not ctx.db.get(M.Designation, c.designation_id):
            raise HTTPException(422, "That designation does not exist")
    for n, c in enumerate(contacts):
        ctx.db.add(M.PartyContact(tenant_id=ctx.tenant.id, party_kind=kind, party_id=pid,
            first_name=c.first_name.strip(), middle_name=c.middle_name,
            last_name=c.last_name, designation_id=c.designation_id,
            phone=c.phone, email=c.email, is_primary=c.is_primary or n == 0))

def _replace_contacts(ctx, kind, pid, contacts):
    for old in ctx.db.execute(
        select(M.PartyContact).where(
            M.PartyContact.tenant_id == ctx.tenant.id,
            M.PartyContact.party_kind == kind,
            M.PartyContact.party_id == pid,
        )
    ).scalars():
        ctx.db.delete(old)

    ctx.db.flush()
    _save_contacts(ctx, kind, pid, contacts)
def _party_out(p, extra=None, contacts=None):
    d = {"id": p.id, "code": p.code, "name": p.name, "party_type": p.party_type, "logo": p.logo,
         "email": p.email, "pan": p.pan, "msme_registered": p.msme_registered,
         "msme_number": p.msme_number, "bank_name": p.bank_name,
         "bank_ifsc": p.bank_ifsc, "bank_account": p.bank_account,
         "gstins": [{"id": g.id, "gstin": g.gstin, "state_code": g.state_code,
                     "label": g.label, "is_default": g.is_default} for g in p.gstins],
         "contacts": contacts or []}
    if hasattr(p, "tds_section"):                 # vendors only
        d["tds_section"] = p.tds_section
        d["tds_rate"] = float(p.tds_rate or 0)
    d.update(extra or {})
    return d


@router.get("/states")
def states(db=Depends(get_db)):
    return [{"code": s.code, "name": s.name}
            for s in db.execute(select(M.State).order_by(M.State.code)).scalars()]


@router.get("/uoms")
def uoms(db=Depends(get_db)):
    return [{"code": u.code, "name": u.name}
            for u in db.execute(select(M.Uom).order_by(M.Uom.code)).scalars()]


# ------------------------------------------------------------ customers
@router.get("/customers")
def list_customers(ctx: Ctx = Depends(need("customers"))):
    rows = ctx.db.execute(ctx.scope(select(M.Customer), M.Customer)
                          .order_by(M.Customer.code)).scalars().all()
    return [_party_out(c, {"bill_addr": c.bill_addr, "bill_city": c.bill_city,
                           "bill_state": c.bill_state, "bill_pin": c.bill_pin,
                           "ship_same": c.ship_same, "ship_addr": c.ship_addr,
                           "ship_city": c.ship_city, "ship_state": c.ship_state,
                           "ship_pin": c.ship_pin},
                       _contacts_for(ctx, "CUSTOMER", c.id)) for c in rows]


@router.post("/customers", status_code=201)
def add_customer(body: S.CustomerIn, ctx: Ctx = Depends(need("customers"))):
    code = body.code or next_code(ctx, "customer")
    if ctx.db.execute(ctx.scope(select(M.Customer), M.Customer)
                      .where(M.Customer.code == code)).scalar_one_or_none():
        raise HTTPException(409, f"Customer code {code} already exists in this organisation")
    for g in body.gstins:
        if ctx.db.execute(select(M.CustomerGstin)
                          .where(M.CustomerGstin.gstin == g.gstin)).scalar_one_or_none():
            raise HTTPException(409, f"GSTIN {g.gstin} is already recorded")
    c = M.Customer(tenant_id=ctx.tenant.id, code=code,
                   **body.model_dump(exclude={"gstins", "code", "contacts"}))
    ctx.db.add(c)
    ctx.db.flush()
    _save_contacts(ctx, "CUSTOMER", c.id, body.contacts)
    for n, g in enumerate(body.gstins):
        ctx.db.add(M.CustomerGstin(customer_id=c.id, gstin=g.gstin, state_code=g.gstin[:2],
                                   label=g.label, is_default=g.is_default or n == 0))
    ctx.db.commit()
    ctx.db.refresh(c)
    return _party_out(c, contacts=_contacts_for(ctx, "CUSTOMER", c.id))

@router.put("/customers/{cid}")
def edit_customer(cid: int, body: S.CustomerIn, ctx: Ctx = Depends(need("customers"))):
    c = ctx.get(M.Customer, cid)
    if not c:
        raise HTTPException(404, "No such customer")

    code = body.code or c.code

    other = ctx.db.execute(
        ctx.scope(select(M.Customer), M.Customer)
        .where(M.Customer.code == code, M.Customer.id != cid)
    ).scalar_one_or_none()

    if other:
        raise HTTPException(
            409,
            f"Customer code {code} already exists in this organisation"
        )

    for g in body.gstins:
        hit = ctx.db.execute(
            select(M.CustomerGstin)
            .where(M.CustomerGstin.gstin == g.gstin)
        ).scalar_one_or_none()

        if hit and hit.customer_id != cid:
            raise HTTPException(
                409,
                f"GSTIN {g.gstin} is already recorded against another customer"
            )

    for k, v in body.model_dump(
        exclude={"gstins", "code", "contacts"}
    ).items():
        setattr(c, k, v)

    c.code = code

    for old in ctx.db.execute(
        select(M.CustomerGstin)
        .where(M.CustomerGstin.customer_id == cid)
    ).scalars():
        ctx.db.delete(old)

    ctx.db.flush()

    for n, g in enumerate(body.gstins):
        ctx.db.add(
            M.CustomerGstin(
                customer_id=c.id,
                gstin=g.gstin,
                state_code=g.gstin[:2],
                label=g.label,
                is_default=g.is_default or n == 0,
            )
        )

    _replace_contacts(ctx, "CUSTOMER", c.id, body.contacts)

    ctx.db.commit()
    ctx.db.refresh(c)

    return _party_out(
        c,
        contacts=_contacts_for(ctx, "CUSTOMER", c.id)
    )

def _check_logo(logo):
    if logo and not str(logo).startswith("data:image/"):
        raise HTTPException(
            422,
            "Send the logo as a data URI beginning data:image/"
        )

    if logo and len(logo) > 700_000:
        raise HTTPException(
            413,
            "That image is too large. Keep it under about 500 KB."
        )


@router.put("/customers/{cid}/logo")
def customer_logo(
    cid: int,
    body: dict,
    ctx: Ctx = Depends(need("customers"))
):
    c = ctx.get(M.Customer, cid)

    if not c:
        raise HTTPException(404, "No such customer")

    _check_logo(body.get("logo"))

    c.logo = body.get("logo") or None

    ctx.db.commit()

    return {
        "id": c.id,
        "logo": c.logo
    }
@router.delete("/customers/{cid}", status_code=204)
def del_customer(cid: int, ctx: Ctx = Depends(need("customers"))):
    c = ctx.get(M.Customer, cid)
    if not c:
        raise HTTPException(404, "No such customer")
    if ctx.db.execute(select(M.Invoice).where(M.Invoice.customer_id == cid)).first():
        raise HTTPException(409, "That customer has invoices and cannot be deleted")
    ctx.db.delete(c)
    ctx.db.commit()


# -------------------------------------------------------------- vendors
@router.get("/vendors")
def list_vendors(ctx: Ctx = Depends(need("vendors"))):
    rows = ctx.db.execute(ctx.scope(select(M.Vendor), M.Vendor)
                          .order_by(M.Vendor.code)).scalars().all()
    return [_party_out(v, {"addr": v.addr, "city": v.city,
                           "state_code": v.state_code, "pin": v.pin,
                           "tds_section": v.tds_section, "tds_rate": float(v.tds_rate)},
                       _contacts_for(ctx, "VENDOR", v.id)) for v in rows]


@router.post("/vendors", status_code=201)
def add_vendor(body: S.VendorIn, ctx: Ctx = Depends(need("vendors"))):
    code = body.code or next_code(ctx, "vendor")
    if ctx.db.execute(ctx.scope(select(M.Vendor), M.Vendor)
                      .where(M.Vendor.code == code)).scalar_one_or_none():
        raise HTTPException(409, f"Vendor code {code} already exists in this organisation")
    v = M.Vendor(tenant_id=ctx.tenant.id, code=code,
                 **body.model_dump(exclude={"gstins", "code", "contacts"}))
    ctx.db.add(v)
    ctx.db.flush()
    _save_contacts(ctx, "VENDOR", v.id, body.contacts)
    for i, g in enumerate(body.gstins):
        ctx.db.add(M.VendorGstin(vendor_id=v.id, gstin=g.gstin, state_code=g.gstin[:2],
                                 label=g.label, is_default=g.is_default or i == 0))
    ctx.db.commit()
    ctx.db.refresh(v)
    return _party_out(v, contacts=_contacts_for(ctx, "VENDOR", v.id))

@router.put("/vendors/{vid}")
def edit_vendor(
    vid: int,
    body: S.VendorIn,
    ctx: Ctx = Depends(need("vendors"))
):
    v = ctx.get(M.Vendor, vid)

    if not v:
        raise HTTPException(404, "No such vendor")

    code = body.code or v.code

    other = ctx.db.execute(
        ctx.scope(select(M.Vendor), M.Vendor)
        .where(M.Vendor.code == code, M.Vendor.id != vid)
    ).scalar_one_or_none()

    if other:
        raise HTTPException(
            409,
            f"Vendor code {code} already exists in this organisation"
        )

    for k, val in body.model_dump(
        exclude={"gstins", "code", "contacts"}
    ).items():
        setattr(v, k, val)

    v.code = code

    for old in ctx.db.execute(
        select(M.VendorGstin)
        .where(M.VendorGstin.vendor_id == vid)
    ).scalars():
        ctx.db.delete(old)

    ctx.db.flush()

    for i, g in enumerate(body.gstins):
        ctx.db.add(
            M.VendorGstin(
                vendor_id=v.id,
                gstin=g.gstin,
                state_code=g.gstin[:2],
                label=g.label,
                is_default=g.is_default or i == 0,
            )
        )

    _replace_contacts(ctx, "VENDOR", v.id, body.contacts)

    ctx.db.commit()
    ctx.db.refresh(v)

    return _party_out(
        v,
        contacts=_contacts_for(ctx, "VENDOR", v.id)
    )


@router.put("/vendors/{vid}/logo")
def vendor_logo(
    vid: int,
    body: dict,
    ctx: Ctx = Depends(need("vendors"))
):
    v = ctx.get(M.Vendor, vid)

    if not v:
        raise HTTPException(404, "No such vendor")

    _check_logo(body.get("logo"))

    v.logo = body.get("logo") or None

    ctx.db.commit()

    return {
        "id": v.id,
        "logo": v.logo
    }

@router.delete("/vendors/{vid}", status_code=204)
def del_vendor(vid: int, ctx: Ctx = Depends(need("vendors"))):
    v = ctx.get(M.Vendor, vid)
    if not v:
        raise HTTPException(404, "No such vendor")
    if ctx.db.execute(select(M.PurchaseOrder).where(M.PurchaseOrder.vendor_id == vid)).first():
        raise HTTPException(409, "That vendor has purchase orders and cannot be deleted")
    ctx.db.delete(v)
    ctx.db.commit()


# ------------------------------------------------------------ materials
def _mat_out(m, attrs=None):
    return {"id": m.id, "code": m.code, "descr": m.descr, "price": float(m.price),
            "cost": float(m.cost), "hsn": m.hsn, "stock_qty": float(m.stock_qty),
            "uom": m.uom, "batch_managed": m.batch_managed,
            "shelf_life_days": m.shelf_life_days,
            "sgst_pct": float(m.sgst_pct), "cgst_pct": float(m.cgst_pct),
            "igst_pct": float(m.igst_pct), "active": m.active,
            "attributes": attrs or {}}


@router.get("/materials")
def list_materials(ctx: Ctx = Depends(need("materials"))):
    mats = ctx.db.execute(ctx.scope(select(M.Material), M.Material)
                          .order_by(M.Material.code)).scalars().all()
    links = ctx.db.execute(select(M.MaterialAttribute)).scalars().all()
    by_mat = {}
    for l in links:
        by_mat.setdefault(l.material_id, {})[l.attribute_id] = l.value
    return [_mat_out(m, by_mat.get(m.id, {})) for m in mats]


@router.post("/materials", status_code=201)
def add_material(body: S.MaterialIn, ctx: Ctx = Depends(need("materials"))):
    code = (body.code or "").strip().upper() or next_code(ctx, "material")
    # an HSN on file supplies the rates unless the material overrides them
    hsn = ctx.db.execute(ctx.scope(select(M.HsnCode), M.HsnCode)
                         .where(M.HsnCode.code == body.hsn)).scalar_one_or_none()
    if hsn and (body.use_hsn_rates or body.sgst_pct is None):
        body.sgst_pct, body.cgst_pct, body.igst_pct = hsn.sgst_pct, hsn.cgst_pct, hsn.igst_pct
    if body.sgst_pct is None:
        raise HTTPException(422,
            f"No rates were given and HSN {body.hsn} is not in the HSN and SAC master. "
            "Add the code there, or enter the three rates on the material.")
    if ctx.db.execute(ctx.scope(select(M.Material), M.Material)
                      .where(M.Material.code == code)).scalar_one_or_none():
        raise HTTPException(409, f"Material code {code} already exists in this organisation")
    data = body.model_dump(exclude={"attributes", "use_hsn_rates"})
    m = M.Material(tenant_id=ctx.tenant.id, **{**data, "code": code})
    ctx.db.add(m)
    ctx.db.flush()
    for aid, val in (body.attributes or {}).items():
        a = ctx.db.get(M.Attribute, int(aid))
        if not a:
            raise HTTPException(422, f"Attribute {aid} does not exist")
        if a.attr_type == "LIST" and val not in [v.value for v in a.values]:
            raise HTTPException(422, f"{val} is not a permitted value for {a.name}")
        if a.attr_type == "MULTI":
            allowed = {v.value for v in a.values}
            bad = [x.strip() for x in str(val).split(",") if x.strip() not in allowed]
            if bad:
                raise HTTPException(422, f"{', '.join(bad)} not permitted for {a.name}")
        ctx.db.add(M.MaterialAttribute(material_id=m.id, attribute_id=a.id, value=str(val)))
    ctx.db.commit()
    ctx.db.refresh(m)
    return _mat_out(m, {int(k): str(v) for k, v in (body.attributes or {}).items()})
@router.put("/materials/{mid}")
def edit_material(
    mid: int,
    body: S.MaterialIn,
    ctx: Ctx = Depends(need("materials"))
):
    m = ctx.get(M.Material, mid)

    if not m:
        raise HTTPException(404, "No such material")

    code = (body.code or "").strip().upper() or m.code

    other = ctx.db.execute(
        ctx.scope(select(M.Material), M.Material)
        .where(M.Material.code == code, M.Material.id != mid)
    ).scalar_one_or_none()

    if other:
        raise HTTPException(
            409,
            f"Material code {code} already exists in this organisation"
        )

    hsn = ctx.db.execute(
        ctx.scope(select(M.HsnCode), M.HsnCode)
        .where(M.HsnCode.code == body.hsn)
    ).scalar_one_or_none()

    if hsn and (body.use_hsn_rates or body.sgst_pct is None):
        body.sgst_pct = hsn.sgst_pct
        body.cgst_pct = hsn.cgst_pct
        body.igst_pct = hsn.igst_pct

    if body.sgst_pct is None:
        raise HTTPException(
            422,
            f"No rates were given and HSN {body.hsn} is not in the HSN and SAC master."
        )

    data = body.model_dump(
        exclude={"attributes", "use_hsn_rates", "stock_qty"}
    )

    for k, v in data.items():
        setattr(m, k, v)

    m.code = code

    for old in ctx.db.execute(
        select(M.MaterialAttribute)
        .where(M.MaterialAttribute.material_id == mid)
    ).scalars():
        ctx.db.delete(old)

    ctx.db.flush()

    for aid, val in (body.attributes or {}).items():
        a = ctx.db.get(M.Attribute, int(aid))

        if not a:
            raise HTTPException(
                422,
                f"Attribute {aid} does not exist"
            )

        ctx.db.add(
            M.MaterialAttribute(
                material_id=m.id,
                attribute_id=a.id,
                value=str(val)
            )
        )

    ctx.db.commit()
    ctx.db.refresh(m)

    return _mat_out(
        m,
        {int(k): str(v) for k, v in (body.attributes or {}).items()}
    )

@router.delete("/materials/{mid}", status_code=204)
def del_material(mid: int, ctx: Ctx = Depends(need("materials"))):
    m = ctx.get(M.Material, mid)
    if not m:
        raise HTTPException(404, "No such material")
    if ctx.db.execute(select(M.InvoiceLine).where(M.InvoiceLine.material_id == mid)).first():
        raise HTTPException(409, "That material appears on invoices; deactivate it instead")
    ctx.db.delete(m)
    ctx.db.commit()


# ------------------------------------------------- organisation and SMTP
@router.get("/org")
def get_org(ctx: Ctx = Depends(need("org"))):
    t = ctx.tenant
    return {"id": t.id, "name": t.name, "gstin": t.gstin, "pan": t.pan, "addr": t.addr,
            "city": t.city, "state_code": t.state_code, "pin": t.pin, "logo": t.logo,
            "company_type": t.company_type,
            "inv_prefix": t.inv_prefix, "inv_seq": t.inv_seq,
            "po_prefix": t.po_prefix, "po_seq": t.po_seq, "bank": t.bank, "inv_fy": t.inv_fy,
            "po_fy": t.po_fy,
            "vinv_prefix": t.vinv_prefix,
            "vinv_seq": t.vinv_seq,
            "vinv_fy": t.vinv_fy,
            "fy_start_month": t.fy_start_month,
            "fy_start_day": t.fy_start_day,
            "current_fy": current_fy(t),
            "cust_prefix": t.cust_prefix,
            "cust_seq": t.cust_seq,
            "vend_prefix": t.vend_prefix,
            "vend_seq": t.vend_seq,
            "mat_prefix": t.mat_prefix,
            "mat_seq": t.mat_seq,
            "bank_name": t.bank_name,
            "bank_ifsc": t.bank_ifsc,
            "bank_account": t.bank_account,
            "smtp": {"from_name": t.smtp_from_name, "from_email": t.smtp_from_email,
                     "reply_to": t.smtp_reply_to, "bcc": t.smtp_bcc, "host": t.smtp_host,
                     "port": t.smtp_port, "encryption": t.smtp_encryption,
                     "username": t.smtp_username,
                     # the password is never sent back, only whether one is set
                     "password_set": bool(t.smtp_password)}}


@router.put("/org")
def put_org(body: S.TenantIn, ctx: Ctx = Depends(need("org"))):
    for k, v in body.model_dump().items():
        setattr(ctx.tenant, k, v)
    ctx.db.commit()
    return get_org(ctx)


@router.put("/org/logo")
def put_logo(body: dict, ctx: Ctx = Depends(need("org"))):
    logo = body.get("logo")
    if logo and not str(logo).startswith("data:image/"):
        raise HTTPException(422, "Send the logo as a data URI beginning data:image/")
    if logo and len(logo) > 700_000:
        raise HTTPException(413, "That image is too large. Keep it under about 500 KB.")
    ctx.tenant.logo = logo
    ctx.db.commit()
    return {"logo": ctx.tenant.logo}


@router.put("/org/smtp")
def put_smtp(body: S.SmtpIn, ctx: Ctx = Depends(need("org"))):
    t = ctx.tenant
    t.smtp_from_name, t.smtp_from_email = body.from_name, body.from_email
    t.smtp_reply_to, t.smtp_bcc = body.reply_to, body.bcc
    t.smtp_host, t.smtp_port = body.host, body.port
    t.smtp_encryption, t.smtp_username = body.encryption, body.username
    if body.password:                       # blank means leave the stored one alone
        t.smtp_password = body.password
    ctx.db.commit()
    return get_org(ctx)


@router.post("/org/smtp/check")
def check_smtp(ctx: Ctx = Depends(need("org"))):
    """Report what is missing. A live send is attempted only by /email/send."""
    t, problems = ctx.tenant, []
    if not t.smtp_from_email: problems.append("send-from address is missing")
    if not t.smtp_host: problems.append("SMTP host is missing")
    if not t.smtp_port: problems.append("port is missing")
    elif t.smtp_encryption == "STARTTLS" and t.smtp_port != 587:
        problems.append(f"port {t.smtp_port} is unusual for STARTTLS, 587 is normal")
    elif t.smtp_encryption == "SSL" and t.smtp_port != 465:
        problems.append(f"port {t.smtp_port} is unusual for SSL, 465 is normal")
    if not t.smtp_username: problems.append("username is missing")
    if not t.smtp_password: problems.append("password is missing")
    return {"ok": not problems, "problems": problems,
            "note": "This checks the settings only. A real connection is made when a mail is sent."}

# ================================================= designations and banks
@router.get("/designations")
def designations(ctx: Ctx = Depends(current)):
    return [{"id": d.id, "name": d.name} for d in ctx.db.execute(
        select(M.Designation).order_by(M.Designation.name)).scalars()]


@router.post("/designations", status_code=201)
def add_designation(body: S.NamedIn, ctx: Ctx = Depends(need("customers"))):
    name = body.name.strip()
    if ctx.db.execute(select(M.Designation)
                      .where(M.Designation.name == name)).scalar_one_or_none():
        raise HTTPException(409, f"{name} is already a designation")
    d = M.Designation(name=name)
    ctx.db.add(d)
    ctx.db.commit()
    return {"id": d.id, "name": d.name}


@router.get("/banks")
def banks(ctx: Ctx = Depends(current)):
    return [{"id": b.id, "name": b.name, "short_code": b.short_code}
            for b in ctx.db.execute(select(M.Bank).order_by(M.Bank.name)).scalars()]


@router.post("/banks", status_code=201)
def add_bank(body: S.NamedIn, ctx: Ctx = Depends(need("customers"))):
    name = body.name.strip()
    if ctx.db.execute(select(M.Bank).where(M.Bank.name == name)).scalar_one_or_none():
        raise HTTPException(409, f"{name} is already on the bank list")
    b = M.Bank(name=name, short_code=body.short_code)
    ctx.db.add(b)
    ctx.db.commit()
    return {"id": b.id, "name": b.name, "short_code": b.short_code}


# ============================================================ HSN and SAC
def _hsn_out(h):
    return {"id": h.id, "code": h.code, "descr": h.descr, "kind": h.kind,
            "sgst_pct": float(h.sgst_pct), "cgst_pct": float(h.cgst_pct),
            "igst_pct": float(h.igst_pct), "cess_pct": float(h.cess_pct),
            "active": h.active}


@router.get("/hsn")
def list_hsn(ctx: Ctx = Depends(current)):
    """Readable by anyone signed in, because the material screen needs it."""
    rows = ctx.db.execute(ctx.scope(select(M.HsnCode), M.HsnCode)
                          .order_by(M.HsnCode.code)).scalars().all()
    out = []
    for h in rows:
        used = ctx.db.execute(select(func.count()).select_from(M.Material).where(
            M.Material.tenant_id == ctx.tenant.id, M.Material.hsn == h.code)).scalar_one()
        out.append({**_hsn_out(h), "used_on": used})
    return out


@router.post("/hsn", status_code=201)
def add_hsn(body: S.HsnIn, ctx: Ctx = Depends(need("hsn"))):
    code = body.code.strip()
    if ctx.db.execute(ctx.scope(select(M.HsnCode), M.HsnCode)
                      .where(M.HsnCode.code == code)).scalar_one_or_none():
        raise HTTPException(409, f"{code} is already on the HSN and SAC list")
    h = M.HsnCode(tenant_id=ctx.tenant.id, **{**body.model_dump(), "code": code})
    ctx.db.add(h)
    ctx.db.commit()
    ctx.db.refresh(h)
    return _hsn_out(h)


@router.put("/hsn/{hid}")
def edit_hsn(hid: int, body: S.HsnIn, ctx: Ctx = Depends(need("hsn"))):
    h = ctx.get(M.HsnCode, hid)
    if not h:
        raise HTTPException(404, "No such HSN or SAC code")
    for k, v in body.model_dump().items():
        setattr(h, k, v)
    ctx.db.commit()
    ctx.db.refresh(h)
    return _hsn_out(h)


@router.delete("/hsn/{hid}", status_code=204)
def del_hsn(hid: int, ctx: Ctx = Depends(need("hsn"))):
    h = ctx.get(M.HsnCode, hid)
    if not h:
        raise HTTPException(404, "No such HSN or SAC code")
    used = ctx.db.execute(select(func.count()).select_from(M.Material).where(
        M.Material.tenant_id == ctx.tenant.id, M.Material.hsn == h.code)).scalar_one()
    if used:
        raise HTTPException(409, f"That code is on {used} material(s)")
    ctx.db.delete(h)
    ctx.db.commit()
