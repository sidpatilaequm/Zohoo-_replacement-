"""E-mailing documents through the organisation's SMTP server.

  GET  /email/draft?kind=invoice|po&id=N   a ready-to-edit mail: from, to, subject,
                                            body, and the PDF that will be attached
  POST /email/send                          send it, as the user edited it
  GET  /email/log?kind=..&id=..             what was sent for a document, newest first
  POST /org/smtp/test                       connect and send a real test message

A proforma, a tax invoice and a purchase order each attach their own PDF, made by
the same code as the Print buttons, so the attachment is exactly what View shows.
"""
import base64
import binascii
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from .. import models as M, schemas as S, mailer
from ..deps import Ctx, current, need
from ..service import invoice_tax, po_tax
from ..printing import _bank_line, _inr, _d
from .printing import invoice_pdf, po_pdf, _org

router = APIRouter(tags=["email"])

LABEL = {"TAX": "Tax Invoice", "PRO": "Proforma Invoice", "PO": "Purchase Order"}
PERM = {"TAX": "saved", "PRO": "proforma", "PO": "po"}


def _load(ctx: Ctx, kind: str, doc_id: int):
    """The document, its kind code (TAX | PRO | PO) and the party it goes to."""
    if kind == "invoice":
        d = ctx.get(M.Invoice, doc_id)
        if not d:
            raise HTTPException(404, "No such invoice")
        code = d.doc_type
        party, pkind = d.customer, "CUSTOMER"
    elif kind == "po":
        d = ctx.get(M.PurchaseOrder, doc_id)
        if not d:
            raise HTTPException(404, "No such purchase order")
        code, party, pkind = "PO", d.vendor, "VENDOR"
    else:
        raise HTTPException(422, "kind must be invoice or po")
    ctx.require(PERM[code])
    return d, code, party, pkind


def _party_emails(ctx, party, pkind) -> list[str]:
    """The party's own address first, then its contacts' (primary contact first)."""
    out = [party.email] if getattr(party, "email", None) else []
    contacts = ctx.db.execute(ctx.scope(select(M.PartyContact), M.PartyContact).where(
        M.PartyContact.party_kind == pkind, M.PartyContact.party_id == party.id)).scalars()
    for c in sorted(contacts, key=lambda c: not c.is_primary):
        if c.email:
            out.append(c.email)
    seen, uniq = set(), []
    for a in out:
        if a.lower() not in seen:
            seen.add(a.lower()); uniq.append(a)
    return uniq


def _default_text(ctx, d, code, party):
    t = ctx.tenant
    signer = t.smtp_from_name or t.name
    subject = f"{LABEL[code]} {d.doc_no} from {t.name}"
    if code == "PO":
        total = po_tax(ctx, d).rounded
        body = (f"Dear {party.name},\n\n"
                f"Please find attached our Purchase Order {d.doc_no} dated {_d(d.doc_date)} "
                f"for INR {_inr(total)}"
                + (f", required by {_d(d.req_date)}" if d.req_date else "") + ".\n\n"
                "Please quote the PO number on your invoice and delivery documents, and "
                "confirm acceptance of the order by reply.\n\n"
                f"Regards,\n{signer}")
        return subject, body
    tot = invoice_tax(ctx, d)
    lead = (f"Please find attached {LABEL[code]} {d.doc_no} dated {_d(d.doc_date)} "
            f"for INR {_inr(tot.rounded)}"
            + (f", due on {_d(d.due_date)}" if d.due_date and code == "TAX" else "") + ".")
    if code == "PRO":
        lead += " The tax invoice will follow once payment is received."
    notes = "\n".join(x.strip() for x in (t.inv_notes or "").splitlines() if x.strip())
    bank = _bank_line(_org(ctx))
    body = f"Dear {party.name},\n\n{lead}\n\n"
    if notes:
        body += notes + "\n\n"
    if bank:
        body += f"Payment details:\n{bank}\n\n"
    body += f"Thanks for your business.\n\nRegards,\n{signer}"
    return subject, body


def _log_rows(ctx, code=None, doc_id=None, limit=20):
    q = ctx.scope(select(M.EmailLog), M.EmailLog)
    if code:
        q = q.where(M.EmailLog.doc_kind.in_(code) if isinstance(code, (list, tuple))
                    else M.EmailLog.doc_kind == code)
    if doc_id is not None:
        q = q.where(M.EmailLog.doc_id == doc_id)
    rows = ctx.db.execute(q.order_by(M.EmailLog.id.desc()).limit(limit)).scalars()
    return [{"id": r.id, "doc_kind": r.doc_kind, "doc_no": r.doc_no, "sent_at": r.sent_at,
             "sent_by": r.sent_by, "from": r.from_addr, "to": r.to_addrs, "cc": r.cc_addrs,
             "subject": r.subject, "attachments": r.attachments, "status": r.status,
             "error": r.error} for r in rows]


