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

Attachments (v4.2, extended in v4.8)
    A bank credit can be attached to the customer invoice(s) it settles, to
    an employee paying money back, or to a loan received from a director; a
    bank debit to the vendor invoice(s) it pays, to an employee's salary or
    expense, or to a loan repaid to a director. One invoice can be settled
    by several transactions, and an invoice attachment can carry TDS — the
    shortfall between the invoice and the money collected, which then shows
    in the TDS register. The amounts attached to a transaction never exceed it, and
    the amounts attached to an invoice across all transactions never exceed
    the invoice.

    Receipts (v4.9) — attaching a customer invoice to a bank credit also posts
    the receipt on Customer Payments (amount and any TDS), so the invoice
    shows as paid or part paid. Removing the attachment, or deleting the
    statement or account it came from, removes that receipt again.

The ledger endpoint puts the month's expense sources side by side — vendor
invoices booked, vendor payments made, bank debits, card spend allocated to
the company — so purchases can be tallied to the monthly expense ledger.
"""
import csv, hashlib, io, re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
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
# The same date shapes found anywhere in a line. Card statements printed in
# two columns (an account summary on the left, transactions on the right)
# read as "Card Number XXXX97 13 Aug 2026 PAYMENT RECEIVED ... 3,07,068.00",
# so the transaction date is not at the start of the line.
DATE_ANY = [(re.compile(r"(?<![\w/.\-])" + pat.pattern[1:]), mk) for pat, mk in DATE_START]


def _find_date(line: str, anywhere: bool):
    """(date, text after it). With anywhere, the earliest valid date in the
    line that still has text and an amount after it."""
    for pat, mk in DATE_START:
        m = pat.match(line)
        if m and mk(m):
            return mk(m), line[m.end():].strip()
    if not anywhere:
        return None, None
    best = None
    for pat, mk in DATE_ANY:
        for m in pat.finditer(line):
            d = mk(m)
            rest = line[m.end():].strip()
            if d and MONEY_TOKEN.search(rest) and (best is None or m.start() < best[0]):
                best = (m.start(), d, rest)
                break
    return (best[1], best[2]) if best else (None, None)


def _strip_value_date(desc: str) -> str:
    """Bank PDFs often print a value date again at the start of the
    narration ("01/04/2026 BY TRANSFER- ..."); it adds nothing."""
    for pat, mk in DATE_START:
        m = pat.match(desc)
        if m and mk(m):
            return desc[m.end():].strip() or desc
    return desc


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
        d, rest = _find_date(line, anywhere=(kind == "CARD"))
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
        out.append({"txn_date": d, "descr": _strip_value_date(desc)[:240], "raw": desc[:240],
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
            out.append({"txn_date": d, "descr": _strip_value_date(desc), "raw": desc,
                        "debit": deb, "credit": cred})
        return out
    return parse_text(text, kind)


STMT_PERIOD_RE = re.compile(
    r"(?:statement|billing)\s+(?:period|cycle)\s*:?\s*(\S.{5,30}?)\s+(?:to|-)\s+(\S.{5,30}?)(?:\s|$)",
    re.I)


def statement_window(text: str):
    """The statement's own period, when the file prints one
    ("Statement Period 13-08-2026 to 12-09-2026"). Rows dated outside it are
    illustrations — a card statement's 'sample transaction' table, say —
    not transactions."""
    m = STMT_PERIOD_RE.search(text or "")
    if not m:
        return None
    lo = hi = None
    for pat, mk in DATE_START:
        a = pat.match(m.group(1).strip())
        if a and not lo:
            lo = mk(a)
        b = pat.match(m.group(2).strip())
        if b and not hi:
            hi = mk(b)
    return (lo, hi) if lo and hi and lo <= hi else None


def keep_in_window(txns, window, period):
    """Drop rows that cannot belong to this statement: outside the period
    the file prints, or — when it prints none — more than two months away
    from the month chosen for the upload."""
    from datetime import timedelta
    if window:
        lo, hi = window[0] - timedelta(days=3), window[1] + timedelta(days=3)
    else:
        m_lo, m_hi = _month_bounds(period)
        lo, hi = m_lo - timedelta(days=62), m_hi + timedelta(days=62)
    kept = [t for t in txns if lo <= t["txn_date"] <= hi]
    return kept, len(txns) - len(kept)


def with_occurrence(txns):
    """Two genuine transactions can be identical — the same merchant, date
    and amount twice. Number repeats within a file so both are saved, while
    a re-upload of the same file still produces the same fingerprints."""
    seen = {}
    for t in txns:
        k = (t["txn_date"], t.get("raw", t["descr"]).upper(), t["debit"], t["credit"])
        seen[k] = seen.get(k, 0) + 1
        t["occurrence"] = seen[k]
    return txns


def fingerprint(t: dict) -> str:
    # Keyed on the narration as printed, so tidying how it is displayed never
    # makes a statement uploaded before the change look new.
    key = f"{t['txn_date'].isoformat()}|{t.get('raw', t['descr']).upper()}|{t['debit']}|{t['credit']}"
    if t.get("occurrence", 1) > 1:      # the first keeps the key used before v4.3
        key += f"#{t['occurrence']}"
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
                           default_allocation: str = Query("UNALLOCATED"),
                           default_category: str | None = Query(None, max_length=60),
                           ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))):
    """default_allocation (cards only) marks every spend in the file as a
    COMPANY or PERSONAL expense as it is saved. Each row can still be changed
    one by one afterwards. UNALLOCATED leaves the decision for later."""
    a = ctx.get(M.StmtAccount, aid)
    if not a:
        raise HTTPException(404, "No such account")
    ctx.require(_perm_for(a.kind))
    if not PERIOD_RE.match(period or ""):
        raise HTTPException(422, "Give the statement month as YYYY-MM")
    default_allocation = (default_allocation or "UNALLOCATED").upper()
    if default_allocation not in ("UNALLOCATED", "COMPANY", "PERSONAL"):
        raise HTTPException(422, "Mark the statement as COMPANY, PERSONAL or UNALLOCATED")
    if a.kind != "CARD" and default_allocation != "UNALLOCATED":
        raise HTTPException(422, "Only a card statement is marked company or personal")
    default_category = (default_category or "").strip() or None
    if default_allocation == "COMPANY":
        if not default_category:
            raise HTTPException(422, "Pick an expense category for a company expense")
        if default_category not in _categories(ctx):
            raise HTTPException(422, f"{default_category} is not an expense category")
    name = (file.filename or "statement").lower()
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_BYTES // (1024*1024)} MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    window = None
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
        window = statement_window(text)
    else:
        raise HTTPException(422, "Upload the statement as PDF or CSV")
    txns, ignored = keep_in_window(txns, window, period)
    txns = with_occurrence(txns)
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
        spend = a.kind == "CARD" and t["debit"] > 0
        alloc = default_allocation if spend else "NA"
        decided = spend and alloc != "UNALLOCATED"
        ctx.db.add(M.StmtTxn(tenant_id=ctx.tenant.id, account_id=a.id, upload_id=up.id,
                             txn_date=t["txn_date"], descr=t["descr"], debit=t["debit"],
                             credit=t["credit"], fingerprint=fp, allocation=alloc,
                             category=default_category if alloc == "COMPANY" else None,
                             allocated_by=ctx.user.name if decided else None,
                             allocated_at=datetime.utcnow() if decided else None))
        new += 1
    up.txns_new = new
    ctx.db.commit()
    return {"upload_id": up.id, "found": len(txns), "saved": new,
            "duplicates_skipped": len(txns) - new,
            "outside_period_ignored": ignored,
            "statement_period": ([window[0].isoformat(), window[1].isoformat()]
                                 if window else None),
            "allocation": default_allocation if a.kind == "CARD" else None,
            "note": None if new else "Every transaction in this file was already saved earlier."}


@router.get("/accounts/{aid}/uploads")
def uploads(aid: int, ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))):
    a = ctx.get(M.StmtAccount, aid)
    if not a:
        raise HTTPException(404, "No such statement account")
    ctx.require(_perm_for(a.kind))

    rows = ctx.db.execute(
        select(M.StmtUpload).where(
            M.StmtUpload.tenant_id == ctx.tenant.id,
            M.StmtUpload.account_id == aid
        ).order_by(
            M.StmtUpload.created_at.desc(),
            M.StmtUpload.id.desc()
        )
    ).scalars().all()

    out = []
    for u in rows:
        held, allocated, links = _upload_impact(ctx, u.id)

        out.append({
            "id": u.id,
            "period": u.period,
            "filename": u.filename,
            "uploaded_by": u.uploaded_by,
            "found": u.txns_found,
            "saved": u.txns_new,
            "at": u.created_at.isoformat() if u.created_at else None,
            "held": held,
            "allocated": allocated,
            "attachments": links
        })

    return out


def _upload_impact(ctx, uid):
    """What deleting an upload would take with it: the transactions it first
    saved, how many of those are allocated company or personal, and how many
    invoice or employee attachments sit on them."""
    held = ctx.db.execute(
        select(func.count())
        .select_from(M.StmtTxn)
        .where(
            M.StmtTxn.tenant_id == ctx.tenant.id,
            M.StmtTxn.upload_id == uid
        )
    ).scalar_one()

    allocated = ctx.db.execute(
        select(func.count())
        .select_from(M.StmtTxn)
        .where(
            M.StmtTxn.tenant_id == ctx.tenant.id,
            M.StmtTxn.upload_id == uid,
            M.StmtTxn.allocation.in_(("COMPANY", "PERSONAL"))
        )
    ).scalar_one()

    links = ctx.db.execute(
        select(func.count())
        .select_from(M.StmtTxnLink)
        .join(
            M.StmtTxn,
            M.StmtTxn.id == M.StmtTxnLink.txn_id
        )
        .where(
            M.StmtTxnLink.tenant_id == ctx.tenant.id,
            M.StmtTxn.upload_id == uid
        )
    ).scalar_one()

    return held, allocated, links


def _purge_txns(ctx, txn_ids):
    """Delete statement transactions and their attachments, and the receipts
    those attachments posted on Customer Payments (v4.9) — so the invoices
    they settled show as unpaid again. Receipts entered by hand on Customer
    Payments are never touched. Returns how many receipts were removed."""
    if not txn_ids:
        return 0

    pids = [p for (p,) in ctx.db.execute(
        select(M.StmtTxnLink.payment_id).where(
            M.StmtTxnLink.tenant_id == ctx.tenant.id,
            M.StmtTxnLink.txn_id.in_(txn_ids),
            M.StmtTxnLink.payment_id.is_not(None))).all()]

    ctx.db.execute(
        delete(M.StmtTxnLink).where(
            M.StmtTxnLink.tenant_id == ctx.tenant.id,
            M.StmtTxnLink.txn_id.in_(txn_ids)
        ).execution_options(synchronize_session=False)
    )

    removed = _drop_receipts(ctx, pids)

    ctx.db.execute(
        delete(M.StmtTxn).where(
            M.StmtTxn.tenant_id == ctx.tenant.id,
            M.StmtTxn.id.in_(txn_ids)
        ).execution_options(synchronize_session=False)
    )

    return removed


@router.delete("/uploads/{uid}")
def delete_upload(
    uid: int,
    force: bool = Query(False),
    ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))
):
    """Delete an uploaded statement and the transactions it first saved.

    Rows that an earlier upload had already saved belong to that earlier
    upload and stay. Without force, an upload whose transactions are
    allocated or attached is refused with the counts, so nothing decided by
    hand disappears by accident; with force=true they are removed with it.
    Re-uploading the same file afterwards saves its transactions afresh.
    """
    u = ctx.get(M.StmtUpload, uid)

    if not u:
        raise HTTPException(404, "No such upload")

    ctx.require(_perm_for(u.account.kind))

    held, allocated, links = _upload_impact(ctx, uid)

    if (allocated or links) and not force:
        what = []

        if allocated:
            what.append(
                f"{allocated} transaction(s) already allocated company or personal"
            )

        if links:
            what.append(
                f"{links} invoice or employee attachment(s)"
            )

        raise HTTPException(
            409,
            "This statement has " + " and ".join(what) +
            ". Confirm the delete to remove them with it."
        )

    txn_ids = [
        i for (i,) in ctx.db.execute(
            select(M.StmtTxn.id).where(
                M.StmtTxn.tenant_id == ctx.tenant.id,
                M.StmtTxn.upload_id == uid
            )
        ).all()
    ]

    pays = _purge_txns(ctx, txn_ids)

    ctx.db.execute(
        delete(M.StmtUpload).where(M.StmtUpload.id == uid)
    )

    ctx.db.commit()

    return {
        "deleted": uid,
        "period": u.period,
        "filename": u.filename,
        "transactions_removed": held,
        "allocations_removed": allocated,
        "attachments_removed": links,
        "payments_removed": pays
    }


def _account_impact(ctx, aid) -> dict:
    """What deleting a whole bank account or card would take with it."""
    txn_q = select(M.StmtTxn.id).where(
        M.StmtTxn.tenant_id == ctx.tenant.id,
        M.StmtTxn.account_id == aid
    )

    n = lambda q: ctx.db.execute(q).scalar_one()

    return {
        "statements": n(
            select(func.count()).select_from(M.StmtUpload).where(
                M.StmtUpload.tenant_id == ctx.tenant.id,
                M.StmtUpload.account_id == aid
            )
        ),
        "transactions": n(
            select(func.count()).select_from(M.StmtTxn).where(
                M.StmtTxn.tenant_id == ctx.tenant.id,
                M.StmtTxn.account_id == aid
            )
        ),
        "allocated": n(
            select(func.count()).select_from(M.StmtTxn).where(
                M.StmtTxn.tenant_id == ctx.tenant.id,
                M.StmtTxn.account_id == aid,
                M.StmtTxn.allocation.in_(("COMPANY", "PERSONAL"))
            )
        ),
        "attachments": n(
            select(func.count()).select_from(M.StmtTxnLink).where(
                M.StmtTxnLink.tenant_id == ctx.tenant.id,
                M.StmtTxnLink.txn_id.in_(txn_q)
            )
        ),
        # v4.9 — receipts these attachments posted on Customer Payments
        "recorded_payments": n(
            select(func.count()).select_from(M.StmtTxnLink).where(
                M.StmtTxnLink.tenant_id == ctx.tenant.id,
                M.StmtTxnLink.txn_id.in_(txn_q),
                M.StmtTxnLink.payment_id.is_not(None)
            )
        ),
    }


@router.get("/accounts/{aid}/impact")
def account_impact(
    aid: int,
    ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))
):
    a = ctx.get(M.StmtAccount, aid)

    if not a:
        raise HTTPException(404, "No such account")

    ctx.require(_perm_for(a.kind))

    return {
        "id": a.id,
        "kind": a.kind,
        "label": a.label,
        **_account_impact(ctx, aid)
    }


@router.delete("/accounts/{aid}")
def delete_account(
    aid: int,
    confirm: str | None = Query(None),
    ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))
):
    """Delete a bank account or director card completely: every statement
    uploaded to it, every transaction, every allocation and attachment, and
    the receipts or payments those attachments recorded. Invoices, vendors,
    employees and loans themselves are untouched. When anything has been
    allocated or attached, the account's label must be given as `confirm`."""
    a = ctx.get(M.StmtAccount, aid)

    if not a:
        raise HTTPException(404, "No such account")

    ctx.require(_perm_for(a.kind))

    imp = _account_impact(ctx, aid)

    if (imp["allocated"] or imp["attachments"]) and (
        confirm or ""
    ).strip() != a.label:
        raise HTTPException(
            409,
            f"{a.label} has {imp['attachments']} attachment(s) and "
            f"{imp['allocated']} allocation(s). Type the account name to confirm."
        )

    txn_ids = [
        i for (i,) in ctx.db.execute(
            select(M.StmtTxn.id).where(
                M.StmtTxn.tenant_id == ctx.tenant.id,
                M.StmtTxn.account_id == aid
            )
        ).all()
    ]

    imp["payments_removed"] = _purge_txns(ctx, txn_ids)

    ctx.db.execute(
        delete(M.StmtUpload).where(
            M.StmtUpload.tenant_id == ctx.tenant.id,
            M.StmtUpload.account_id == aid
        ).execution_options(synchronize_session=False)
    )

    label, kind = a.label, a.kind

    ctx.db.execute(
        delete(M.StmtAccount).where(
            M.StmtAccount.tenant_id == ctx.tenant.id,
            M.StmtAccount.id == aid
        ).execution_options(synchronize_session=False)
    )

    ctx.db.commit()

    return {
        "deleted": aid,
        "label": label,
        "kind": kind,
        **imp
    }


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
        _view_bounds(ctx, period)                       # a month or a financial year
        q = _in_period(q, a, period, ctx)
    rows = ctx.db.execute(q.order_by(M.StmtTxn.txn_date, M.StmtTxn.id)).scalars().all()
    links = _links_for(ctx, [t.id for t in rows])
    out = []
    for t in rows:
        ls = links.get(t.id, [])
        attached = sum(l["amount"] for l in ls)
        out.append({"id": t.id, "date": t.txn_date.isoformat(), "descr": t.descr,
                    "debit": float(t.debit), "credit": float(t.credit),
                    "allocation": t.allocation, "category": t.category, "notes": t.notes,
                    "allocated_by": t.allocated_by, "links": ls,
                    "attached": round(attached, 2),
                    "unattached": round(float(t.debit or t.credit) - attached, 2)})
    return out


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
    if body.allocation != "COMPANY" and _attached_sum(ctx, txn_id=t.id) > 0:
        raise HTTPException(
            409,
            "A vendor invoice is attached to this spend, so it was paid for "
            "the company. Remove the invoice first to mark it "
            f"{body.allocation.lower()}."
        )
    t.allocation = body.allocation
    t.category = (body.category or "").strip() or None if body.allocation == "COMPANY" else None
    t.notes = (body.notes or "").strip() or None
    t.allocated_by, t.allocated_at = ctx.user.name, datetime.utcnow()
    ctx.db.commit()
    return {"id": t.id, "allocation": t.allocation, "category": t.category}


