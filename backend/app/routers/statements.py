"""Bank and director-card statements.

Two screens hang off this router:

Bank Statements (perm: bankstmt)
    The company's own accounts. A monthly statement (PDF or CSV) is uploaded,
    every transaction in it is parsed and saved, and a re-upload of the same
    file cannot double rows — each transaction carries a fingerprint and is
    stored exactly once.

Director Cards (perm: cardstmt)
    Cards a director pays personally. The same upload, and then each card
    debit is allocated to COMPANY (a business expense the company owes the
    director for) or PERSONAL. The reconciliation endpoint totals, month by
    month, what the company owes the director against what has been settled.

The ledger endpoint puts the month's expense sources side by side — vendor
invoices booked, vendor payments made, bank debits, card spend allocated to
the company — so purchases can be tallied to the monthly expense ledger.
"""
import csv, hashlib, io, re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from .. import models as M
from ..deps import Ctx, need, need_any
from .. import extract as X

router = APIRouter(prefix="/statements", tags=["statements"])

MAX_BYTES = 20 * 1024 * 1024
PDFS = (".pdf",)
SHEETS = (".csv", ".txt")
PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

CARD_CATEGORIES = ["Travel", "Fuel", "Meals and entertainment", "Software and subscriptions",
                   "Office supplies", "Communication", "Professional fees", "Marketing",
                   "Repairs", "Statutory and bank charges", "Other"]

