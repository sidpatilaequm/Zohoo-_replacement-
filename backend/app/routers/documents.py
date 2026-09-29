"""Documents kept against invoices (v4.4).

Any number of supporting files can be uploaded against a customer (sales)
invoice or a vendor (purchase) invoice — the vendor's own PDF, a signed
delivery challan, a proof of payment, correspondence — and listed, opened,
downloaded and deleted from the invoice registers.

Access follows the invoice: sales documents need the Invoice or Saved
Invoices screen, purchase documents need Vendor Invoices. A view-only group
(the auditor) can list and open them but not upload or delete, because that
is refused at the HTTP verb for every route.

The bytes are stored in MySQL (doc_files.content), so the nightly
mysqldump that backs up the invoices backs up their documents too.
"""
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select, func
from .. import models as M
from ..deps import Ctx, need_any

router = APIRouter(tags=["documents"])

MAX_BYTES = 10 * 1024 * 1024
MAX_PER_INVOICE = 25
SALES = ("invoice", "saved")
PURCHASE = ("vinv",)

# What may be uploaded, by extension. The stored content type comes from
# this table, never from the browser, so a file is always served as what its
# extension says it is. HTML and SVG are deliberately absent: they could run
# script when opened.
TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".eml": "message/rfc822",
    ".msg": "application/vnd.ms-outlook",
    ".zip": "application/zip",
}

VIEWABLE = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "text/plain",
}

ACCEPT = ",".join(sorted(TYPES))


def _require_any(ctx: Ctx, perms):
    if not any(p in ctx.perms for p in perms):
        raise HTTPException(
            403,
            "Your group does not have access to " + " or ".join(perms),
        )


def _out(d: M.DocFile) -> dict:
    return {
        "id": d.id,
        "filename": d.filename,
        "content_type": d.content_type,
        "size": d.size_bytes,
        "notes": d.notes,
        "uploaded_by": d.uploaded_by,
        "at": d.created_at.isoformat() if d.created_at else None,
        "viewable": d.content_type in VIEWABLE,
    }


def counts(ctx: Ctx, column) -> dict[int, int]:
    """{invoice id: number of documents} for the whole tenant, in one query,
    so the registers can show a count on every row."""
    rows = ctx.db.execute(
        select(column, func.count())
        .where(
            M.DocFile.tenant_id == ctx.tenant.id,
            column.is_not(None),
        )
        .group_by(column)
    ).all()

    return {k: n for k, n in rows}


def _list(ctx, **owner) -> list[dict]:
    q = select(M.DocFile).where(
        M.DocFile.tenant_id == ctx.tenant.id
    )

    for k, v in owner.items():
        q = q.where(getattr(M.DocFile, k) == v)

    return [
        _out(d)
        for d in ctx.db.execute(
            q.order_by(M.DocFile.id)
        ).scalars()
    ]


async def _save(
    ctx,
    file: UploadFile,
    notes: str | None,
    **owner,
) -> dict:
    name = (
        (file.filename or "")
        .strip()
        .replace("\\", "/")
        .split("/")[-1][:200]
    )

    if not name:
        raise HTTPException(422, "The file has no name")

    ext = (
        "." + name.rsplit(".", 1)[-1].lower()
        if "." in name
        else ""
    )

    ctype = TYPES.get(ext)

    if not ctype:
        raise HTTPException(
            422,
            "That type of file cannot be kept against an invoice. "
            "Use PDF, an image (JPG, PNG, WebP, GIF, TIFF, HEIC), "
            "Word, Excel, CSV, text, an e-mail (.eml, .msg) or a ZIP.",
        )

    data = await file.read()

    if not data:
        raise HTTPException(422, f"{name} is empty")

    if len(data) > MAX_BYTES:
        raise HTTPException(
            413,
            f"{name} is larger than {MAX_BYTES // (1024 * 1024)} MB",
        )

    n = ctx.db.execute(
        select(func.count())
        .select_from(M.DocFile)
        .where(
            M.DocFile.tenant_id == ctx.tenant.id,
            *[
                getattr(M.DocFile, k) == v
                for k, v in owner.items()
            ],
        )
    ).scalar_one()

    if n >= MAX_PER_INVOICE:
        raise HTTPException(
            409,
            f"An invoice can hold {MAX_PER_INVOICE} documents. "
            "Delete one before adding another.",
        )

    d = M.DocFile(
        tenant_id=ctx.tenant.id,
        filename=name,
        content_type=ctype,
        size_bytes=len(data),
        content=data,
        notes=(notes or "").strip()[:200] or None,
        uploaded_by=ctx.user.name,
        **owner,
    )

    ctx.db.add(d)
    ctx.db.commit()
    ctx.db.refresh(d)

    return _out(d)


# ------------------------------------------------------------ sales invoices
def _invoice(ctx, iid):
    inv = ctx.get(M.Invoice, iid)

    if not inv:
        raise HTTPException(404, "No such invoice")

    return inv


@router.get("/invoices/{iid}/documents")
def invoice_documents(
    iid: int,
    ctx: Ctx = Depends(need_any(*SALES)),
):
    _invoice(ctx, iid)
    return _list(ctx, invoice_id=iid)


@router.post("/invoices/{iid}/documents", status_code=201)
async def add_invoice_document(
    iid: int,
    file: UploadFile = File(...),
    notes: str | None = Form(None),
    ctx: Ctx = Depends(need_any(*SALES)),
):
    _invoice(ctx, iid)
    return await _save(ctx, file, notes, invoice_id=iid)


# --------------------------------------------------------- purchase invoices
def _vinv(ctx, vid):
    vi = ctx.get(M.VendorInvoice, vid)

    if not vi:
        raise HTTPException(404, "No such vendor invoice")

    return vi


@router.get("/vendor-invoices/{vid}/documents")
def vinv_documents(
    vid: int,
    ctx: Ctx = Depends(need_any(*PURCHASE)),
):
    _vinv(ctx, vid)
    return _list(ctx, vinv_id=vid)


@router.post("/vendor-invoices/{vid}/documents", status_code=201)
async def add_vinv_document(
    vid: int,
    file: UploadFile = File(...),
    notes: str | None = Form(None),
    ctx: Ctx = Depends(need_any(*PURCHASE)),
):
    _vinv(ctx, vid)
    return await _save(ctx, file, notes, vinv_id=vid)


# --------------------------------------------------------- one document
def _doc(ctx, did) -> M.DocFile:
    d = ctx.get(M.DocFile, did)

    if not d:
        raise HTTPException(404, "No such document")

    _require_any(
        ctx,
        SALES if d.invoice_id else PURCHASE,
    )

    return d


@router.get("/documents/{did}/file")
def document_file(
    did: int,
    inline: bool = Query(False),
    ctx: Ctx = Depends(need_any(*SALES, *PURCHASE)),
):
    d = _doc(ctx, did)

    how = (
        "inline"
        if inline and d.content_type in VIEWABLE
        else "attachment"
    )

    ascii_name = (
        d.filename
        .encode("ascii", "replace")
        .decode()
        .replace('"', "'")
        .replace("?", "_")
    )

    return Response(
        content=d.content,
        media_type=d.content_type,
        headers={
            "Content-Disposition": (
                f"{how}; filename=\"{ascii_name}\"; "
                f"filename*=UTF-8''{quote(d.filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/documents/{did}", status_code=204)
def delete_document(
    did: int,
    ctx: Ctx = Depends(need_any(*SALES, *PURCHASE)),
):
    d = _doc(ctx, did)

    ctx.db.delete(d)
    ctx.db.commit()