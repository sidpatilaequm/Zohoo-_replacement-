"""Blank CSV templates and the importers that read them back.

Each template carries the exact column names the importer expects and one
worked example row, so the shape is never in doubt.
"""
import csv, io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from .. import models as M, schemas as S
from ..deps import Ctx, need
from ..routers.masters import add_customer, add_vendor, add_material
from ..routers.docs import add_invoice, add_po, add_vinv

router = APIRouter(prefix="/templates", tags=["templates"])

OBJECTS = {
  "customers": {
    "perm": "customers", "label": "Customers",
    "cols": ["Customer Code","Customer Name","Type","PAN","MSME Registered","MSME Number",
             "Billing Address","Billing City","Billing State Code","Billing PIN",
             "Delivery Same As Billing","Delivery Address","Delivery City",
             "Delivery State Code","Delivery PIN","Email","GSTIN","GSTIN Label",
             "Bank Name","IFSC","Bank Account","Contact First Name","Contact Middle Name",
             "Contact Last Name","Contact Designation","Contact Phone","Contact Email"],
    "example": ["C900","Example Traders Pvt Ltd","B2B","AAPCA3382B","Yes","UDYAM-KR-03-0001234",
                "12 MG Road","Bengaluru","29","560001","Y","","","","","ap@example.com",
                "29AAACE1234R1Z9","Head office","State Bank of India","SBIN0040807",
                "38600386525","Anita","K","Rao","Accounts Manager","+91 98450 12345",
                "anita@example.com"]},
  "vendors": {
    "perm": "vendors", "label": "Vendors",
    "cols": ["Vendor Code","Vendor Name","Type","PAN","MSME Registered","MSME Number",
             "Address","City","State Code","PIN","Email","GSTIN","GSTIN Label",
             "Bank Name","IFSC","Bank Account","Contact First Name","Contact Middle Name",
             "Contact Last Name","Contact Designation","Contact Phone","Contact Email"],
    "example": ["V900","Example Supplies Pvt Ltd","B2B","AABCE1234F","No","",
                "9 Industrial Estate","Pune","27","411019","ap@supplier.com",
                "27AABCE1234F1Z5","Pune","HDFC Bank","HDFC0000123","50200012345678",
                "Ravi","","Kumar","Sales Head","+91 90000 11111","ravi@supplier.com"]},
  "materials": {
    "perm": "materials", "label": "Materials",
    "cols": ["Material Code","Description","Selling Price","Cost Price","HSN/SAC",
             "Stock Quantity","UoM","Batch Managed","Shelf Life Days",
             "SGST %","CGST %","IGST %"],
    "example": ["PHM-NEW","Example tablet 10 mg","148.00","112.00","30049099","0","BOX",
                "Yes","730","6","6","12"]},
  "customer-estimates": {
    "perm": "invoice", "label": "Customer estimates (proforma invoices)",
    "cols": ["Document Number","Document Date","Due Date","Customer Code","Recipient GSTIN",
             "Place of Supply","Their Reference","Material Code","Quantity","Unit Price"],
    "example": ["EST/900","2026-08-14","","C900","29AAACE1234R1Z9","29","RFQ-11",
                "PHM-NEW","10","148.00"]},
  "customer-invoices": {
    "perm": "invoice", "label": "Customer invoices",
    "cols": ["Invoice Number","Invoice Date","Due Date","Customer Code","Recipient GSTIN",
             "Place of Supply","PO Number","PO Date","Reverse Charge","Material Code",
             "Quantity","Unit Price"],
    "example": ["INV/900","2026-08-14","2026-09-13","C900","29AAACE1234R1Z9","29","PO-8891",
                "2026-08-01","N","PHM-NEW","10","148.00"]},
  "vendor-estimates": {
    "perm": "po", "label": "Vendor estimates (purchase orders)",
    "cols": ["PO Number","PO Date","Required By","Vendor Code","Vendor GSTIN",
             "Billing Address","Delivery Address","Material Code","Quantity","Cost Price"],
    "example": ["PO/900","2026-08-01","2026-08-20","V900","27AABCE1234F1Z5",
                "Our registered office","Warehouse 2","PHM-NEW","200","112.00"]},
  "vendor-invoices": {
    "perm": "vinv", "label": "Vendor invoices",
    "cols": ["Vendor Invoice Number","Invoice Date","Due Date","Vendor Code","PO Number",
             "Material Code","Quantity","Unit Price"],
    "example": ["SUP/2026/77","2026-08-05","2026-09-04","V900","PO/900","PHM-NEW",
                "200","112.00"]},
}