@router.put("/accounts/{aid}/allocate-all")
def allocate_all(aid: int, body: AllocateIn, period: str = Query(...),
                 ctx: Ctx = Depends(need("cardstmt"))):
    """Mark every still-unallocated spend on a card for the month as company
    or personal in one go. Rows already decided are left as they are."""
    a = ctx.get(M.StmtAccount, aid)
    if not a or a.kind != "CARD":
        raise HTTPException(404, "No such card")
    if not PERIOD_RE.match(period or ""):
        raise HTTPException(422, "Give the month as YYYY-MM")
    if body.allocation == "UNALLOCATED":
        raise HTTPException(422, "Choose company or personal")
    cat = (body.category or "").strip() or None
    if body.allocation == "COMPANY":
        if not cat:
            raise HTTPException(422, "Pick an expense category for a company expense")
    else:
        cat = None
    rows = ctx.db.execute(_in_period(select(M.StmtTxn).where(
        M.StmtTxn.tenant_id == ctx.tenant.id, M.StmtTxn.account_id == aid,
        M.StmtTxn.allocation == "UNALLOCATED", M.StmtTxn.debit > 0), a, period)).scalars().all()
    now = datetime.utcnow()
    for t in rows:
        t.allocation, t.category = body.allocation, cat
        t.allocated_by, t.allocated_at = ctx.user.name, now
    ctx.db.commit()
    return {"updated": len(rows), "allocation": body.allocation, "category": cat}