# --------------------------------------------------------------- parsing

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_START = [
    # 13 Mar 2025 / 13-Mar-25
    (re.compile(r"^(\d{1,2})[\s\-/.]([A-Za-z]{3,9})[\s\-/.,]+(\d{2,4})\b"),
     lambda m: _mk(m.group(3), MONTHS.get(m.group(2)[:3].lower()), m.group(1))),
    # Mar 13, 2025
    (re.compile(r"^([A-Za-z]{3,9})[\s\-/.]+(\d{1,2})[\s,\-/.]+(\d{2,4})\b"),
     lambda m: _mk(m.group(3), MONTHS.get(m.group(1)[:3].lower()), m.group(2))),
    # 13/03/2025 (day first, as Indian statements print)
    (re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b"),
     lambda m: _mk(m.group(3), int(m.group(2)), m.group(1))),
    # 2025-03-13
    (re.compile(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b"),
     lambda m: _mk(m.group(1), int(m.group(2)), m.group(3))),
]
MONEY_TOKEN = re.compile(r"(-?\d[\d,]*\.\d{2})\s*(Cr|CR|cr|Dr|DR|dr)?\.?(?=\s|$)")
CREDIT_WORDS = re.compile(r"PAYMENT\s+RECEIVED|REVERSAL|REFUND|CASHBACK|NEFT[\s\-]*CR|IMPS[\s\-]*CR"
                          r"|UPI[\s\-]*CR|\bBY\s+TRANSFER|INTEREST\s+CREDIT|SALARY|DIVIDEND", re.I)


def _mk(y, mo, d):
    try:
        y = int(y); y += 2000 if y < 100 else 0
        if not mo or not (1 <= int(mo) <= 12):
            return None
        return date(y, int(mo), int(d))
    except (ValueError, TypeError):
        return None


def _amt(s):
    try:
        return Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None


def parse_text(text: str, kind: str) -> list[dict]:
    """Line-shaped parsing: a date at the start, money at the end.

    A card line carries one amount, credit marked by 'Cr' or by wording.
    A bank line usually carries two or three (withdrawal / deposit / balance);
    the last is the running balance, the one before it the amount, and the
    direction comes from a Dr/Cr marker, from the balance delta, or from
    wording, in that order of trust.
    """
    out, prev_balance = [], None
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        d, rest = None, None
        for pat, mk in DATE_START:
            m = pat.match(line)
            if m:
                d = mk(m)
                rest = line[m.end():].strip()
                break
        if not d:
            continue
        tokens = list(MONEY_TOKEN.finditer(rest))
        if not tokens:
            continue
        if kind == "BANK" and len(tokens) >= 2:
            bal_tok, amt_tok = tokens[-1], tokens[-2]
            desc = rest[:amt_tok.start()].strip()
            amount, balance = _amt(amt_tok.group(1)), _amt(bal_tok.group(1))
            marker = (amt_tok.group(2) or "").lower()
            if marker in ("cr", "dr"):
                credit = marker == "cr"
            elif balance is not None and prev_balance is not None and amount:
                credit = balance > prev_balance
            else:
                credit = bool(CREDIT_WORDS.search(desc))
            prev_balance = balance if balance is not None else prev_balance
        else:
            amt_tok = tokens[-1]
            desc = rest[:amt_tok.start()].strip()
            amount = _amt(amt_tok.group(1))
            marker = (amt_tok.group(2) or "").lower()
            credit = marker == "cr" or bool(CREDIT_WORDS.search(desc))
        if amount is None or not desc:
            continue
        amount = abs(amount)
        if amount == 0:
            continue
        out.append({"txn_date": d, "descr": desc[:240],
                    "debit": Decimal(0) if credit else amount,
                    "credit": amount if credit else Decimal(0)})
    return out


def parse_csv(data: bytes, kind: str) -> list[dict]:
    """A CSV export: the header names find the columns; failing a header,
    each row is treated like a text line."""
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    hdr = [c.strip().lower() for c in rows[0]]

    def col(*names):
        for n in names:
            for i, h in enumerate(hdr):
                if n in h:
                    return i
        return None
    ci_date = col("date")
    ci_desc = col("narration", "description", "particulars", "details", "remarks")
    ci_deb = col("withdrawal", "debit")
    ci_cred = col("deposit", "credit")
    ci_amt = col("amount")
    out = []
    if ci_date is not None and ci_desc is not None and (ci_deb is not None or ci_amt is not None):
        for r in rows[1:]:
            if len(r) <= max(x for x in (ci_date, ci_desc, ci_deb, ci_cred, ci_amt) if x is not None):
                continue
            d = None
            for pat, mk in DATE_START:
                m = pat.match(r[ci_date].strip())
                if m:
                    d = mk(m)
                    break
            if not d:
                continue
            desc = r[ci_desc].strip()[:240]
            deb = _amt(r[ci_deb].strip() or "0") if ci_deb is not None else None
            cred = _amt(r[ci_cred].strip() or "0") if ci_cred is not None else None
            if deb is None and cred is None and ci_amt is not None:
                a = _amt(r[ci_amt].strip() or "0")
                if a is None:
                    continue
                cred, deb = (abs(a), Decimal(0)) if a < 0 or CREDIT_WORDS.search(desc) \
                    else (Decimal(0), a)
            deb, cred = abs(deb or 0), abs(cred or 0)
            if not desc or (deb == 0 and cred == 0):
                continue
            out.append({"txn_date": d, "descr": desc, "debit": deb, "credit": cred})
        return out
    return parse_text(text, kind)


def fingerprint(t: dict) -> str:
    key = f"{t['txn_date'].isoformat()}|{t['descr'].upper()}|{t['debit']}|{t['credit']}"
    return hashlib.sha1(key.encode()).hexdigest()


# --------------------------------------------------------------- accounts

class AccountIn(BaseModel):
    kind: str = Field(pattern="^(BANK|CARD)$")
    label: str = Field(min_length=2, max_length=120)
    holder: str | None = Field(default=None, max_length=120)
    number_hint: str | None = Field(default=None, max_length=30)


def _perm_for(kind: str) -> str:
    return "bankstmt" if kind == "BANK" else "cardstmt"


def _acct_out(a):
    return {"id": a.id, "kind": a.kind, "label": a.label, "holder": a.holder,
            "number_hint": a.number_hint, "active": bool(a.active)}


@router.get("/accounts")
def accounts(ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))):
    rows = ctx.db.execute(ctx.scope(select(M.StmtAccount), M.StmtAccount)
                          .order_by(M.StmtAccount.kind, M.StmtAccount.label)).scalars().all()
    return [_acct_out(a) for a in rows if _perm_for(a.kind) in ctx.perms]


