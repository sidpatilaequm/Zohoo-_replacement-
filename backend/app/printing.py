"""PDF print-outs: purchase order, customer invoice and customer receipt.

Every document is drawn by one function, `render(kind, doc, variant)`, and
the layout differs by *variant*:

  TRADING     goods — HSN column, quantity and unit, batch line where the
              material is batch managed, a "deliver to" block, and terms
              about goods, transport and returns.
  NONTRADING  services and IT products — SAC column, "Units" instead of
              quantity, service period on the header, no delivery block,
              and terms about services, licences and SLAs.

The variant defaults to the organisation's own company type, but a caller
may ask for the other one, so a services company that occasionally sells
hardware can still print a goods invoice.

Numbers come from the same tax engine as the screen, so the PDF never
disagrees with what the user saw before pressing print.
"""
import base64, io, re
from datetime import date
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image, KeepTogether)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from .tax import hsn_summary, in_words

VARIANTS = ("TRADING", "NONTRADING")
INK, MUTED, LINE, SOFT = (colors.HexColor("#1A1A1F"), colors.HexColor("#6E6E68"),
                          colors.HexColor("#D2D2CA"), colors.HexColor("#F2F2EE"))
ACCENT = colors.HexColor("#2E5E4E")

_base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.6, leading=11, textColor=INK)
S = {
    "body": _base,
    "small": ParagraphStyle("s", _base, fontSize=7.4, leading=9.4, textColor=MUTED),
    "label": ParagraphStyle("l", _base, fontSize=6.8, leading=9, textColor=MUTED,
                            spaceAfter=1),
    "h1": ParagraphStyle("h1", _base, fontName="Helvetica-Bold", fontSize=15, leading=18,
                         textColor=ACCENT),
    "h2": ParagraphStyle("h2", _base, fontName="Helvetica-Bold", fontSize=10.5, leading=13),
    "bold": ParagraphStyle("bd", _base, fontName="Helvetica-Bold"),
    "right": ParagraphStyle("r", _base, alignment=TA_RIGHT),
    "rightb": ParagraphStyle("rb", _base, alignment=TA_RIGHT, fontName="Helvetica-Bold"),
    "center": ParagraphStyle("c", _base, alignment=TA_CENTER),
    "th": ParagraphStyle("th", _base, fontName="Helvetica-Bold", fontSize=7.4, leading=9,
                         textColor=colors.white),
    "thr": ParagraphStyle("thr", _base, fontName="Helvetica-Bold", fontSize=7.4, leading=9,
                          textColor=colors.white, alignment=TA_RIGHT),
}


def _esc(text):
    text = "" if text is None else str(text)
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\n", "<br/>"))


def _p(text, style="body", raw=False):
    """Paragraph. Values are escaped; pass raw=True for strings that carry markup
    (which must escape their own data with _esc)."""
    return Paragraph(text if raw else _esc(text), S[style])


def _lv(label, value):
    """grey label, then value — for the key: value rows in party blocks."""
    return _p(f"<font color='#6E6E68'>{_esc(label)}</font> {_esc(value)}", raw=True)


RUPEE = "Rs."


def _inr(x) -> str:
    """Indian grouping: 12,34,567.89"""
    d = Decimal(str(x or 0)).quantize(Decimal("0.01"))
    neg, d = d < 0, abs(d)
    whole, frac = str(d).split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return ("-" if neg else "") + whole + "." + frac


def _qty(x) -> str:
    d = Decimal(str(x or 0))
    return str(d.quantize(Decimal("1"))) if d == d.to_integral() else str(d.normalize())


def _d(x) -> str:
    if not x:
        return "—"
    if isinstance(x, str):
        x = date.fromisoformat(x[:10])
    return x.strftime("%d-%b-%Y")


def _logo(data_url, size=16 * mm):
    if not data_url or "base64," not in data_url:
        return None
    try:
        raw = base64.b64decode(data_url.split("base64,", 1)[1])
        img = Image(io.BytesIO(raw))
        ratio = img.imageWidth / float(img.imageHeight or 1)
        img.drawHeight, img.drawWidth = size, size * ratio
        return img
    except Exception:
        return None