def _categories(ctx):
    """The expense heads in the Expense master, or the standard list while
    the master is still empty."""
    from .expenses import active_heads
    heads = active_heads(ctx)
    return [h.name for h in heads] if heads else list(CARD_CATEGORIES)


@router.get("/categories")
def categories(ctx: Ctx = Depends(need("cardstmt"))):
    return _categories(ctx)



# --------------------------------------------------------------- attachments

PURPOSES = ("SALARY", "EXPENSE", "REFUND")
CENT = Decimal("0.005")


def _links_for(ctx, txn_ids):
    """Attachments of the given transactions, as {txn_id: [link, ...]}."""
    if not txn_ids:
        return {}
    rows = ctx.db.execute(select(M.StmtTxnLink).where(
        M.StmtTxnLink.tenant_id == ctx.tenant.id,
        M.StmtTxnLink.txn_id.in_(txn_ids)).order_by(M.StmtTxnLink.id)).scalars().all()
    out = {}
    for l in rows:
        out.setdefault(l.txn_id, []).append(_link_out(ctx, l))
    return out


def _link_out(ctx, l):
    d = {"id": l.id, "txn_id": l.txn_id, "link_type": l.link_type,
         "amount": float(l.amount), "tds": float(l.tds or 0),
         "gst_tds": float(l.gst_tds or 0), "notes": l.notes,
         "govt_kind": l.govt_kind, "govt_period": l.govt_period,
         "challan_ref": l.challan_ref, "govt_descr": l.govt_descr,
         "purpose": l.purpose, "linked_by": l.linked_by, "ref_id": None, "ref": None,
         "party": None, "expense_id": l.expense_id, "expense": None,
         "invoice_total": None, "invoice_open": None}
    if l.expense_id:
        h = ctx.db.get(M.ExpenseHead, l.expense_id)
        if h:
            d["expense"] = f"{h.exp_code} {h.name}"
    if l.link_type == "CUST_INV" and l.invoice_id:
        inv = ctx.db.get(M.Invoice, l.invoice_id)
        if inv:
            from ..service import invoice_tax
            total = invoice_tax(ctx, inv).rounded
            d.update(ref_id=inv.id, ref=inv.doc_no, party=inv.customer.name,
                     invoice_total=float(total), invoice_open=float(_cust_open(ctx, inv)),
                     payment_id=l.payment_id)
    elif l.link_type == "VEND_INV" and l.vinv_id:
        vi = ctx.db.get(M.VendorInvoice, l.vinv_id)
        if vi:
            from ..service import vinv_tax
            total = vinv_tax(ctx, vi).rounded
            d.update(ref_id=vi.id, ref=vi.doc_no, party=vi.vendor.name,
                     invoice_total=float(total),
                     invoice_open=float(_vend_open(ctx, vi)), payment_id=l.payment_id)
    elif l.link_type == "EMPLOYEE" and l.employee_id:
        e = ctx.db.get(M.Employee, l.employee_id)
        if e:
            d.update(ref_id=e.id, ref=e.emp_code, party=f"{e.first_name} {e.last_name}")
    elif l.link_type == "DIRECTOR_LOAN" and l.director_id:
        dr = ctx.db.get(M.Director, l.director_id)
        if dr:
            d.update(ref_id=dr.id, ref=dr.din or "Director", party=dr.name)
    elif l.link_type == "GOVT":
        d.update(ref=GOVT_LABEL.get(l.govt_kind, "Government"),
                 party=" · ".join(x for x in (
                     l.govt_descr, _month_label(l.govt_period),
                     f"challan {l.challan_ref}" if l.challan_ref else None) if x))
    return d


# v5.0 — payments to the government (statutory compliance)
GOVT_LABEL = {"GST": "GST payment", "TDS": "TDS payment", "PF": "PF payment",
              "ESI": "ESI payment", "OTHER": "Other statutory payment"}


def _month_label(period):
    if not period:
        return None
    mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"for {mon[int(period[5:]) - 1]} {period[:4]}"

def _vinv_attached(ctx, txn_ids) -> dict[int, float]:
    """{txn id: amount attached to vendor invoices} for the given rows."""
    if not txn_ids:
        return {}

    rows = ctx.db.execute(
        select(
            M.StmtTxnLink.txn_id,
            func.sum(M.StmtTxnLink.amount)
        )
        .where(
            M.StmtTxnLink.tenant_id == ctx.tenant.id,
            M.StmtTxnLink.link_type == "VEND_INV",
            M.StmtTxnLink.txn_id.in_(txn_ids)
        )
        .group_by(M.StmtTxnLink.txn_id)
    ).all()

    return {k: float(v or 0) for k, v in rows}
def _attached_sum(ctx, **where) -> Decimal:
    """Money attached (the cash that moved), excluding any TDS."""
    q = select(func.coalesce(func.sum(M.StmtTxnLink.amount), 0)).where(
        M.StmtTxnLink.tenant_id == ctx.tenant.id)
    for k, v in where.items():
        q = q.where(getattr(M.StmtTxnLink, k) == v)
    return Decimal(str(ctx.db.execute(q).scalar_one()))


def _tds_sum(ctx, **where) -> Decimal:
    q = select(func.coalesce(func.sum(M.StmtTxnLink.tds), 0)).where(
        M.StmtTxnLink.tenant_id == ctx.tenant.id)
    for k, v in where.items():
        q = q.where(getattr(M.StmtTxnLink, k) == v)
    return Decimal(str(ctx.db.execute(q).scalar_one()))


def _gst_sum(ctx, **where) -> Decimal:
    """GST withheld on attachments (v5.0)."""
    q = select(func.coalesce(func.sum(M.StmtTxnLink.gst_tds), 0)).where(
        M.StmtTxnLink.tenant_id == ctx.tenant.id)
    for k, v in where.items():
        q = q.where(getattr(M.StmtTxnLink, k) == v)
    return Decimal(str(ctx.db.execute(q).scalar_one()))


def _booked(ctx, **where) -> Decimal:
    """What is settled on an invoice from bank attachments: money collected
    or paid plus TDS deducted plus GST withheld."""
    return _attached_sum(ctx, **where) + _tds_sum(ctx, **where) + _gst_sum(ctx, **where)


# ------------------------------------------------ receipts from the bank (v4.9)

def _guess_mode(descr: str) -> str:
    """The payment mode a bank narration points to; NEFT when it says none."""
    d = (descr or "").upper()
    for key, mode in (("UPI", "UPI"), ("IMPS", "IMPS"), ("RTGS", "RTGS"),
                      ("CHQ", "Cheque"), ("CHEQUE", "Cheque"), ("CLG", "Cheque")):
        if key in d:
            return mode
    return "NEFT"