@router.post("/accounts")
def add_account(body: AccountIn, ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))):
    ctx.require(_perm_for(body.kind))
    if body.kind == "CARD" and not (body.holder or "").strip():
        raise HTTPException(422, "Name the director who holds this card")
    a = M.StmtAccount(tenant_id=ctx.tenant.id, kind=body.kind, label=body.label.strip(),
                      holder=(body.holder or "").strip() or None,
                      number_hint=(body.number_hint or "").strip() or None)
    ctx.db.add(a)
    try:
        ctx.db.commit()
    except Exception:
        ctx.db.rollback()
        raise HTTPException(409, "An account with that label already exists")
    return _acct_out(a)


@router.put("/accounts/{aid}")
def edit_account(aid: int, body: AccountIn, ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))):
    a = ctx.get(M.StmtAccount, aid)
    if not a:
        raise HTTPException(404, "No such account")
    ctx.require(_perm_for(a.kind))
    a.label, a.holder, a.number_hint = body.label.strip(), \
        (body.holder or "").strip() or None, (body.number_hint or "").strip() or None
    ctx.db.commit()
    return _acct_out(a)


# --------------------------------------------------------------- upload

@router.post("/accounts/{aid}/upload")
async def upload_statement(aid: int, period: str = Query(...),
                           file: UploadFile = File(...),
                           ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))):
    a = ctx.get(M.StmtAccount, aid)
    if not a:
        raise HTTPException(404, "No such account")
    ctx.require(_perm_for(a.kind))
    if not PERIOD_RE.match(period or ""):
        raise HTTPException(422, "Give the statement month as YYYY-MM")
    name = (file.filename or "statement").lower()
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_BYTES // (1024*1024)} MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    if name.endswith(SHEETS):
        txns = parse_csv(data, a.kind)
    elif name.endswith(PDFS) or data[:4] == b"%PDF":
        try:
            text, _ = X.read_text(name, data)
        except RuntimeError as e:
            raise HTTPException(422, str(e))
        except Exception as e:
            raise HTTPException(422, f"Could not read that file: {e.__class__.__name__}")
        txns = parse_text(text, a.kind)
    else:
        raise HTTPException(422, "Upload the statement as PDF or CSV")
    if not txns:
        raise HTTPException(422, "No transactions were recognised in the file. "
                            "If the PDF is a scan, upload the bank's CSV export instead.")

    up = M.StmtUpload(tenant_id=ctx.tenant.id, account_id=a.id, period=period,
                      filename=file.filename or "statement", uploaded_by=ctx.user.name,
                      txns_found=len(txns))
    ctx.db.add(up)
    ctx.db.flush()

    existing = set(ctx.db.execute(
        select(M.StmtTxn.fingerprint).where(M.StmtTxn.tenant_id == ctx.tenant.id,
                                            M.StmtTxn.account_id == a.id)).scalars())
    new = 0
    for t in txns:
        fp = fingerprint(t)
        if fp in existing:
            continue
        existing.add(fp)
        alloc = "UNALLOCATED" if (a.kind == "CARD" and t["debit"] > 0) else "NA"
        ctx.db.add(M.StmtTxn(tenant_id=ctx.tenant.id, account_id=a.id, upload_id=up.id,
                             txn_date=t["txn_date"], descr=t["descr"], debit=t["debit"],
                             credit=t["credit"], fingerprint=fp, allocation=alloc))
        new += 1
    up.txns_new = new
    ctx.db.commit()
    return {"upload_id": up.id, "found": len(txns), "saved": new,
            "duplicates_skipped": len(txns) - new,
            "note": None if new else "Every transaction in this file was already saved earlier."}


@router.get("/accounts/{aid}/uploads")
def uploads(aid: int, ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))):
    a = ctx.get(M.StmtAccount, aid)
    if not a:
        raise HTTPException(404, "No such account")
    ctx.require(_perm_for(a.kind))
    rows = ctx.db.execute(select(M.StmtUpload).where(
        M.StmtUpload.tenant_id == ctx.tenant.id, M.StmtUpload.account_id == aid)
        .order_by(M.StmtUpload.created_at.desc())).scalars().all()
    return [{"id": u.id, "period": u.period, "filename": u.filename,
             "uploaded_by": u.uploaded_by, "found": u.txns_found, "saved": u.txns_new,
             "at": u.created_at.isoformat()} for u in rows]