def _addr_block(title, name, lines, extra=()):
    """A titled party block: name in bold, address lines, then key: value rows."""
    body = [_p(title, "label"), _p(name, "bold")]
    for ln in lines:
        if ln and str(ln).strip():
            body.append(_p(ln))
    for k, v in extra:
        if v:
            body.append(_lv(k, v))
    return body


def _kv_table(pairs, col_w):
    rows = [[_p(k, "label"), _p(v or "—")] for k, v in pairs]
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _header(story, org, title, subtitle, meta_pairs, width):
    """Organisation masthead on the left, document title and meta on the right."""
    left = []
    lg = _logo(org.get("logo"))
    if lg:
        left.append(lg)
    left += [_p(org["name"], "h2"),
             _p("\n".join(x for x in [org.get("addr"), " ".join(
                 y for y in [org.get("city"), org.get("pin")] if y)] if x)),
             _p(f"GSTIN {org.get('gstin') or '—'}   ·   PAN {org.get('pan') or '—'}   ·   "
                f"State {org.get('state') or '—'}", "small")]
    right = [_p(title, "h1"), _p(subtitle, "small"), Spacer(1, 3),
             _kv_table(meta_pairs, [28 * mm, 42 * mm])]
    t = Table([[left, right]], colWidths=[width * 0.56, width * 0.44])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [t, Spacer(1, 6)]


def _parties(story, blocks, width):
    n = len(blocks)
    t = Table([blocks], colWidths=[width / n] * n)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                           ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                           ("LEFTPADDING", (0, 0), (-1, -1), 7),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 7)]))
    story += [t, Spacer(1, 7)]


def _lines_table(story, totals, variant, width, price_label="Rate", batch=None):
    """The line grid. Trading shows Qty/UoM per line; non-trading shows Units."""
    intra, goods = totals["intra"], variant == "TRADING"
    code_lbl = "HSN" if goods else "SAC"
    qty_lbl, unit_lbl = ("Qty", "UoM") if goods else ("Units", "Per")
    head = ["#", "Description", code_lbl, qty_lbl, unit_lbl, price_label, "Taxable value"]
    head += ["CGST", "SGST"] if intra else ["IGST"]
    head += ["Line total"]
    rows = [[_p(h, "thr" if i >= 3 and h not in ("UoM", "Per") else "th")
             for i, h in enumerate(head)]]
    for L in totals["lines"]:
        descr = L["descr"]
        if goods and batch and batch.get(L.get("material_id")):
            descr += f"\nBatch {batch[L['material_id']]}"
        descr_p = [_p(descr), _p(L["code"], "small")]
        def _tax(v, pct):
            return _p(f"{_inr(v)}<br/><font size='6.5' color='#6E6E68'>@ {_qty(pct)}%</font>",
                      "right", raw=True)
        r = [_p(L["line_no"], "center"), descr_p, _p(L["hsn"], "center"),
             _p(_qty(L["qty"]), "right"), _p(L["uom"], "center"),
             _p(_inr(L["price"]), "right"), _p(_inr(L["amount"]), "right")]
        if intra:
            r += [_tax(L["cgst"], L["rate"] / 2), _tax(L["sgst"], L["rate"] / 2)]
        else:
            r += [_tax(L["igst"], L["rate"])]
        r += [_p(_inr(L["amount"] + L["cgst"] + L["sgst"] + L["igst"]), "rightb")]
        rows.append(r)
    fixed = [7, 17, 11, 10, 19, 22] + ([19, 19] if intra else [22]) + [23]
    fixed = [w * mm for w in fixed]
    widths = [fixed[0]] + [width - sum(fixed)] + fixed[1:]
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                           ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    story += [t, Spacer(1, 6)]