@router.get("")
def list_templates(ctx: Ctx = Depends(need("data"))):
    return [{"key": k, "label": v["label"], "columns": v["cols"]}
            for k, v in OBJECTS.items()]


@router.get("/{key}.csv")
def template_csv(key: str, ctx: Ctx = Depends(need("data"))):
    o = OBJECTS.get(key)
    if not o:
        raise HTTPException(404, "No template with that name")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(o["cols"])
    w.writerow(o["example"])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="template_{key}.csv"'})


# ------------------------------------------------------------- helpers
def _rows(raw, cols):
    rdr = csv.DictReader(io.StringIO(raw))
    missing = [c for c in cols if c not in (rdr.fieldnames or [])]
    if missing:
        raise HTTPException(422,
            f"These columns are missing from the file: {', '.join(missing)}. "
            "Download the template and use its headings exactly.")
    return [r for r in rdr if any((v or "").strip() for v in r.values())]


def _dec(v, field, row):
    try:
        return Decimal(str(v).replace(",", "").strip() or "0")
    except InvalidOperation:
        raise HTTPException(422, f"Row {row}: {field} is not a number")


def _date(v, field, row, required=True):
    v = (v or "").strip()
    if not v:
        if required:
            raise HTTPException(422, f"Row {row}: {field} is required")
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    raise HTTPException(422, f"Row {row}: {field} '{v}' is not a date. Use YYYY-MM-DD.")


YES = {"y", "yes", "true", "1"}