@router.get("/email/draft")
def draft(kind: str, id: int, variant: str | None = None, ctx: Ctx = Depends(current)):
    d, code, party, pkind = _load(ctx, kind, id)
    t = ctx.tenant
    subject, body = _default_text(ctx, d, code, party)
    emails = _party_emails(ctx, party, pkind)
    _, filename = invoice_pdf(ctx, d, variant) if kind == "invoice" else po_pdf(ctx, d, variant)
    problems = mailer.smtp_problems(t)
    return {"kind": kind, "id": d.id, "doc_kind": code, "doc_label": LABEL[code],
            "doc_no": d.doc_no, "party": party.name,
            "from": mailer.from_header(t) if t.smtp_from_email else None,
            "reply_to": t.smtp_reply_to,
            "to": emails[:1], "suggestions": emails,
            "cc": [], "bcc": [t.smtp_bcc] if t.smtp_bcc else [],
            "subject": subject, "body": body,
            "attachment": filename,
            "smtp_ready": not problems, "smtp_problems": problems,
            "history": _log_rows(ctx, code, d.id, limit=5)}


def _extra_files(items):
    out = []
    for a in items:
        try:
            data = base64.b64decode(a.content_base64.split("base64,")[-1], validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, f"{a.filename} could not be read")
        name = a.filename.replace("/", "_").replace("\\", "_")
        out.append((name, data, a.content_type or "application/octet-stream"))
    return out


@router.post("/email/send")
def send(body: S.DocMailIn, ctx: Ctx = Depends(current)):
    import re
    addresses = body.to + body.cc + body.bcc
    if not body.to or any(
        not re.fullmatch(r"[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+", a.strip())
        for a in addresses
    ):
        raise HTTPException(422, "Enter valid email addresses for To, Cc and Bcc")
    d, code, party, _ = _load(ctx, body.kind, body.id)
    t = ctx.tenant
    attachments = []
    if body.attach_pdf:
        pdf, name = (invoice_pdf(ctx, d, body.variant) if body.kind == "invoice"
                     else po_pdf(ctx, d, body.variant))
        attachments.append((name, pdf, "application/pdf"))
    attachments += _extra_files(body.extra)
    log = M.EmailLog(tenant_id=t.id, doc_kind=code, doc_id=d.id, doc_no=d.doc_no,
                     sent_by=ctx.user.name, from_addr=mailer.from_header(t),
                     to_addrs=", ".join(body.to), cc_addrs=", ".join(body.cc) or None,
                     bcc_addrs=", ".join(body.bcc) or None, subject=body.subject,
                     attachments=", ".join(a[0] for a in attachments) or None)
    try:
        msg = mailer.build(t, to=body.to, cc=body.cc, bcc=body.bcc, subject=body.subject,
                           body=body.body, attachments=attachments)
        refused = mailer.deliver(t, msg)
    except mailer.MailError as e:
        log.status, log.error = "FAILED", str(e)
        ctx.db.add(log); ctx.db.commit()
        raise HTTPException(502, str(e))
    log.status = "SENT"
    if refused:
        log.error = "Refused: " + "; ".join(f"{a} ({r})" for a, r in refused.items())
    ctx.db.add(log); ctx.db.commit()
    return {"ok": True, "doc_no": d.doc_no, "to": body.to, "cc": body.cc,
            "attachments": [a[0] for a in attachments], "refused": refused,
            "message_id": msg["Message-ID"], "log_id": log.id}


@router.get("/email/log")
def email_log(kind: str | None = None, id: int | None = None, ctx: Ctx = Depends(current)):
    if kind and id is not None:
        _, code, _, _ = _load(ctx, kind, id)
        return _log_rows(ctx, code, id, limit=50)
    visible = [c for c, p in PERM.items() if p in ctx.perms]
    if "org" in ctx.perms:
        visible.append("TEST")
    return _log_rows(ctx, visible, limit=100)


@router.post("/org/smtp/test")
def smtp_test(body: S.SmtpTestIn, ctx: Ctx = Depends(need("org"))):
    """Make a real connection with the saved settings and send a short message."""
    t = ctx.tenant
    log = M.EmailLog(tenant_id=t.id, doc_kind="TEST", sent_by=ctx.user.name,
                     from_addr=mailer.from_header(t), to_addrs=body.to,
                     subject=f"Test mail from {t.name}")
    try:
        msg = mailer.build(t, to=[body.to], subject=log.subject,
                           body=(f"This is a test message from Aequm Billing for {t.name}.\n\n"
                                 f"It was sent through {t.smtp_host}:{t.smtp_port} "
                                 f"({t.smtp_encryption or 'STARTTLS'}) as "
                                 f"{t.smtp_from_email}.\nIf you can read this, invoices and "
                                 "purchase orders can be e-mailed from the application."))
        mailer.deliver(t, msg)
    except mailer.MailError as e:
        log.status, log.error = "FAILED", str(e)
        ctx.db.add(log); ctx.db.commit()
        raise HTTPException(502, str(e))
    log.status = "SENT"
    ctx.db.add(log); ctx.db.commit()
    return {"ok": True, "to": body.to,
            "note": f"Sent through {t.smtp_host}. Check the inbox (and spam) of {body.to}."}