def _hsn_and_totals(story, totals, variant, width, words_label="Amount in words",
                    extra_rows=()):
    intra, goods = totals["intra"], variant == "TRADING"
    # HSN / SAC summary on the left
    hs = totals["hsn"]
    hh = [("HSN" if goods else "SAC"), "Taxable", "Rate"]
    hh += ["CGST", "SGST"] if intra else ["IGST"]
    hh += ["Total"]
    hrows = [[_p(h, "th" if i == 0 else "thr") for i, h in enumerate(hh)]]
    for h in hs:
        r = [_p(h["hsn"]), _p(_inr(h["taxable"]), "right"), _p(f"{_qty(h['rate'])}%", "right")]
        r += [_p(_inr(h["cgst"]), "right"), _p(_inr(h["sgst"]), "right")] if intra \
            else [_p(_inr(h["igst"]), "right")]
        r += [_p(_inr(h["total_value"]), "right")]
        hrows.append(r)
    hsn_t = Table(hrows, colWidths=[18 * mm, 22 * mm, 12 * mm] + ([18 * mm, 18 * mm] if intra else [20 * mm]) + [22 * mm])
    hsn_t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), MUTED),
                               ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
                               ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                               ("LEFTPADDING", (0, 0), (-1, -1), 4),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    # totals on the right
    trows = [["Taxable value", _inr(totals["taxable"])]]
    if intra:
        trows += [["CGST", _inr(totals["cgst"])], ["SGST", _inr(totals["sgst"])]]
    else:
        trows += [["IGST", _inr(totals["igst"])]]
    if totals["tax"] == 0:
        trows = [["Taxable value", _inr(totals["taxable"])], ["GST", "nil"]]
    if abs(totals["roundoff"]) >= 0.005:
        trows.append(["Round off", _inr(totals["roundoff"])])
    trows += list(extra_rows)
    grand = trows[-1][0] if extra_rows else None
    trows.append(["TOTAL", f"{RUPEE} " + _inr(totals["rounded"])])
    tt = Table([[_p(k, "rightb" if k == "TOTAL" else "right"),
                 _p(v, "rightb" if k == "TOTAL" else "right")] for k, v in trows],
               colWidths=[34 * mm, 34 * mm])
    tt.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 0.8, INK),
                            ("BACKGROUND", (0, -1), (-1, -1), SOFT),
                            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    left = [_p("Tax summary", "label"), hsn_t] if hs else [_p("")]
    outer = Table([[left, tt]], colWidths=[width - 70 * mm, 70 * mm])
    outer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [outer, Spacer(1, 4),
              _p(f"<font color='#6E6E68'>{_esc(words_label)}:</font> "
                 f"<b>Rupees {in_words(totals['rounded'])} only</b>", raw=True),
              Spacer(1, 8)]


def _footer(story, left_blocks, right_blocks, width, sign_for):
    left = [_p("Terms", "label")] + left_blocks
    right = list(right_blocks) + [Spacer(1, 22), _p(f"For {sign_for}", "bold"),
                                  Spacer(1, 14), _p("Authorised signatory", "small")]
    t = Table([[left, right]], colWidths=[width * 0.58, width * 0.42])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    story.append(KeepTogether(t))


def _doc(buf, title):
    return SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                             topMargin=13 * mm, bottomMargin=14 * mm, title=title)


def _watermark(canvas, doc):
    text = getattr(doc, "watermark", None)
    if not text:
        return
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 64)
    canvas.setFillColor(colors.Color(0.62, 0.17, 0.13, alpha=0.18))
    canvas.translate(A4[0] / 2, A4[1] / 2)
    canvas.rotate(35)
    canvas.drawCentredString(0, 0, text)
    canvas.restoreState()


def _page_no(canvas, doc):
    _watermark(canvas, doc)
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {doc.page}")
    canvas.drawString(14 * mm, 8 * mm, doc.title)
    canvas.restoreState()


def _build(buf, title, story, watermark=None):
    d = _doc(buf, title)
    d.watermark = watermark
    d.build(story, onFirstPage=_page_no, onLaterPages=_page_no)


TERMS = {
    "PO": {
        "TRADING": ["Quote our PO number on the invoice, delivery challan and e-way bill.",
                    "Goods are accepted subject to inspection; shortages or damage will be "
                    "raised as a discrepancy and the line held until released.",
                    "Deliver on or before the required-by date to the delivery address shown.",
                    "Supply batch numbers and expiry where the material is batch managed."],
        "NONTRADING": ["Quote our PO number on the invoice.",
                       "Licences, subscriptions and services are accepted on confirmation of "
                       "activation or completion, not on invoice.",
                       "Service period and SLA as agreed in the order; renewals need a fresh order.",
                       "TDS will be deducted at source where applicable under the Income-tax Act."]},
    "INV": {
        "TRADING": ["Goods once sold will not be taken back except as agreed in writing.",
                    "Ownership passes on payment; risk passes on delivery.",
                    "Interest at 18% p.a. on amounts unpaid after the due date.",
                    "Subject to the jurisdiction of the courts at our registered office."],
        "NONTRADING": ["Services and licences are non-returnable once provisioned.",
                       "Payment within the credit period shown; TDS certificates to be shared "
                       "within the quarter.",
                       "Interest at 18% p.a. on amounts unpaid after the due date.",
                       "Subject to the jurisdiction of the courts at our registered office."]},
}