def _legacy_booked(ctx, invoice_id=None, vinv_id=None) -> Decimal:
    """Money and TDS attached to an invoice by attachments that posted no
    payment entry: customer invoices attached before v4.9, vendor invoices
    attached before v5.0. Counted so nothing is settled twice."""
    q = select(func.coalesce(func.sum(
        M.StmtTxnLink.amount + M.StmtTxnLink.tds + M.StmtTxnLink.gst_tds), 0)).where(
        M.StmtTxnLink.tenant_id == ctx.tenant.id,
        M.StmtTxnLink.payment_id.is_(None))
    q = q.where(M.StmtTxnLink.invoice_id == invoice_id) if invoice_id \
        else q.where(M.StmtTxnLink.vinv_id == vinv_id)
    return Decimal(str(ctx.db.execute(q).scalar_one()))


def _cust_open(ctx, inv) -> Decimal:
    """What is still to be received on a customer invoice: its total less
    every receipt on Customer Payments (including those posted from the bank
    statement) and less older attachments that posted none."""
    from ..service import invoice_tax, settled
    return (invoice_tax(ctx, inv).rounded - settled(ctx, invoice_id=inv.id)
            - _legacy_booked(ctx, invoice_id=inv.id))


def _vend_open(ctx, vi) -> Decimal:
    """What is still to be paid on a vendor invoice (v5.0): its total less
    every payment on Vendor Payments (including those posted from the bank
    statement) and less older attachments that posted none. Before v5.0 the
    bank statement and Vendor Payments each kept their own count."""
    from ..service import vinv_tax, settled
    return (vinv_tax(ctx, vi).rounded - settled(ctx, vinv_id=vi.id)
            - _legacy_booked(ctx, vinv_id=vi.id))


def _post_receipt(ctx, link, t, a):
    """Record the payment entry for an invoice attached on the statement, so
    the invoice shows as paid or part paid everywhere: a receipt on Customer
    Payments for a customer invoice (v4.9), a payment on Vendor Payments for
    a vendor invoice (v5.0). It carries the TDS and GST withheld."""
    ctx.db.flush()                      # link.id, for the narration
    vend = link.link_type == "VEND_INV"
    p = M.Payment(tenant_id=ctx.tenant.id, pay_type="PAY" if vend else "REC",
                  pay_date=t.txn_date,
                  invoice_id=None if vend else link.invoice_id,
                  vinv_id=link.vinv_id if vend else None,
                  amount=link.amount, tds=link.tds or 0, gst_tds=link.gst_tds or 0,
                  mode=_guess_mode(t.descr), bank_ref=(t.descr or "")[:60] or None,
                  bank_acct=(a.label or "")[:80] or None,
                  narration=f"Bank statement attachment #{link.id}")
    ctx.db.add(p)
    ctx.db.flush()
    link.payment_id = p.id
    return p


def _drop_receipts(ctx, payment_ids) -> int:
    """Delete receipts posted from the bank statement, with any reversal an
    invoice cancellation made of them."""
    ids = [i for i in payment_ids if i]
    if not ids:
        return 0
    ctx.db.execute(delete(M.Payment).where(
        M.Payment.tenant_id == ctx.tenant.id,
        M.Payment.reverses_id.in_(ids)).execution_options(synchronize_session=False))
    ctx.db.execute(delete(M.Payment).where(
        M.Payment.tenant_id == ctx.tenant.id,
        M.Payment.id.in_(ids)).execution_options(synchronize_session=False))
    return len(ids)


def _link_txn(ctx, tid):
    """The transaction to attach to, and its account, checking the caller
    holds the screen for that kind of account. On a card only a spend can
    carry an invoice, and not one marked personal."""
    t = ctx.get(M.StmtTxn, tid)

    if not t:
        raise HTTPException(404, "No such transaction")

    a = ctx.get(M.StmtAccount, t.account_id)

    ctx.require(_perm_for(a.kind))

    if a.kind == "CARD":
        if t.debit <= 0:
            raise HTTPException(
                422,
                "This is a payment or refund on the card, not a spend — "
                "vendor invoices are attached to card spends."
            )

        if t.allocation == "PERSONAL":
            raise HTTPException(
                422,
                "This spend is marked personal. Mark it company before "
                "attaching the vendor invoice it paid."
            )

    return t, a


def _director_out(dr):
    return {"id": dr.id, "name": dr.name, "din": dr.din, "pan": dr.pan,
            "active": dr.active}


def _active_directors(ctx):
    return ctx.db.execute(ctx.scope(select(M.Director), M.Director)
                          .where(M.Director.active.is_(True))
                          .order_by(M.Director.name)).scalars().all()


@router.get("/txns/{tid}/attachables")
def attachables(
    tid: int,
    ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))
):
    """What this transaction can be attached to. A credit lists customer tax
    invoices, employees (money paid back) and directors (a loan received); a
    debit lists vendor invoices, employees and directors (a loan repaid).
    Each invoice shows its total, what is already collected or paid against
    it from bank transactions, any TDS already booked, and the open amount.
    An invoice matching the transaction exactly comes first."""
    from ..service import invoice_tax, vinv_tax, settled
    t, a = _link_txn(ctx, tid)
    card = a.kind == "CARD"
    remaining = (t.credit or t.debit) - _attached_sum(ctx, txn_id=t.id)
    out = {
        "side": "CREDIT" if t.credit > 0 else "DEBIT",
        "account_kind": a.kind,
        "amount": float(t.credit or t.debit),
        "remaining": float(remaining),
        "customer_invoices": [],
        "vendor_invoices": [],
        "employees": [],
        "directors": [],
        "expense_heads": []
    }

    def _row(doc, tx, booked, party):
        collected = float(_attached_sum(ctx, **booked))
        tds = float(_tds_sum(ctx, **booked))
        gst = float(_gst_sum(ctx, **booked))
        open_amt = round(float(tx.rounded) - collected - tds - gst, 2)
        return {"id": doc.id, "doc_no": doc.doc_no, "doc_date": doc.doc_date.isoformat(),
                "party": party, "total": float(tx.rounded), "taxable": float(tx.taxable),
                "attached": collected, "tds": tds, "gst_tds": gst, "open": open_amt,
                "exact": abs(open_amt - float(remaining)) < 0.005}

    if t.credit > 0:
        invs = ctx.db.execute(ctx.scope(select(M.Invoice), M.Invoice).where(
            M.Invoice.doc_type == "TAX", M.Invoice.status == "ACTIVE")
            .order_by(M.Invoice.doc_date.desc())).scalars().all()
        for inv in invs:
            r = _row(inv, invoice_tax(ctx, inv), {"invoice_id": inv.id},
                     inv.customer.name)
            # Receipts recorded by hand on Customer Payments count too: an
            # invoice already paid there is not offered again.
            r["open"] = round(float(_cust_open(ctx, inv)), 2)
            r["exact"] = abs(r["open"] - float(remaining)) < 0.005
            linked = float(_booked(ctx, invoice_id=inv.id) - _legacy_booked(ctx, invoice_id=inv.id))
            r["receipts"] = round(float(settled(ctx, invoice_id=inv.id)) - linked, 2)
            r.update(_withheld_totals(ctx, invoice_id=inv.id))
            if r["open"] > 0:
                out["customer_invoices"].append(r)
        out["customer_invoices"].sort(key=lambda r: not r["exact"])
    else:
        vis = ctx.db.execute(ctx.scope(select(M.VendorInvoice), M.VendorInvoice)
                             .order_by(M.VendorInvoice.doc_date.desc())).scalars().all()
        for vi in vis:
            r = _row(vi, vinv_tax(ctx, vi), {"vinv_id": vi.id}, vi.vendor.name)
            # v5.0: payments entered by hand on Vendor Payments count too, as
            # receipts do on the customer side.
            r["open"] = round(float(_vend_open(ctx, vi)), 2)
            r["exact"] = abs(r["open"] - float(remaining)) < 0.005
            linked = float(_booked(ctx, vinv_id=vi.id) - _legacy_booked(ctx, vinv_id=vi.id))
            r["payments"] = round(float(settled(ctx, vinv_id=vi.id)) - linked, 2)
            r["receipts"] = r["payments"]
            r.update(_withheld_totals(ctx, vinv_id=vi.id))
            if r["open"] > 0:
                out["vendor_invoices"].append(r)
        out["vendor_invoices"].sort(key=lambda r: not r["exact"])
    if card:
        return out
    emps = ctx.db.execute(ctx.scope(select(M.Employee), M.Employee)
                          .where(M.Employee.active.is_(True))
                          .order_by(M.Employee.emp_code)).scalars().all()
    out["employees"] = [{"id": e.id, "emp_code": e.emp_code,
                         "name": f"{e.first_name} {e.last_name}", "email": e.email}
                        for e in emps]
    out["directors"] = [{**_director_out(dr), **_director_balance(ctx, dr.id)}
                        for dr in _active_directors(ctx)]
    if t.debit > 0:
        from .expenses import active_heads
        out["expense_heads"] = [{"id": h.id, "exp_code": h.exp_code, "name": h.name}
                                for h in active_heads(ctx)]
    return out


