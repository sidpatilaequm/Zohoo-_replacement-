"""Read a vendor's invoice (PDF or image) and propose the entry.

Three stages, each independent so a failure in one still yields the rest:

1. read_text   — text layer of a PDF via pdfplumber; if that is thin the
                 pages are rasterised (pypdfium2) and OCR'd (tesseract).
                 Images go straight to OCR.
2. parse       — rule-based: GSTINs, invoice number and date, PO number,
                 due date, totals, and line items found by shape (a
                 description followed by HSN, quantity, rate, amount).
                 If ANTHROPIC_API_KEY is set, Claude is asked for the same
                 fields as JSON and its answer is preferred where the rules
                 found nothing or disagree with the printed total.
3. match       — the vendor by GSTIN (then by name), the purchase order by
                 number, each line to a material by code, then by HSN and
                 description similarity. Everything is returned with a
                 confidence so the screen can highlight what to check.

Nothing is written. The result is a proposal for the vendor invoice form.
"""
import io, json, os, re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b")
PAN_RE = re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b")
DATE_RE = re.compile(r"(\d{1,2})[\-/. ]([A-Za-z]{3,9}|\d{1,2})[\-/. ](\d{2,4})|(\d{4})-(\d{2})-(\d{2})")
MONEY = r"(?:₹|Rs\.?|INR)?\s*(\d[\d,]*(?:\.\d{1,2})?)(?![\d.])"
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                      "sep", "oct", "nov", "dec"], 1)}

# ------------------------------------------------------------- reading
def _ocr_image(img):
    try:
        import pytesseract
        return pytesseract.image_to_string(img)
    except Exception as e:  # tesseract missing or unreadable image
        raise RuntimeError(f"OCR is not available in this container ({e.__class__.__name__}). "
                           "Install tesseract-ocr, or upload a PDF with a text layer.")


def read_text(filename: str, data: bytes) -> tuple[str, str]:
    """Returns (text, method) where method is 'text', 'ocr' or 'text+ocr'."""
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        import pdfplumber
        text = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:10]:
                text.append(page.extract_text() or "")
        joined = "\n".join(text)
        if len(joined.strip()) >= 80:
            return joined, "text"
        # scanned — rasterise and OCR
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(data)
        out = []
        for i in range(min(len(doc), 5)):
            img = doc[i].render(scale=2.2).to_pil()
            out.append(_ocr_image(img))
        return joined + "\n" + "\n".join(out), ("text+ocr" if joined.strip() else "ocr")
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    return _ocr_image(img), "ocr"