# ======================================================================
def render_po(org: dict, po: dict, totals: dict, variant: str) -> bytes:
    """org: supplier-of-the-print (us). po: header with vendor, addresses, lines."""
    variant = variant if variant in VARIANTS else "NONTRADING"
    goods = variant == "TRADING"
    buf, story, width = io.BytesIO(), [], A4[0] - 28 * mm
    _header(story, org, "PURCHASE ORDER", "Goods" if goods else "Services and IT products",
            [("PO number", po["doc_no"]), ("PO date", _d(po["doc_date"])),
             ("Required by" if goods else "Service start", _d(po.get("req_date"))),
             ("Status", po.get("status", "OPEN").title()),
             ("Supply", "Intra-state" if totals["intra"] else "Inter-state")], width)
    v = po["vendor"]
    blocks = [_addr_block("Vendor", v["name"], [v.get("addr"), " ".join(
        x for x in [v.get("city"), v.get("pin")] if x)],
        [("GSTIN", po.get("gstin") or "Unregistered"), ("PAN", v.get("pan")),
         ("Email", v.get("email"))])]
    blocks.append(_addr_block("Bill to", "", [po.get("bill_addr")]))
    if goods:
        blocks.append(_addr_block("Deliver to", "", [po.get("ship_addr") or po.get("bill_addr")]))
    _parties(story, blocks, width)
    _lines_table(story, totals, variant, width, price_label="Unit cost")
    _hsn_and_totals(story, totals, variant, width, words_label="Order value in words")
    _footer(story, [_p("• " + t, "small") for t in TERMS["PO"][variant]],
            [_p("Vendor acknowledgement", "label"),
             _p("Please sign and return a copy, or confirm by email, within 3 working days.", "small")],
            width, org["name"])
    _build(buf, f"Purchase order {po['doc_no']}", story)
    return buf.getvalue()


def render_invoice(org: dict, inv: dict, totals: dict, variant: str, received=0) -> bytes:
    variant = variant if variant in VARIANTS else "NONTRADING"
    goods = variant == "TRADING"
    pro = inv["doc_type"] == "PRO"
    title = "PROFORMA INVOICE" if pro else "TAX INVOICE"
    buf, story, width = io.BytesIO(), [], A4[0] - 28 * mm
    meta = [("Invoice no", inv["doc_no"]), ("Invoice date", _d(inv["doc_date"])),
            ("Due date", _d(inv.get("due_date"))),
            ("Place of supply", inv.get("pos_state")),
            ("Reverse charge", "Yes" if inv.get("reverse_chg") == "Y" else "No")]
    if inv.get("po_no"):
        meta.append(("Your PO", f"{inv['po_no']} · {_d(inv.get('po_date'))}"))
    if inv.get("converted_from"):
        meta.append(("Converted from", inv["converted_from"]))
    if inv.get("cancelled"):
        meta.append(("Cancelled", f"{_d(inv.get('cancelled_on'))} — {inv.get('cancel_reason') or ''}"))
    _header(story, org, title,
            ("Supply of goods" if goods else "Supply of services / IT products")
            + (" — not a tax invoice, not valid for input credit" if pro else ""),
            meta, width)
    c, b, sh = inv["customer"], inv["customer"]["bill"], inv["customer"]["ship"]
    blocks = [_addr_block("Bill to", c["name"], [b.get("addr"), " ".join(
        x for x in [b.get("city"), b.get("pin")] if x), f"State {b.get('state')}"],
        [("GSTIN", inv.get("gstin") or ("Unregistered (B2C)" if c.get("party_type") == "B2C" else "—")),
         ("PAN", c.get("pan")), ("Email", c.get("email"))])]
    if goods:
        blocks.append(_addr_block("Ship to", c["name"] if not c.get("ship_same") else "",
                                  [sh.get("addr"), " ".join(x for x in [sh.get("city"), sh.get("pin")] if x),
                                   f"State {sh.get('state')}"] if not c.get("ship_same")
                                  else ["Same as billing address"],
                                  [("Transport", inv.get("transport")), ("E-way bill", inv.get("eway"))]))
    else:
        blocks.append(_addr_block("Service details", "", [],
                                  [("Service period", inv.get("service_period") or "As per order"),
                                   ("Delivery", "Electronic / on-site as agreed")]))
    _parties(story, blocks, width)
    _lines_table(story, totals, variant, width, price_label="Rate", batch=inv.get("batches"))
    extra = []
    if not pro and received:
        extra = [["Received to date", _inr(received)],
                 ["Balance due", _inr(Decimal(str(totals["rounded"])) - Decimal(str(received)))]]
    _hsn_and_totals(story, totals, variant, width, extra_rows=extra)
    right = []
    if org.get("bank"):
        right += [_p("Pay to", "label"), _p(org["bank"])]
    _footer(story, [_p("• " + t, "small") for t in TERMS["INV"][variant]]
            + ([_p("This is a proforma for advance or approval. A tax invoice will follow.", "small")]
               if pro else []),
            right, width, org["name"])
    _build(buf, f"{title.title()} {inv['doc_no']}", story,
           watermark="CANCELLED" if inv.get("cancelled") else None)
    return buf.getvalue()