class LinkIn(BaseModel):
    link_type: str = Field(pattern="^(CUST_INV|VEND_INV|EMPLOYEE|DIRECTOR_LOAN|GOVT)$")
    ref_id: int | None = None           # not used for GOVT
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    # v4.8 — TDS on an invoice attachment: the part of the invoice settled by
    # tax deducted at source rather than by money.
    tds: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    purpose: str | None = Field(default=None, pattern="^(SALARY|EXPENSE|REFUND)$")
    expense_id: int | None = None
    notes: str | None = Field(default=None, max_length=200)
    # v5.0 — GST withheld on an invoice attachment (GST TDS, CGST Act s.51)
    gst_tds: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    # v5.0 — a payment to the government (statutory compliance)
    govt_kind: str | None = Field(default=None, pattern="^(GST|TDS|PF|ESI|OTHER)$")
    govt_period: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    challan_ref: str | None = Field(default=None, max_length=40)
    govt_descr: str | None = Field(default=None, max_length=120)


@router.post("/txns/{tid}/links", status_code=201)
def add_link(
    tid: int,
    body: LinkIn,
    ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))
):
    """Attach a transaction to what it was for.

    Credit: a customer invoice, an employee paying money back, or a loan
    received from a director. Debit: a vendor invoice, an employee's salary
    or expense, or a loan repaid to a director.

    With no amount, the smaller of what is left on the transaction and what
    is open on the invoice is attached. On an invoice, TDS may be given as
    well: amount plus TDS can never exceed what is open on the invoice."""
    t, a = _link_txn(ctx, tid)
    link = _add_link(ctx, t, a, body)
    ctx.db.commit()
    return _link_out(ctx, link)


def _add_link(ctx, t, a, body: LinkIn):
    """Attach one transaction (not committed, so several can go together)."""
    from ..service import invoice_tax, vinv_tax
    if a.kind == "CARD" and body.link_type != "VEND_INV":
        raise HTTPException(
            422,
            "A card spend is attached to the vendor invoice it paid. "
            "Customer invoices, employees and director loans are attached on "
            "Bank Statements."
        )
    is_credit = t.credit > 0
    remaining = (t.credit or t.debit) - _attached_sum(ctx, txn_id=t.id)
    if remaining <= 0:
        raise HTTPException(409, "The whole of this transaction is already attached. "
                            "Remove an attachment first to change it.")
    if (body.tds or body.gst_tds) and body.link_type not in ("CUST_INV", "VEND_INV"):
        raise HTTPException(422, "TDS and GST withheld are recorded against an invoice only")
    if body.link_type != "GOVT" and body.ref_id is None:
        raise HTTPException(422, "Pick what this transaction is for")
    link = M.StmtTxnLink(tenant_id=ctx.tenant.id, txn_id=t.id, link_type=body.link_type,
                         notes=(body.notes or "").strip() or None, linked_by=ctx.user.name)
    cap = remaining
    open_amt = None

    if body.link_type == "CUST_INV":
        if not is_credit:
            raise HTTPException(422, "A customer invoice is attached to money received — "
                                "pick a credit in the statement, not a debit.")
        inv = ctx.get(M.Invoice, body.ref_id)
        if not inv:
            raise HTTPException(404, "No such customer invoice")
        if inv.doc_type != "TAX" or inv.status != "ACTIVE":
            raise HTTPException(422, f"{inv.doc_no} is not an active tax invoice")
        if ctx.db.execute(select(func.count()).select_from(M.StmtTxnLink).where(
                M.StmtTxnLink.tenant_id == ctx.tenant.id, M.StmtTxnLink.txn_id == t.id,
                M.StmtTxnLink.invoice_id == inv.id)).scalar_one():
            raise HTTPException(409, f"{inv.doc_no} is already attached to this transaction")
        open_amt = _cust_open(ctx, inv)
        if open_amt <= 0:
            raise HTTPException(409, f"{inv.doc_no} is already fully paid — by bank credits, "
                                "receipts on Customer Payments or TDS")
        link.invoice_id, cap = inv.id, min(remaining, open_amt)
        doc_no = inv.doc_no
    elif body.link_type == "VEND_INV":
        if is_credit:
            raise HTTPException(422, "A vendor invoice is attached to money paid out — "
                                "pick a debit in the statement, not a credit.")
        vi = ctx.get(M.VendorInvoice, body.ref_id)
        if not vi:
            raise HTTPException(404, "No such vendor invoice")
        if ctx.db.execute(select(func.count()).select_from(M.StmtTxnLink).where(
                M.StmtTxnLink.tenant_id == ctx.tenant.id, M.StmtTxnLink.txn_id == t.id,
                M.StmtTxnLink.vinv_id == vi.id)).scalar_one():
            raise HTTPException(409, f"{vi.doc_no} is already attached to this transaction")
        open_amt = _vend_open(ctx, vi)
        if open_amt <= 0:
            raise HTTPException(
                409,
                f"{vi.doc_no} is already fully paid — by bank debits, card spends, "
                "payments on Vendor Payments or TDS"
            )
        link.vinv_id, cap = vi.id, min(remaining, open_amt)
        doc_no = vi.doc_no
    elif body.link_type == "EMPLOYEE":
        e = ctx.get(M.Employee, body.ref_id)
        if not e:
            raise HTTPException(404, "No such employee")
        if not e.active:
            raise HTTPException(422, f"{e.first_name} {e.last_name} is marked inactive")
        link.employee_id = e.id
        if is_credit:
            # Money received from an employee: an advance or excess paid back.
            if body.purpose not in (None, "REFUND"):
                raise HTTPException(422, "Money received from an employee is recorded as "
                                    "a refund — salary and expenses are paid out as debits.")
            link.purpose = "REFUND"
        else:
            if body.purpose not in ("SALARY", "EXPENSE"):
                raise HTTPException(422, "Say whether this is salary or an expense")
            link.purpose = body.purpose
            if body.purpose == "EXPENSE":
                if not body.expense_id:
                    raise HTTPException(422, "Pick the expense head this employee expense "
                                        "belongs to. Heads are kept on the Expenses screen.")
                h = ctx.get(M.ExpenseHead, body.expense_id)
                if not h:
                    raise HTTPException(404, "No such expense head")
                if not h.active:
                    raise HTTPException(422, f"{h.name} is marked inactive")
                link.expense_id = h.id
    elif body.link_type == "GOVT":
        # v5.0 — money paid to the government: GST, TDS, PF, ESI or another
        # statutory due, with the month it is for and the challan reference.
        if is_credit:
            raise HTTPException(422, "A government payment is money paid out — pick a debit "
                                "in the statement, not a credit.")
        if not body.govt_kind:
            raise HTTPException(422, "Say what was paid: GST, TDS, PF, ESI or other")
        descr = (body.govt_descr or "").strip()
        if body.govt_kind == "OTHER" and not descr:
            raise HTTPException(422, "Say what the other statutory payment was for "
                                "(professional tax, labour welfare fund, …)")
        link.govt_kind = body.govt_kind
        link.govt_period = body.govt_period
        link.challan_ref = (body.challan_ref or "").strip() or None
        link.govt_descr = descr or None
    else:  # DIRECTOR_LOAN — credit: loan received; debit: loan repaid
        dr = ctx.get(M.Director, body.ref_id)
        if not dr:
            raise HTTPException(404, "No such director")
        if not dr.active:
            raise HTTPException(422, f"{dr.name} is marked inactive")
        link.director_id = dr.id

    amount = Decimal(str(body.amount)) if body.amount is not None else cap
    tds = Decimal(str(body.tds)) if body.tds else Decimal("0")
    gst = Decimal(str(body.gst_tds)) if body.gst_tds else Decimal("0")
    if amount > remaining:
        raise HTTPException(422, f"Only {remaining:.2f} of this transaction is left to attach")
    if open_amt is not None:
        if amount > open_amt:
            raise HTTPException(422, f"Only {open_amt:.2f} is open on that invoice")
        if amount + tds + gst > open_amt + CENT:
            raise HTTPException(
                422,
                f"Amount {amount:.2f} plus TDS {tds:.2f}"
                + (f" plus GST withheld {gst:.2f}" if gst else "")
                + f" is more than the {open_amt:.2f} open on {doc_no}")
    link.amount = amount
    link.tds = tds
    link.gst_tds = gst
    ctx.db.add(link)
    if link.link_type in ("CUST_INV", "VEND_INV"):
        _post_receipt(ctx, link, t, a)

    if a.kind == "CARD" and t.allocation != "COMPANY":
        # Paying a vendor's invoice is spending for the company.
        t.allocation = "COMPANY"
        t.allocated_by = ctx.user.name
        t.allocated_at = datetime.utcnow()

    ctx.db.flush()
    return link