# ------------------------------------------------------------- parsing
def _dec(s):
    try:
        return Decimal(str(s).replace(",", "").replace("₹", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _date(s):
    if not s:
        return None
    m = DATE_RE.search(s)
    if not m:
        return None
    try:
        if m.group(4):
            return date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
        d, mo, y = m.group(1), m.group(2), m.group(3)
        mo = MONTHS.get(mo[:3].lower()) if mo.isalpha() else int(mo)
        y = int(y) + (2000 if len(y) == 2 else 0)
        return date(y, mo, int(d))
    except (ValueError, TypeError):
        return None


def _after(text, labels, pattern=r"[:\-#.]?\s*([A-Za-z0-9/\-]+)"):
    for lab in labels:
        m = re.search(lab + r"\s*(?:no\.?|number|#)?\s*" + pattern, text, re.I)
        if m:
            return m.group(1)
    return None


def _amount_after(text, labels):
    for lab in labels:
        m = re.search(lab + r"[^0-9₹]{0,25}" + MONEY, text, re.I)
        if m and _dec(m.group(1)) is not None:
            return _dec(m.group(1))
    return None


LINE_RE = re.compile(
    r"^(?:(?P<no>\d{1,2})[\s.)]+)?(?P<descr>[A-Za-z][A-Za-z0-9 ,.()/&+\-]{3,}?)\s+"
    r"(?P<hsn>\d{4,8})\s+(?P<qty>\d+(?:\.\d+)?)\s*(?P<uom>[A-Za-z]{2,4})?\s+"
    r"(?P<rate>\d[\d,]*(?:\.\d+)?)\s+(?:(?P<pct>\d{1,2}(?:\.\d+)?)\s*%?\s+)?"
    r"(?P<amount>\d[\d,]*(?:\.\d+)?)\s*$")


def parse_rules(text: str, our_gstin: str | None = None) -> dict:
    t = re.sub(r"[ \t]+", " ", text)
    gstins = [g for g in dict.fromkeys(GSTIN_RE.findall(t))]
    vendor_gstin = next((g for g in gstins if g != (our_gstin or "")), None)
    inv_no = None
    for pat in (r"(?:tax\s+)?(?:invoice|bill)\s*(?:no\.?|number|#|ref\.?)\s*[:\-.]?\s*([A-Za-z0-9][A-Za-z0-9/\-]*)",
                r"(?:invoice|bill)\s*[:#]\s*([A-Za-z0-9][A-Za-z0-9/\-]*)"):
        m = re.search(pat, t, re.I)
        if m and m.group(1).lower() not in ("date", "no", "number", "to", "invoice", "of"):
            inv_no = m.group(1)
            break
    inv_date = _date(_after(t, [r"invoice date", r"date of invoice", r"bill date", r"\bdate"],
                            r"[:\-]?\s*([0-9]{1,2}[\-/. ][A-Za-z0-9]{1,9}[\-/. ][0-9]{2,4}|\d{4}-\d{2}-\d{2})"))
    due = _date(_after(t, [r"due date", r"payment due", r"due on"],
                       r"[:\-]?\s*([0-9]{1,2}[\-/. ][A-Za-z0-9]{1,9}[\-/. ][0-9]{2,4}|\d{4}-\d{2}-\d{2})"))
    po_no = _after(t, [r"P\.?O\.?", r"purchase order", r"your order", r"order ref"],
                   r"[:\-#.]?\s*([A-Za-z]{0,4}[/\-]?\d[\w/\-]*)")
    total = _amount_after(t, [r"grand total", r"total amount", r"invoice total", r"net payable",
                              r"amount payable", r"total"])
    taxable = _amount_after(t, [r"taxable value", r"taxable amount", r"sub ?total", r"basic"])
    lines = []
    for raw in t.splitlines():
        m = LINE_RE.match(raw.strip())
        if not m:
            continue
        qty, rate, amt = _dec(m["qty"]), _dec(m["rate"]), _dec(m["amount"])
        if not (qty and rate and amt):
            continue
        if abs(qty * rate - amt) > max(Decimal("1"), amt * Decimal("0.02")):
            continue  # shape matched but numbers do not, probably a header row
        lines.append({"descr": m["descr"].strip(" -"), "hsn": m["hsn"], "qty": qty,
                      "uom": (m["uom"] or "").upper() or None, "price": rate, "amount": amt})
    # a vendor's own name is usually the first non-empty line
    first = next((ln.strip() for ln in t.splitlines() if ln.strip() and not GSTIN_RE.search(ln)), None)
    return {"vendor_gstin": vendor_gstin, "gstins": gstins, "vendor_name": first,
            "doc_no": inv_no, "doc_date": inv_date, "due_date": due, "po_no": po_no,
            "taxable": taxable, "total": total, "lines": lines}


LLM_PROMPT = """You are reading a supplier's invoice sent to a buyer in India. Return ONLY a JSON
object with these keys (null when absent): vendor_name, vendor_gstin, buyer_gstin, doc_no,
doc_date (YYYY-MM-DD), due_date (YYYY-MM-DD), po_no, taxable (number), tax (number),
total (number), lines: [{descr, hsn, qty, uom, price, amount}]. Use the printed line items
only; do not invent lines. No prose, no markdown fences.

INVOICE TEXT:
"""


def parse_llm(text: str) -> dict | None:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    import httpx
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=60,
                       headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                "content-type": "application/json"},
                       json={"model": os.getenv("EXTRACT_MODEL", "claude-sonnet-4-5"),
                             "max_tokens": 2000,
                             "messages": [{"role": "user", "content": LLM_PROMPT + text[:12000]}]})
        r.raise_for_status()
        body = "".join(b.get("text", "") for b in r.json().get("content", []))
        body = re.sub(r"^```(?:json)?|```$", "", body.strip(), flags=re.M).strip()
        d = json.loads(body)
        for k in ("doc_date", "due_date"):
            d[k] = _date(d.get(k) or "") if d.get(k) else None
        for k in ("taxable", "tax", "total"):
            d[k] = _dec(d[k]) if d.get(k) is not None else None
        for ln in d.get("lines") or []:
            for k in ("qty", "price", "amount"):
                ln[k] = _dec(ln.get(k)) if ln.get(k) is not None else None
        d["lines"] = [ln for ln in d.get("lines") or [] if ln.get("qty") and ln.get("price")]
        return d
    except Exception:
        return None