@router.delete("/uploads/{uid}")
def delete_upload(uid: int, ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))):
    u = ctx.get(M.StmtUpload, uid)
    if not u:
        raise HTTPException(404, "No such upload")
    ctx.require(_perm_for(u.account.kind))
    n = ctx.db.execute(select(func.count()).select_from(M.StmtTxn).where(
        M.StmtTxn.upload_id == uid,
        M.StmtTxn.allocation.in_(("COMPANY", "PERSONAL")))).scalar()
    if n:
        raise HTTPException(409, f"{n} transaction(s) from this upload are already allocated. "
                            "Remove the allocations first if you really mean to delete it.")
    ctx.db.delete(u)  # cascades to its transactions
    ctx.db.commit()
    return {"deleted": uid}


# --------------------------------------------------------------- transactions

@router.get("/accounts/{aid}/txns")
def txns(aid: int, period: str | None = None,
         ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))):
    a = ctx.get(M.StmtAccount, aid)
    if not a:
        raise HTTPException(404, "No such account")
    ctx.require(_perm_for(a.kind))
    q = select(M.StmtTxn).where(M.StmtTxn.tenant_id == ctx.tenant.id,
                                M.StmtTxn.account_id == aid)
    if period:
        if not PERIOD_RE.match(period):
            raise HTTPException(422, "Give the month as YYYY-MM")
        y, m = int(period[:4]), int(period[5:])
        nxt = date(y + (m == 12), (m % 12) + 1, 1)
        q = q.where(M.StmtTxn.txn_date >= date(y, m, 1), M.StmtTxn.txn_date < nxt)
    rows = ctx.db.execute(q.order_by(M.StmtTxn.txn_date, M.StmtTxn.id)).scalars().all()
    return [{"id": t.id, "date": t.txn_date.isoformat(), "descr": t.descr,
             "debit": float(t.debit), "credit": float(t.credit),
             "allocation": t.allocation, "category": t.category, "notes": t.notes,
             "allocated_by": t.allocated_by} for t in rows]


class AllocateIn(BaseModel):
    allocation: str = Field(pattern="^(UNALLOCATED|COMPANY|PERSONAL)$")
    category: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=200)


@router.put("/txns/{tid}/allocate")
def allocate(tid: int, body: AllocateIn, ctx: Ctx = Depends(need("cardstmt"))):
    t = ctx.get(M.StmtTxn, tid)
    if not t:
        raise HTTPException(404, "No such transaction")
    a = ctx.get(M.StmtAccount, t.account_id)
    if a.kind != "CARD":
        raise HTTPException(422, "Only card transactions are allocated. Bank rows are the "
                            "company's own money already.")
    if t.debit == 0:
        raise HTTPException(422, "This is a payment or refund on the card, not a spend — "
                            "it has nothing to allocate.")
    if body.allocation == "COMPANY" and not (body.category or "").strip():
        raise HTTPException(422, "Pick an expense category for a company expense")
    t.allocation = body.allocation
    t.category = (body.category or "").strip() or None if body.allocation == "COMPANY" else None
    t.notes = (body.notes or "").strip() or None
    t.allocated_by, t.allocated_at = ctx.user.name, datetime.utcnow()
    ctx.db.commit()
    return {"id": t.id, "allocation": t.allocation, "category": t.category}


@router.get("/categories")
def categories(ctx: Ctx = Depends(need("cardstmt"))):
    return CARD_CATEGORIES


# --------------------------------------------------------------- reconciliation

def _month_bounds(period):
    y, m = int(period[:4]), int(period[5:])
    return date(y, m, 1), date(y + (m == 12), (m % 12) + 1, 1)