class LinkTdsIn(BaseModel):
    # Neither given: book the whole balance still open on the invoice as TDS.
    # Either given: set it (0 clears it) and leave the other as it is.
    tds: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    gst_tds: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)


@router.put("/links/{lid}/tds")
def set_link_tds(
    lid: int,
    body: LinkTdsIn,
    ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))
):
    """Set the TDS on an invoice attachment after the fact — for when the
    last payment on an invoice was attached before it was known that the
    shortfall was tax deducted at source. With no figure, the balance still
    open on the invoice is booked as TDS; 0 clears it."""
    l = ctx.get(M.StmtTxnLink, lid)
    if not l:
        raise HTTPException(404, "No such attachment")
    t = ctx.get(M.StmtTxn, l.txn_id)
    ctx.require(_perm_for(ctx.get(M.StmtAccount, t.account_id).kind))
    if l.link_type == "CUST_INV":
        doc = ctx.get(M.Invoice, l.invoice_id)
        open_now = _cust_open(ctx, doc)
    elif l.link_type == "VEND_INV":
        doc = ctx.get(M.VendorInvoice, l.vinv_id)
        open_now = _vend_open(ctx, doc)
    else:
        raise HTTPException(422, "TDS and GST withheld are recorded against an invoice only")
    cur_tds, cur_gst = Decimal(str(l.tds or 0)), Decimal(str(l.gst_tds or 0))
    # what this link's TDS and GST withheld may come to together: what is
    # open on the invoice with this link's own withholding put back
    room = open_now + cur_tds + cur_gst
    if body.tds is None and body.gst_tds is None:
        tds, gst = room - cur_gst, cur_gst                   # the balance as TDS
    else:
        tds = cur_tds if body.tds is None else Decimal(str(body.tds))
        gst = cur_gst if body.gst_tds is None else Decimal(str(body.gst_tds))
    tds, gst = max(tds, Decimal("0")), max(gst, Decimal("0"))
    if tds + gst > room + CENT:
        raise HTTPException(422, f"Only {max(room, Decimal('0')):.2f} is left open on "
                            f"{doc.doc_no} to book as TDS and GST withheld")
    l.tds, l.gst_tds = tds, gst
    p = ctx.db.get(M.Payment, l.payment_id) if l.payment_id else None
    if p:
        p.tds, p.gst_tds = tds, gst     # the payment entry carries the same
    else:
        _post_receipt(ctx, l, t, ctx.get(M.StmtAccount, t.account_id))
    ctx.db.commit()
    return _link_out(ctx, l)


@router.delete("/links/{lid}", status_code=204)
def del_link(
    lid: int,
    ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))
):
    l = ctx.get(M.StmtTxnLink, lid)

    if not l:
        raise HTTPException(404, "No such attachment")

    t = ctx.get(M.StmtTxn, l.txn_id)

    ctx.require(
        _perm_for(
            ctx.get(M.StmtAccount, t.account_id).kind
        )
    )

    pid = l.payment_id
    ctx.db.delete(l)
    ctx.db.flush()
    _drop_receipts(ctx, [pid])          # the invoice goes back to unpaid
    ctx.db.commit()


# ------------------------------------------- an invoice's payments (v5.0)

def _withheld_totals(ctx, *, invoice_id=None, vinv_id=None) -> dict:
    """TDS and GST withheld on an invoice so far, from every payment entry
    (bank-posted or entered by hand) and older attachments without one."""
    col = M.Payment.invoice_id if invoice_id else M.Payment.vinv_id
    key = invoice_id or vinv_id
    tds, gst = ctx.db.execute(select(
        func.coalesce(func.sum(M.Payment.tds), 0), func.coalesce(func.sum(M.Payment.gst_tds), 0))
        .where(M.Payment.tenant_id == ctx.tenant.id, col == key)).one()
    lcol = M.StmtTxnLink.invoice_id if invoice_id else M.StmtTxnLink.vinv_id
    ltds, lgst = ctx.db.execute(select(
        func.coalesce(func.sum(M.StmtTxnLink.tds), 0), func.coalesce(func.sum(M.StmtTxnLink.gst_tds), 0))
        .where(M.StmtTxnLink.tenant_id == ctx.tenant.id, lcol == key,
               M.StmtTxnLink.payment_id.is_(None))).one()
    return {"tds_total": round(float(tds) + float(ltds), 2),
            "gst_tds_total": round(float(gst) + float(lgst), 2)}


def _invoice_doc(ctx, link_type, ref_id):
    from ..service import invoice_tax, vinv_tax
    if link_type == "CUST_INV":
        inv = ctx.get(M.Invoice, ref_id)
        if not inv or inv.doc_type != "TAX":
            raise HTTPException(404, "No such customer tax invoice")
        return inv, invoice_tax(ctx, inv), inv.customer.name, _cust_open(ctx, inv), {"invoice_id": inv.id}
    vi = ctx.get(M.VendorInvoice, ref_id)
    if not vi:
        raise HTTPException(404, "No such vendor invoice")
    return vi, vinv_tax(ctx, vi), vi.vendor.name, _vend_open(ctx, vi), {"vinv_id": vi.id}


def _invoice_summary(ctx, link_type, ref_id) -> dict:
    """An invoice with every payment against it — from the bank statement and
    entered by hand — and the TDS and GST withheld on each."""
    doc, tx, party, open_amt, key = _invoice_doc(ctx, link_type, ref_id)
    from_bank = {pid: (lbl, descr) for pid, lbl, descr in ctx.db.execute(
        select(M.StmtTxnLink.payment_id, M.StmtAccount.label, M.StmtTxn.descr)
        .join(M.StmtTxn, M.StmtTxn.id == M.StmtTxnLink.txn_id)
        .join(M.StmtAccount, M.StmtAccount.id == M.StmtTxn.account_id)
        .where(M.StmtTxnLink.tenant_id == ctx.tenant.id,
               M.StmtTxnLink.payment_id.is_not(None))).all()}
    col = M.Payment.invoice_id if link_type == "CUST_INV" else M.Payment.vinv_id
    rows = []
    for p in ctx.db.execute(select(M.Payment).where(
            M.Payment.tenant_id == ctx.tenant.id, col == doc.id)
            .order_by(M.Payment.pay_date, M.Payment.id)).scalars():
        b = from_bank.get(p.id)
        rows.append({"date": p.pay_date.isoformat(), "amount": float(p.amount), "tds": float(p.tds or 0),
                     "gst_tds": float(p.gst_tds or 0),
                     "source": f"Bank statement · {b[0]}" if b else
                               ("Reversal" if p.reverses_id else f"Entered by hand · {p.mode}"),
                     "ref": (b[1] if b else p.bank_ref) or "", "from_bank": bool(b),
                     "reversal": bool(p.reverses_id)})
    lcol = M.StmtTxnLink.invoice_id if link_type == "CUST_INV" else M.StmtTxnLink.vinv_id
    for l, t, a in ctx.db.execute(
            select(M.StmtTxnLink, M.StmtTxn, M.StmtAccount)
            .join(M.StmtTxn, M.StmtTxn.id == M.StmtTxnLink.txn_id)
            .join(M.StmtAccount, M.StmtAccount.id == M.StmtTxn.account_id)
            .where(M.StmtTxnLink.tenant_id == ctx.tenant.id, lcol == doc.id,
                   M.StmtTxnLink.payment_id.is_(None))).all():
        rows.append({"date": t.txn_date.isoformat(), "amount": float(l.amount), "tds": float(l.tds or 0),
                     "gst_tds": float(l.gst_tds or 0), "source": f"Bank statement · {a.label}",
                     "ref": t.descr or "", "from_bank": True, "reversal": False})
    rows.sort(key=lambda r: r["date"])
    paid = round(sum(r["amount"] for r in rows), 2)
    tds = round(sum(r["tds"] for r in rows), 2)
    gst = round(sum(r["gst_tds"] for r in rows), 2)
    return {"link_type": link_type, "id": doc.id, "doc_no": doc.doc_no, "doc_date": doc.doc_date.isoformat(),
            "party": party, "total": float(tx.rounded), "taxable": float(tx.taxable),
            "gst": round(float(tx.rounded) - float(tx.taxable), 2),
            "paid": paid, "tds": tds, "gst_tds": gst, "open": round(float(open_amt), 2),
            "payments": rows}