def merge(rules: dict, llm: dict | None) -> tuple[dict, list[str]]:
    """Prefer the rule value; fall back to the LLM; note where they differ."""
    notes = []
    if not llm:
        return rules, notes
    out = dict(rules)
    for k in ("vendor_gstin", "vendor_name", "doc_no", "doc_date", "due_date", "po_no",
              "taxable", "total"):
        if not out.get(k) and llm.get(k):
            out[k] = llm[k]
        elif out.get(k) and llm.get(k) and str(out[k]) != str(llm[k]):
            notes.append(f"{k}: read '{out[k]}', model read '{llm[k]}' — check.")
    # lines: take whichever set reconciles better with the printed total
    def gap(lines):
        if not lines or not out.get("taxable"):
            return Decimal("1e9")
        return abs(sum(l["amount"] or 0 for l in lines) - out["taxable"])
    if llm.get("lines") and (not out["lines"] or gap(llm["lines"]) < gap(out["lines"])):
        out["lines"] = llm["lines"]
        notes.append("Line items taken from the model's reading.")
    out["llm_used"] = True
    return out, notes


# ------------------------------------------------------------ matching
def _sim(a, b):
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def match(ctx, parsed: dict) -> dict:
    from sqlalchemy import select
    from . import models as M
    warnings = []
    vendor, vconf = None, 0
    if parsed.get("vendor_gstin"):
        reg = ctx.db.execute(select(M.VendorGstin).join(M.Vendor).where(
            M.VendorGstin.gstin == parsed["vendor_gstin"],
            M.Vendor.tenant_id == ctx.tenant.id)).scalar_one_or_none()
        if reg:
            vendor, vconf = reg.vendor, 1.0
    vendors = list(ctx.db.execute(ctx.scope(select(M.Vendor), M.Vendor)).scalars())
    if not vendor and parsed.get("vendor_name"):
        best = max(vendors, key=lambda v: _sim(v.name, parsed["vendor_name"]), default=None)
        if best and _sim(best.name, parsed["vendor_name"]) >= 0.6:
            vendor, vconf = best, round(_sim(best.name, parsed["vendor_name"]), 2)
    if not vendor:
        warnings.append("Vendor not recognised — create it under Vendors, or pick one below."
                        + (f" GSTIN on the invoice: {parsed['vendor_gstin']}." if parsed.get("vendor_gstin") else ""))
    po = None
    if parsed.get("po_no"):
        want = re.sub(r"[^A-Z0-9]", "", parsed["po_no"].upper())
        for p in ctx.db.execute(ctx.scope(select(M.PurchaseOrder), M.PurchaseOrder)).scalars():
            if re.sub(r"[^A-Z0-9]", "", p.doc_no.upper()) == want:
                po = p
                break
        if not po:
            warnings.append(f"Purchase order '{parsed['po_no']}' not found; record without a PO or pick one.")
        elif vendor and po.vendor_id != vendor.id:
            warnings.append(f"PO {po.doc_no} belongs to {po.vendor.name}, not the vendor read from the invoice.")
        elif po.status != "OPEN":
            warnings.append(f"PO {po.doc_no} is already {po.status.lower()}.")
    if po and not vendor:
        vendor, vconf = po.vendor, 0.8
    mats = list(ctx.db.execute(ctx.scope(select(M.Material), M.Material)).scalars())
    lines = []
    for i, ln in enumerate(parsed.get("lines") or [], 1):
        best, conf, how = None, 0.0, None
        code_in = re.search(r"\b([A-Z]{2,5}-?\d{2,6})\b", ln.get("descr") or "")
        if code_in:
            best = next((m for m in mats if m.code.upper() == code_in.group(1).upper()), None)
            if best:
                conf, how = 1.0, "code"
        if not best and po:
            cands = [l.material for l in po.lines]
            b = max(cands, key=lambda m: _sim(m.descr, ln.get("descr")), default=None)
            if b:
                best, conf, how = b, round(0.5 + 0.5 * _sim(b.descr, ln.get("descr")), 2), "po line"
        if not best:
            pool = [m for m in mats if ln.get("hsn") and m.hsn == ln["hsn"]] or mats
            b = max(pool, key=lambda m: _sim(m.descr, ln.get("descr")), default=None)
            s = _sim(b.descr, ln.get("descr")) if b else 0
            if b and (s >= 0.45 or (ln.get("hsn") and b.hsn == ln["hsn"] and s >= 0.3)):
                best, conf, how = b, round(s, 2), "description"
        lines.append({"line_no": i, "descr": ln.get("descr"), "hsn": ln.get("hsn"),
                      "qty": float(ln["qty"]), "uom": ln.get("uom"),
                      "price": float(ln["price"]),
                      "amount": float(ln["amount"]) if ln.get("amount") else float(ln["qty"] * ln["price"]),
                      "material_id": best.id if best else None,
                      "material_code": best.code if best else None,
                      "material_descr": best.descr if best else None,
                      "confidence": conf, "matched_by": how})
        if not best:
            warnings.append(f"Line {i}: no material matched '{ln.get('descr')}'.")
    if parsed.get("taxable") and lines:
        s = sum(Decimal(str(l["amount"])) for l in lines)
        if abs(s - parsed["taxable"]) > Decimal("1"):
            warnings.append(f"Lines add to {s} but the invoice shows taxable {parsed['taxable']}.")
    if not lines and po:
        lines = [{"line_no": l.line_no, "descr": l.material.descr, "hsn": l.material.hsn,
                  "qty": float(l.qty), "uom": l.material.uom, "price": float(l.price),
                  "amount": float(l.qty * l.price), "material_id": l.material_id,
                  "material_code": l.material.code, "material_descr": l.material.descr,
                  "confidence": 0.5, "matched_by": "copied from PO"} for l in po.lines]
        warnings.append("No line items could be read; the purchase order lines are proposed instead.")
    return {"vendor_id": vendor.id if vendor else None,
            "vendor_name": vendor.name if vendor else parsed.get("vendor_name"),
            "vendor_confidence": vconf,
            "vendor_gstin": parsed.get("vendor_gstin"),
            "po_id": po.id if po else None, "po_no": po.doc_no if po else parsed.get("po_no"),
            "doc_no": parsed.get("doc_no"),
            "doc_date": parsed["doc_date"].isoformat() if parsed.get("doc_date") else None,
            "due_date": parsed["due_date"].isoformat() if parsed.get("due_date") else None,
            "taxable": float(parsed["taxable"]) if parsed.get("taxable") else None,
            "total": float(parsed["total"]) if parsed.get("total") else None,
            "lines": lines, "warnings": warnings}