def render_receipt(org: dict, rc: dict, variant: str) -> bytes:
    """Customer receipt voucher / payment acknowledgement."""
    variant = variant if variant in VARIANTS else "NONTRADING"
    buf, story, width = io.BytesIO(), [], A4[0] - 28 * mm
    _header(story, org, "RECEIPT VOUCHER", "Acknowledgement of payment received",
            [("Receipt no", rc["receipt_no"]), ("Receipt date", _d(rc["pay_date"])),
             ("Mode", rc["mode"]), ("Reference", rc.get("bank_ref") or "—")], width)
    c = rc["customer"]
    _parties(story, [
        _addr_block("Received from", c["name"], [c.get("addr"), " ".join(
            x for x in [c.get("city"), c.get("pin")] if x)],
            [("GSTIN", c.get("gstin")), ("PAN", c.get("pan"))]),
        _addr_block("Credited to", org["name"], [rc.get("bank_acct") or org.get("bank") or "—"],
                    [("Narration", rc.get("narration"))])], width)
    inv = rc["invoice"]
    rows = [[_p(h, "th" if i < 3 else "thr") for i, h in enumerate(
        ["Against invoice", "Invoice date", "Due date", "Invoice total",
         "Received earlier", "This receipt", "Balance"])]]
    rows.append([_p(inv["doc_no"], "bold"), _p(_d(inv["doc_date"])), _p(_d(inv.get("due_date"))),
                 _p(_inr(inv["total"]), "right"), _p(_inr(rc["received_before"]), "right"),
                 _p(_inr(rc["amount"]), "rightb"), _p(_inr(rc["balance_after"]), "right")])
    t = Table(rows, colWidths=[width - 150 * mm, 24 * mm, 24 * mm, 26 * mm, 26 * mm, 26 * mm, 24 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                           ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [t, Spacer(1, 6)]
    amt = Table([[_p("Amount received", "right"), _p(f"{RUPEE} " + _inr(rc["amount"]), "rightb")]],
                colWidths=[width - 60 * mm, 60 * mm])
    amt.setStyle(TableStyle([("BACKGROUND", (1, 0), (1, 0), SOFT),
                             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [amt, Spacer(1, 3),
              _p(f"<font color='#6E6E68'>Amount in words:</font> <b>Rupees {in_words(rc['amount'])} only</b>", raw=True),
              Spacer(1, 8)]
    notes = ["Receipt is subject to realisation of the instrument where paid by cheque.",
             "Any TDS deducted should be supported by Form 16A for the quarter."]
    if variant == "TRADING":
        notes.append("Goods against this invoice were delivered as per the delivery challan referenced on the invoice.")
    _footer(story, [_p("• " + n, "small") for n in notes],
            [_p("Received with thanks", "label"), _p("This is a computer generated receipt.", "small")],
            width, org["name"])
    _build(buf, f"Receipt {rc['receipt_no']}", story)
    return buf.getvalue()