def _candidates(ctx, link_type, doc, open_amt) -> list:
    """Bank lines (and, for a vendor invoice, company card spends) with money
    still to attach, on the right side, from 90 days before the invoice."""
    credit = link_type == "CUST_INV"
    q = (select(M.StmtTxn, M.StmtAccount)
         .join(M.StmtAccount, M.StmtAccount.id == M.StmtTxn.account_id)
         .where(M.StmtTxn.tenant_id == ctx.tenant.id,
                M.StmtTxn.txn_date >= doc.doc_date - timedelta(days=90)))
    q = q.where(M.StmtTxn.credit > 0, M.StmtAccount.kind == "BANK") if credit \
        else q.where(M.StmtTxn.debit > 0)
    allowed = {k for k in ("BANK", "CARD") if _perm_for(k) in ctx.perms}
    out = []
    for t, a in ctx.db.execute(q.order_by(M.StmtTxn.txn_date)).all():
        if a.kind not in allowed or (a.kind == "CARD" and t.allocation == "PERSONAL"):
            continue
        left = float((t.credit or t.debit) - _attached_sum(ctx, txn_id=t.id))
        if left <= 0.005:
            continue
        out.append({"txn_id": t.id, "date": t.txn_date.isoformat(), "descr": t.descr,
                    "account": a.label, "account_kind": a.kind,
                    "amount": float(t.credit or t.debit), "remaining": round(left, 2),
                    "exact": abs(left - float(open_amt)) < 0.005})
    out.sort(key=lambda r: (not r["exact"], abs(r["remaining"] - float(open_amt))))
    return out[:100]


@router.get("/invoice-payments")
def invoice_payments(
    link_type: str = Query(..., pattern="^(CUST_INV|VEND_INV)$"), id: int = Query(...),
    ctx: Ctx = Depends(need_any("bankstmt", "cardstmt", "saved", "vinv", "crec", "vpay"))
):
    """An invoice's payments with TDS and GST withheld on each, and — for
    someone who can work Bank Statements — the bank lines that could still
    be attached to it."""
    out = _invoice_summary(ctx, link_type, id)
    can_attach = bool({"bankstmt", "cardstmt"} & ctx.perms)
    out["can_attach"] = can_attach
    out["candidates"] = []
    if can_attach and out["open"] > 0.005:
        doc = _invoice_doc(ctx, link_type, id)[0]
        out["candidates"] = _candidates(ctx, link_type, doc, out["open"])
    return out


class MatchItem(BaseModel):
    txn_id: int
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)


class MatchIn(BaseModel):
    link_type: str = Field(pattern="^(CUST_INV|VEND_INV)$")
    ref_id: int
    items: list[MatchItem] = Field(min_length=1, max_length=50)
    tds: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    gst_tds: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    notes: str | None = Field(default=None, max_length=200)


@router.post("/invoice-payments", status_code=201)
def match_invoice_payments(body: MatchIn, ctx: Ctx = Depends(need_any("bankstmt", "cardstmt"))):
    """Attach several bank lines to one invoice at once (v5.0). The TDS and
    GST withheld go on the last line, which closes the invoice. All or
    nothing: if any line cannot be attached, none is."""
    if len({i.txn_id for i in body.items}) != len(body.items):
        raise HTTPException(422, "The same bank line is listed twice")
    try:
        for n, it in enumerate(body.items):
            t, a = _link_txn(ctx, it.txn_id)
            last = n == len(body.items) - 1
            _add_link(ctx, t, a, LinkIn(
                link_type=body.link_type, ref_id=body.ref_id, amount=it.amount,
                tds=body.tds if last else None, gst_tds=body.gst_tds if last else None,
                notes=body.notes))
    except HTTPException as e:
        ctx.db.rollback()
        raise HTTPException(e.status_code, f"Line {n + 1}: {e.detail} — nothing was attached.") from None
    ctx.db.commit()
    return _invoice_summary(ctx, body.link_type, body.ref_id)


# ------------------------------------------- statutory payments (v5.0)

@router.get("/govt-payments")
def govt_payments(period: str | None = None, ctx: Ctx = Depends(need_any("bankstmt", "registers"))):
    """Payments to the government attached on Bank Statements — GST, TDS,
    PF, ESI and other statutory dues — for a month or a financial year."""
    q = (select(M.StmtTxnLink, M.StmtTxn, M.StmtAccount)
         .join(M.StmtTxn, M.StmtTxn.id == M.StmtTxnLink.txn_id)
         .join(M.StmtAccount, M.StmtAccount.id == M.StmtTxn.account_id)
         .where(M.StmtTxnLink.tenant_id == ctx.tenant.id, M.StmtTxnLink.link_type == "GOVT"))
    if period:
        lo, hi = _view_bounds(ctx, period)
        q = q.where(M.StmtTxn.txn_date >= lo, M.StmtTxn.txn_date < hi)
    rows, by_kind = [], {k: 0.0 for k in GOVT_LABEL}
    for l, t, a in ctx.db.execute(q.order_by(M.StmtTxn.txn_date, M.StmtTxnLink.id)).all():
        amt = float(l.amount)
        by_kind[l.govt_kind] = round(by_kind[l.govt_kind] + amt, 2)
        rows.append({"id": l.id, "date": t.txn_date.isoformat(), "kind": l.govt_kind,
                     "kind_label": GOVT_LABEL[l.govt_kind], "for_month": l.govt_period,
                     "challan_ref": l.challan_ref, "descr": l.govt_descr, "amount": amt,
                     "account": a.label, "bank_ref": t.descr, "notes": l.notes})
    return {"period": period, "rows": rows,
            "by_kind": [{"kind": k, "label": GOVT_LABEL[k], "amount": v} for k, v in by_kind.items()],
            "total": round(sum(r["amount"] for r in rows), 2)}


# --------------------------------------------------------------- directors (v4.8)

class DirectorIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    din: str | None = Field(default=None, max_length=8)
    pan: str | None = Field(default=None, max_length=10)
    active: bool = True


def _director_balance(ctx, director_id, upto=None) -> dict:
    """Loans received from and repaid to a director through bank attachments."""
    def _side(col):
        q = (select(func.coalesce(func.sum(M.StmtTxnLink.amount), 0))
             .join(M.StmtTxn, M.StmtTxn.id == M.StmtTxnLink.txn_id)
             .where(M.StmtTxnLink.tenant_id == ctx.tenant.id,
                    M.StmtTxnLink.link_type == "DIRECTOR_LOAN",
                    M.StmtTxnLink.director_id == director_id, col > 0))
        if upto:
            q = q.where(M.StmtTxn.txn_date < upto)
        return Decimal(str(ctx.db.execute(q).scalar_one()))
    received, repaid = _side(M.StmtTxn.credit), _side(M.StmtTxn.debit)
    return {"received": float(received), "repaid": float(repaid),
            "balance": float(received - repaid)}


def _clean_director(body: DirectorIn) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Give the director's name")
    din = (body.din or "").strip() or None
    if din and not re.fullmatch(r"\d{8}", din):
        raise HTTPException(422, "A DIN is 8 digits")
    pan = (body.pan or "").strip().upper() or None
    if pan and not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", pan):
        raise HTTPException(422, "A PAN is 10 characters, like ABCDE1234F")
    return {"name": name, "din": din, "pan": pan, "active": body.active}


@router.get("/directors")
def directors(ctx: Ctx = Depends(need("bankstmt"))):
    rows = ctx.db.execute(ctx.scope(select(M.Director), M.Director)
                          .order_by(M.Director.name)).scalars().all()
    return [{**_director_out(d), **_director_balance(ctx, d.id)} for d in rows]


@router.post("/directors", status_code=201)
def add_director(body: DirectorIn, ctx: Ctx = Depends(need("bankstmt"))):
    v = _clean_director(body)
    dup = ctx.db.execute(ctx.scope(select(M.Director), M.Director)
                         .where(func.lower(M.Director.name) == v["name"].lower())).scalars().first()
    if dup:
        raise HTTPException(409, f"{dup.name} is already on the list of directors")
    d = M.Director(tenant_id=ctx.tenant.id, **v)
    ctx.db.add(d)
    ctx.db.commit()
    return {**_director_out(d), **_director_balance(ctx, d.id)}


@router.put("/directors/{did}")
def edit_director(did: int, body: DirectorIn, ctx: Ctx = Depends(need("bankstmt"))):
    d = ctx.get(M.Director, did)
    if not d:
        raise HTTPException(404, "No such director")
    v = _clean_director(body)
    dup = ctx.db.execute(ctx.scope(select(M.Director), M.Director)
                         .where(func.lower(M.Director.name) == v["name"].lower(),
                                M.Director.id != did)).scalars().first()
    if dup:
        raise HTTPException(409, f"{dup.name} is already on the list of directors")
    for k, val in v.items():
        setattr(d, k, val)
    ctx.db.commit()
    return {**_director_out(d), **_director_balance(ctx, d.id)}