@router.post("/{key}/import")
async def import_csv(key: str, file: UploadFile = File(...),
                     dry_run: bool = Query(False,
                        description="Check the file and report, without writing anything"),
                     ctx: Ctx = Depends(need("data"))):
    o = OBJECTS.get(key)
    if not o:
        raise HTTPException(404, "No importer with that name")
    ctx.require(o["perm"])
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    rows = _rows(raw, o["cols"])
    if not rows:
        raise HTTPException(422, "The file has headings but no data rows")

    added, skipped, errors = 0, 0, []

    # The handlers below are the same ones the API uses, so the rules cannot drift
    # between a typed entry and an imported one. They each commit, which would end
    # the transaction mid-file, so commit is turned into flush for the duration and
    # the whole file is committed or rolled back once at the end.
    real_commit = ctx.db.commit
    ctx.db.commit = ctx.db.flush

    def code_of(model, code):
        return ctx.db.execute(ctx.scope(select(model), model)
                              .where(model.code == code)).scalar_one_or_none()

    try:
        if key in ("customers", "vendors"):
            for n, r in enumerate(rows, 2):
                try:
                    code = (r.get("Customer Code") or r.get("Vendor Code") or "").strip()
                    name = (r.get("Customer Name") or r.get("Vendor Name") or "").strip()
                    if not name:
                        raise HTTPException(422, f"Row {n}: a name is required")
                    model = M.Customer if key == "customers" else M.Vendor
                    if code and code_of(model, code):
                        skipped += 1
                        continue
                    g = (r.get("GSTIN") or "").strip().upper()
                    contacts = []
                    if (r.get("Contact First Name") or "").strip():
                        dname = (r.get("Contact Designation") or "").strip()
                        did = None
                        if dname:
                            d = ctx.db.execute(select(M.Designation)
                                    .where(M.Designation.name == dname)).scalar_one_or_none()
                            if not d:
                                d = M.Designation(name=dname)
                                ctx.db.add(d)
                                ctx.db.flush()
                            did = d.id
                        contacts = [S.ContactIn(first_name=r["Contact First Name"].strip(),
                            middle_name=(r.get("Contact Middle Name") or "").strip() or None,
                            last_name=(r.get("Contact Last Name") or "").strip() or None,
                            designation_id=did,
                            phone=(r.get("Contact Phone") or "").strip() or None,
                            email=(r.get("Contact Email") or "").strip() or None,
                            is_primary=True)]
                    bank = (r.get("Bank Name") or "").strip()
                    if bank and not ctx.db.execute(select(M.Bank)
                            .where(M.Bank.name == bank)).scalar_one_or_none():
                        ctx.db.add(M.Bank(name=bank))
                        ctx.db.flush()
                    common = dict(code=code or None, name=name,
                        party_type=(r.get("Type") or "B2B").strip().upper() or "B2B",
                        pan=(r.get("PAN") or "").strip() or None,
                        msme_registered=(r.get("MSME Registered") or "").strip().lower() in YES,
                        msme_number=(r.get("MSME Number") or "").strip() or None,
                        email=(r.get("Email") or "").strip() or None,
                        bank_name=bank or None,
                        bank_ifsc=(r.get("IFSC") or "").strip() or None,
                        bank_account=(r.get("Bank Account") or "").strip() or None,
                        gstins=([{"gstin": g, "label": (r.get("GSTIN Label") or "").strip() or None,
                                  "is_default": True}] if g else []),
                        contacts=contacts)
                    if key == "customers":
                        same = (r.get("Delivery Same As Billing") or "Y").strip().lower() in YES
                        add_customer(S.CustomerIn(**common,
                            bill_addr=r["Billing Address"].strip(),
                            bill_city=r["Billing City"].strip(),
                            bill_state=r["Billing State Code"].strip(),
                            bill_pin=(r.get("Billing PIN") or "").strip() or None,
                            ship_same=same,
                            ship_addr=(r.get("Delivery Address") or "").strip() or None,
                            ship_city=(r.get("Delivery City") or "").strip() or None,
                            ship_state=(r.get("Delivery State Code") or "").strip() or None,
                            ship_pin=(r.get("Delivery PIN") or "").strip() or None), ctx)
                    else:
                        add_vendor(S.VendorIn(**common, addr=r["Address"].strip(),
                            city=r["City"].strip(), state_code=r["State Code"].strip(),
                            pin=(r.get("PIN") or "").strip() or None), ctx)
                    added += 1
                except HTTPException as e:
                    errors.append(f"Row {n}: {e.detail}")
                except Exception as e:
                    errors.append(f"Row {n}: {e}")

        elif key == "materials":
            for n, r in enumerate(rows, 2):
                try:
                    code = r["Material Code"].strip().upper()
                    if code_of(M.Material, code):
                        skipped += 1
                        continue
                    add_material(S.MaterialIn(code=code, descr=r["Description"].strip(),
                        price=_dec(r["Selling Price"], "Selling Price", n),
                        cost=_dec(r.get("Cost Price"), "Cost Price", n),
                        hsn=r["HSN/SAC"].strip(),
                        stock_qty=_dec(r.get("Stock Quantity"), "Stock Quantity", n),
                        uom=(r.get("UoM") or "NOS").strip().upper(),
                        batch_managed=(r.get("Batch Managed") or "").strip().lower() in YES,
                        shelf_life_days=int(_dec(r.get("Shelf Life Days"), "Shelf Life Days", n)),
                        sgst_pct=_dec(r["SGST %"], "SGST %", n),
                        cgst_pct=_dec(r["CGST %"], "CGST %", n),
                        igst_pct=_dec(r["IGST %"], "IGST %", n),
                        use_hsn_rates=False), ctx)
                    added += 1
                except HTTPException as e:
                    errors.append(f"Row {n}: {e.detail}")
                except Exception as e:
                    errors.append(f"Row {n}: {e}")

        else:
            added, skipped, errors = _import_documents(ctx, key, rows)
    finally:
        ctx.db.commit = real_commit

    if dry_run or errors:
        ctx.db.rollback()
    else:
        ctx.db.commit()

    return {"object": o["label"], "rows_read": len(rows),
            "added": 0 if (dry_run or errors) else added,
            "would_add": added if (dry_run or errors) else None,
            "skipped_existing": skipped, "errors": errors,
            "committed": not (dry_run or errors),
            "note": ("Nothing was written. Fix the rows listed and upload again."
                     if errors else
                     "Checked only, nothing written." if dry_run else "Imported.")}