@router.get("/reconcile")
def reconcile(period: str | None = None, ctx: Ctx = Depends(need("cardstmt"))):
    """Per card: what the director spent for the company, what was personal,
    what is still unallocated, and the payments made onto the card — so the
    director can reconcile the statements of the cards he has paid."""
    cards = ctx.db.execute(ctx.scope(select(M.StmtAccount), M.StmtAccount)
                           .where(M.StmtAccount.kind == "CARD")).scalars().all()
    out = []
    for a in cards:
        q = select(M.StmtTxn).where(M.StmtTxn.tenant_id == ctx.tenant.id,
                                    M.StmtTxn.account_id == a.id)
        if period:
            lo, hi = _month_bounds(period)
            q = q.where(M.StmtTxn.txn_date >= lo, M.StmtTxn.txn_date < hi)
        rows = ctx.db.execute(q).scalars().all()
        company = sum(t.debit for t in rows if t.allocation == "COMPANY")
        personal = sum(t.debit for t in rows if t.allocation == "PERSONAL")
        unalloc = sum(t.debit for t in rows if t.allocation == "UNALLOCATED")
        paid = sum(t.credit for t in rows)
        by_cat = {}
        for t in rows:
            if t.allocation == "COMPANY":
                by_cat[t.category or "Other"] = by_cat.get(t.category or "Other", 0) + float(t.debit)
        out.append({"account": _acct_out(a),
                    "company": float(company), "personal": float(personal),
                    "unallocated": float(unalloc), "payments": float(paid),
                    "owed_to_director": float(company),
                    "by_category": [{"category": k, "amount": v}
                                    for k, v in sorted(by_cat.items())],
                    "txn_count": len(rows)})
    return out


@router.get("/ledger")
def expense_ledger(period: str = Query(...), ctx: Ctx = Depends(
        need_any("bankstmt", "cardstmt"))):
    """The month's expense sources side by side, so invoices and purchases can
    be tallied against what actually moved: vendor invoices booked, vendor
    payments recorded, bank statement debits, and card spend allocated to the
    company."""
    if not PERIOD_RE.match(period):
        raise HTTPException(422, "Give the month as YYYY-MM")
    lo, hi = _month_bounds(period)

    vinvs = ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)
                           .where(M.VendorInvoice.doc_date >= lo,
                                  M.VendorInvoice.doc_date < hi)).scalars().all()
    from ..service import vinv_tax
    inv_total = sum(float(vinv_tax(ctx, v).rounded) for v in vinvs)

    pays = ctx.db.execute(ctx.scope(select(M.Payment), M.Payment)
                          .where(M.Payment.pay_type == "PAY",
                                 M.Payment.pay_date >= lo,
                                 M.Payment.pay_date < hi)).scalars().all()
    pay_total = sum(float(p.amount or 0) for p in pays)

    bank_rows, card_company, card_unalloc = [], 0.0, 0.0
    accts = ctx.db.execute(ctx.scope(select(M.StmtAccount), M.StmtAccount)).scalars().all()
    for a in accts:
        rows = ctx.db.execute(select(M.StmtTxn).where(
            M.StmtTxn.tenant_id == ctx.tenant.id, M.StmtTxn.account_id == a.id,
            M.StmtTxn.txn_date >= lo, M.StmtTxn.txn_date < hi)).scalars().all()
        if a.kind == "BANK" and "bankstmt" in ctx.perms:
            bank_rows.append({"account": a.label,
                              "debits": float(sum(t.debit for t in rows)),
                              "credits": float(sum(t.credit for t in rows)),
                              "txns": len(rows)})
        if a.kind == "CARD" and "cardstmt" in ctx.perms:
            card_company += float(sum(t.debit for t in rows if t.allocation == "COMPANY"))
            card_unalloc += float(sum(t.debit for t in rows if t.allocation == "UNALLOCATED"))

    bank_debits = sum(b["debits"] for b in bank_rows)
    return {
        "period": period,
        "vendor_invoices": {"count": len(vinvs), "total": inv_total},
        "vendor_payments": {"count": len(pays), "total": pay_total},
        "bank": bank_rows,
        "bank_debits_total": bank_debits,
        "card_company_expense": card_company,
        "card_unallocated": card_unalloc,
        "expense_recognised": inv_total + card_company,
        "cash_out": bank_debits,
        # Payments recorded in the books that the bank statement should contain.
        "payments_vs_bank_gap": round(pay_total - bank_debits, 2),
        # Purchases booked vs paid this month: a timing gap, not necessarily an error.
        "invoices_vs_payments_gap": round(inv_total - pay_total, 2),
    }