@router.get("/director-loans")
def director_loans(period: str | None = None, ctx: Ctx = Depends(need("bankstmt"))):
    """Loan account of each director: the balance brought forward, what was
    received and repaid in the month, and the balance owed at month end.
    With no month, the whole history."""
    lo = hi = None
    if period:
        lo, hi = _view_bounds(ctx, period)              # a month or a financial year
    out, entries = [], []
    for d in ctx.db.execute(ctx.scope(select(M.Director), M.Director)
                            .order_by(M.Director.name)).scalars().all():
        opening = _director_balance(ctx, d.id, upto=lo)["balance"] if lo else 0.0
        q = (select(M.StmtTxnLink, M.StmtTxn, M.StmtAccount)
             .join(M.StmtTxn, M.StmtTxn.id == M.StmtTxnLink.txn_id)
             .join(M.StmtAccount, M.StmtAccount.id == M.StmtTxn.account_id)
             .where(M.StmtTxnLink.tenant_id == ctx.tenant.id,
                    M.StmtTxnLink.link_type == "DIRECTOR_LOAN",
                    M.StmtTxnLink.director_id == d.id))
        if lo:
            q = q.where(M.StmtTxn.txn_date >= lo, M.StmtTxn.txn_date < hi)
        received = repaid = 0.0
        for l, t, a in ctx.db.execute(q.order_by(M.StmtTxn.txn_date, M.StmtTxnLink.id)).all():
            is_in = t.credit > 0
            amt = float(l.amount)
            received += amt if is_in else 0
            repaid += 0 if is_in else amt
            entries.append({"date": t.txn_date.isoformat(), "director": d.name,
                            "account": a.label, "descr": t.descr,
                            "kind": "RECEIVED" if is_in else "REPAID",
                            "amount": amt, "notes": l.notes})
        if not (opening or received or repaid) and not d.active:
            continue
        out.append({**_director_out(d), "opening": round(opening, 2),
                    "received": round(received, 2), "repaid": round(repaid, 2),
                    "closing": round(opening + received - repaid, 2)})
    entries.sort(key=lambda e: e["date"])
    return {"period": period, "directors": out, "entries": entries,
            "total_owed": round(sum(r["closing"] for r in out), 2)}

# --------------------------------------------------------------- reconciliation

FY_VIEW_RE = re.compile(r"^(?:FY)?\d{4}-\d{2}$", re.I)


def _is_fy(period) -> bool:
    """A financial-year label (FY2026-27 / 2026-27), not a month (2026-04)."""
    return bool(period) and not PERIOD_RE.match(period) and bool(FY_VIEW_RE.match(period))


def _view_bounds(ctx, period):
    """(first day, day after the last) of a month "YYYY-MM" or a financial
    year "FY2026-27" (v5.0: Bank Statements open on the financial year)."""
    if PERIOD_RE.match(period or ""):
        return _month_bounds(period)
    if _is_fy(period):
        from ..fy import fy_bounds
        lo, hi = fy_bounds(ctx.tenant, period.upper().removeprefix("FY"))
        return lo, hi + timedelta(days=1)
    raise HTTPException(422, "Give a month as YYYY-MM or a financial year as FY2026-27")


def _months_between(lo, hi):
    """The YYYY-MM months from lo up to (not including) hi."""
    out, y, m = [], lo.year, lo.month
    while date(y, m, 1) < hi:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _in_period(q, account, period, ctx=None):
    """A bank statement follows the calendar month, so its rows are picked by
    date. A card statement runs from one billing date to the next (13 Aug to
    12 Sep, say), so its rows belong to the statement month they were
    uploaded under, whatever their dates."""
    if account.kind == "CARD":
        months = [period] if PERIOD_RE.match(period) else _months_between(*_view_bounds(ctx, period))
        ups = select(M.StmtUpload.id).where(M.StmtUpload.tenant_id == account.tenant_id,
                                            M.StmtUpload.account_id == account.id,
                                            M.StmtUpload.period.in_(months))
        return q.where(M.StmtTxn.upload_id.in_(ups))
    lo, hi = _view_bounds(ctx, period) if ctx else _month_bounds(period)
    return q.where(M.StmtTxn.txn_date >= lo, M.StmtTxn.txn_date < hi)


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
            q = _in_period(q, a, period, ctx)          # v5.0: a month or a financial year
        rows = ctx.db.execute(q).scalars().all()
        inv_paid = _vinv_attached(ctx, [t.id for t in rows])

        company = sum(t.debit for t in rows if t.allocation == "COMPANY")
        personal = sum(t.debit for t in rows if t.allocation == "PERSONAL")
        unalloc = sum(t.debit for t in rows if t.allocation == "UNALLOCATED")
        paid = sum(t.credit for t in rows)
        by_cat = {}
        for t in rows:
            if t.allocation == "COMPANY":
                rest = float(t.debit) - inv_paid.get(t.id, 0.0)
                if rest > 0.005:
                    by_cat[t.category or "Other"] = (
                        by_cat.get(t.category or "Other", 0) + rest
                    )

        vendor_paid = round(sum(inv_paid.values()), 2)
        out.append({"account": _acct_out(a),
                    "company": float(company), "personal": float(personal),
                    "unallocated": float(unalloc), "payments": float(paid),
                    "owed_to_director": float(company),
                    "vendor_invoices": vendor_paid,
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
    lo, hi = _view_bounds(ctx, period)                  # a month or a financial year

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

    bank_rows, card_company, card_unalloc, card_vinv = [], 0.0, 0.0, 0.0
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
              paid = _vinv_attached(
                  ctx,
                  [t.id for t in rows if t.allocation == "COMPANY"]
              )

              card_vinv += sum(paid.values())

              card_company += (
                  float(sum(t.debit for t in rows if t.allocation == "COMPANY"))
                  - sum(paid.values())
              )

              card_unalloc += float(
                  sum(t.debit for t in rows if t.allocation == "UNALLOCATED")
              )
    
    bank_debits = sum(b["debits"] for b in bank_rows)

    # Salary and expenses attached to employees on bank debits this month.
    emp = {"SALARY": 0.0, "EXPENSE": 0.0, "REFUND": 0.0}
    loans = {"received": 0.0, "repaid": 0.0}
    emp_heads = []
    if "bankstmt" in ctx.perms:
        for purpose, amt in ctx.db.execute(
                select(M.StmtTxnLink.purpose, func.sum(M.StmtTxnLink.amount))
                .join(M.StmtTxn, M.StmtTxn.id == M.StmtTxnLink.txn_id)
                .where(M.StmtTxnLink.tenant_id == ctx.tenant.id,
                       M.StmtTxnLink.link_type == "EMPLOYEE",
                       M.StmtTxn.txn_date >= lo, M.StmtTxn.txn_date < hi)
                .group_by(M.StmtTxnLink.purpose)).all():
            emp[purpose] = float(amt or 0)
        for credit_side, amt in ctx.db.execute(
                select(M.StmtTxn.credit > 0, func.sum(M.StmtTxnLink.amount))
                .join(M.StmtTxn, M.StmtTxn.id == M.StmtTxnLink.txn_id)
                .where(M.StmtTxnLink.tenant_id == ctx.tenant.id,
                       M.StmtTxnLink.link_type == "DIRECTOR_LOAN",
                       M.StmtTxn.txn_date >= lo, M.StmtTxn.txn_date < hi)
                .group_by(M.StmtTxn.credit > 0)).all():
            loans["received" if credit_side else "repaid"] = float(amt or 0)
        by_head = ctx.db.execute(
            select(M.ExpenseHead.exp_code, M.ExpenseHead.name, func.sum(M.StmtTxnLink.amount))
            .join(M.StmtTxnLink, M.StmtTxnLink.expense_id == M.ExpenseHead.id)
            .join(M.StmtTxn, M.StmtTxn.id == M.StmtTxnLink.txn_id)
            .where(M.StmtTxnLink.tenant_id == ctx.tenant.id,
                   M.StmtTxn.txn_date >= lo, M.StmtTxn.txn_date < hi)
            .group_by(M.ExpenseHead.exp_code, M.ExpenseHead.name)
            .order_by(M.ExpenseHead.exp_code)).all()
        emp_heads = [{"exp_code": c, "name": n, "amount": float(a or 0)} for c, n, a in by_head]
    return {
        "period": period,
        "vendor_invoices": {"count": len(vinvs), "total": inv_total},
        "vendor_payments": {"count": len(pays), "total": pay_total},
        "bank": bank_rows,
        "bank_debits_total": bank_debits,
        "card_company_expense": round(card_company, 2),
        "card_vendor_invoices": round(card_vinv, 2),
        "card_unallocated": card_unalloc,
        "employee_salary": emp["SALARY"],
        "employee_expense": emp["EXPENSE"],
        "employee_expense_by_head": emp_heads,
        # v4.8 — money employees paid back, and director loans in and out
        "employee_refunds": emp["REFUND"],
        "director_loans_received": loans["received"],
        "director_loans_repaid": loans["repaid"],
        "expense_recognised": inv_total + card_company + emp["SALARY"] + emp["EXPENSE"],
        "cash_out": bank_debits,
        # Payments recorded in the books that the bank statement should contain.
        "payments_vs_bank_gap": round(pay_total - bank_debits, 2),
        # Purchases booked vs paid this month: a timing gap, not necessarily an error.
        "invoices_vs_payments_gap": round(inv_total - pay_total, 2),
    }