def _import_documents(ctx, key, rows):
    """Group the flat rows into documents, then post each one."""
    added, skipped, errors = 0, 0, []
    keyfield = {"customer-estimates": "Document Number", "customer-invoices": "Invoice Number",
                "vendor-estimates": "PO Number", "vendor-invoices": "Vendor Invoice Number"}[key]
    groups = {}
    for n, r in enumerate(rows, 2):
        groups.setdefault(r[keyfield].strip(), []).append((n, r))

    def find(model, code):
        return ctx.db.execute(ctx.scope(select(model), model)
                              .where(model.code == code)).scalar_one_or_none()

    for doc_no, items in groups.items():
        n0, first = items[0]
        try:
            lines = []
            for n, r in items:
                m = find(M.Material, r["Material Code"].strip().upper())
                if not m:
                    raise HTTPException(422, f"material {r['Material Code']} is not on file")
                price_col = "Unit Price" if "Unit Price" in r else "Cost Price"
                lines.append({"material_id": m.id,
                              "qty": _dec(r["Quantity"], "Quantity", n),
                              "price": _dec(r.get(price_col), price_col, n)})
            if key in ("customer-estimates", "customer-invoices"):
                c = find(M.Customer, first["Customer Code"].strip())
                if not c:
                    raise HTTPException(422, f"customer {first['Customer Code']} is not on file")
                if ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice)
                                  .where(M.Invoice.doc_no == doc_no)).scalar_one_or_none():
                    skipped += 1
                    continue
                datecol = "Document Date" if key == "customer-estimates" else "Invoice Date"
                add_invoice(S.InvoiceIn(doc_no=doc_no,
                    doc_type="PRO" if key == "customer-estimates" else "TAX",
                    doc_date=_date(first[datecol], datecol, n0),
                    due_date=_date(first.get("Due Date"), "Due Date", n0, False),
                    customer_id=c.id,
                    gstin=(first.get("Recipient GSTIN") or "").strip().upper() or None,
                    pos_state=(first.get("Place of Supply") or "").strip() or None,
                    po_no=(first.get("PO Number") or first.get("Their Reference") or "").strip() or None,
                    po_date=_date(first.get("PO Date"), "PO Date", n0, False),
                    reverse_chg=(first.get("Reverse Charge") or "N").strip().upper() or "N",
                    lines=lines), ctx)
            elif key == "vendor-estimates":
                v = find(M.Vendor, first["Vendor Code"].strip())
                if not v:
                    raise HTTPException(422, f"vendor {first['Vendor Code']} is not on file")
                if ctx.db.execute(ctx.scope(select(M.PurchaseOrder), M.PurchaseOrder)
                                  .where(M.PurchaseOrder.doc_no == doc_no)).scalar_one_or_none():
                    skipped += 1
                    continue
                ship = (first.get("Delivery Address") or "").strip()
                add_po(S.PoIn(doc_no=doc_no, doc_date=_date(first["PO Date"], "PO Date", n0),
                    req_date=_date(first.get("Required By"), "Required By", n0, False),
                    vendor_id=v.id,
                    gstin=(first.get("Vendor GSTIN") or "").strip().upper() or None,
                    bill_addr=(first.get("Billing Address") or "").strip() or None,
                    ship_same=not ship, ship_addr=ship or None, lines=lines), ctx)
            else:
                v = find(M.Vendor, first["Vendor Code"].strip())
                if not v:
                    raise HTTPException(422, f"vendor {first['Vendor Code']} is not on file")
                po = None
                if (first.get("PO Number") or "").strip():
                    po = ctx.db.execute(ctx.scope(select(M.PurchaseOrder), M.PurchaseOrder)
                        .where(M.PurchaseOrder.doc_no == first["PO Number"].strip())
                        ).scalar_one_or_none()
                add_vinv(S.VendorInvoiceIn(doc_no=doc_no,
                    doc_date=_date(first["Invoice Date"], "Invoice Date", n0),
                    due_date=_date(first.get("Due Date"), "Due Date", n0, False),
                    vendor_id=v.id, po_id=po.id if po else None, lines=lines), ctx)
            added += 1
        except HTTPException as e:
            errors.append(f"{doc_no}: {e.detail}")
        except Exception as e:
            errors.append(f"{doc_no}: {e}")
    return added, skipped, errors
