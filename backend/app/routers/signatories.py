"""Directors' signature images, printed on customer invoices.

  GET    /signatories                     every signatory with its image, and the settings
  POST   /signatories                     add one (name, designation, image, on_invoices)
  PUT    /signatories/{id}                change name, designation, on_invoices, or the image
  DELETE /signatories/{id}
  PUT    /signatories/settings            print on tax invoices / on proforma invoices

At most two signatories print at once: one director, or both. The image is
cleaned on upload (paper made transparent, trimmed) so it sits on the invoice
without a box around it. It is a picture of a signature, not a Digital
Signature Certificate: the PDF is not cryptographically signed.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from .. import models as M
from ..deps import Ctx, need
from ..signature import clean, SignatureError

router = APIRouter(prefix="/signatories", tags=["signatories"])
MAX_PRINTED = 2


class SignatoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    designation: str = Field("Director", min_length=1, max_length=80)
    image: str | None = None              # data URI; required when adding
    on_invoices: bool = False


class SigSettingsIn(BaseModel):
    sig_on_tax: bool = True
    sig_on_pro: bool = True


def _out(s: M.Signatory) -> dict:
    return {"id": s.id, "name": s.name, "designation": s.designation, "image": s.image,
            "on_invoices": s.on_invoices, "sort_order": s.sort_order,
            "uploaded_by": s.uploaded_by, "uploaded_at": s.uploaded_at}


def _all(ctx):
    return ctx.db.execute(ctx.scope(select(M.Signatory), M.Signatory)
                          .order_by(M.Signatory.sort_order, M.Signatory.id)).scalars().all()


def _check_limit(ctx, turning_on_id=None):
    on = [s for s in _all(ctx) if s.on_invoices and s.id != turning_on_id]
    if len(on) >= MAX_PRINTED:
        names = " and ".join(s.name for s in on)
        raise HTTPException(409, f"{names} already sign invoices. At most two signatures "
                                 "print; untick one of them first.")


def _image(raw):
    try:
        return clean(raw)
    except SignatureError as e:
        raise HTTPException(422, str(e))


@router.get("")
def list_signatories(ctx: Ctx = Depends(need("signatures"))):
    t = ctx.tenant
    return {"signatories": [_out(s) for s in _all(ctx)],
            "settings": {"sig_on_tax": bool(t.sig_on_tax), "sig_on_pro": bool(t.sig_on_pro)},
            "max_printed": MAX_PRINTED}


@router.post("", status_code=201)
def add_signatory(body: SignatoryIn, ctx: Ctx = Depends(need("signatures"))):
    if not body.image:
        raise HTTPException(422, "Upload the signature image")
    if body.on_invoices:
        _check_limit(ctx)
    n = ctx.db.execute(select(func.coalesce(func.max(M.Signatory.sort_order), 0))
                       .where(M.Signatory.tenant_id == ctx.tenant.id)).scalar_one()
    s = M.Signatory(tenant_id=ctx.tenant.id, name=body.name.strip(),
                    designation=body.designation.strip(), image=_image(body.image),
                    on_invoices=body.on_invoices, sort_order=n + 1,
                    uploaded_by=ctx.user.name)
    ctx.db.add(s)
    ctx.db.commit()
    ctx.db.refresh(s)
    return _out(s)


@router.put("/settings")
def put_settings(body: SigSettingsIn, ctx: Ctx = Depends(need("signatures"))):
    ctx.tenant.sig_on_tax, ctx.tenant.sig_on_pro = body.sig_on_tax, body.sig_on_pro
    ctx.db.commit()
    return {"sig_on_tax": body.sig_on_tax, "sig_on_pro": body.sig_on_pro}


@router.put("/{sid}")
def edit_signatory(sid: int, body: SignatoryIn, ctx: Ctx = Depends(need("signatures"))):
    s = ctx.get(M.Signatory, sid)
    if not s:
        raise HTTPException(404, "No such signatory")
    if body.on_invoices and not s.on_invoices:
        _check_limit(ctx, turning_on_id=s.id)
    s.name, s.designation = body.name.strip(), body.designation.strip()
    s.on_invoices = body.on_invoices
    if body.image:
        s.image, s.uploaded_by = _image(body.image), ctx.user.name
        s.uploaded_at = func.now()
    ctx.db.commit()
    ctx.db.refresh(s)
    return _out(s)


@router.delete("/{sid}", status_code=204)
def del_signatory(sid: int, ctx: Ctx = Depends(need("signatures"))):
    s = ctx.get(M.Signatory, sid)
    if not s:
        raise HTTPException(404, "No such signatory")
    ctx.db.delete(s)
    ctx.db.commit()


def printed_signatures(ctx, doc_type: str) -> list[dict]:
    """The signatures a document of this type carries (used by the print router)."""
    t = ctx.tenant
    if (doc_type == "PRO" and not t.sig_on_pro) or (doc_type != "PRO" and not t.sig_on_tax):
        return []
    return [{"name": s.name, "designation": s.designation, "image": s.image}
            for s in _all(ctx) if s.on_invoices][:MAX_PRINTED]
