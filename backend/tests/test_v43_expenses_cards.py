"""v4.3: expense master, employee expenses booked to a head, and card
statements read the way banks actually print them."""
import pathlib, shutil
import pytest
from datetime import date
from decimal import Decimal
from tests.test_v42_bank_links import BANK_CSV, emp, bank, _card

RBL = pathlib.Path(__file__).parent / "fixtures" / "rbl_card_sample.pdf"


# ------------------------------------------------------------ expense master
def test_expense_master_holds_id_and_name(org):
    a = org()
    r = a.post("/api/expense-heads", json={"exp_code": "EXP001", "name": "Travel"})
    assert r.status_code == 201 and r.json()["exp_code"] == "EXP001"
    assert a.post("/api/expense-heads", json={"exp_code": "EXP001", "name": "Fuel"}).status_code == 409
    assert a.post("/api/expense-heads", json={"exp_code": "EXP002", "name": "Travel"}).status_code == 409


def test_standard_heads_can_be_loaded_once(org):
    a = org()
    a.post("/api/expense-heads", json={"exp_code": "EXP001", "name": "Travel"})
    n = a.post("/api/expense-heads/standard").json()["added"]
    assert n == 10
    assert a.post("/api/expense-heads/standard").json()["added"] == 0
    codes = [h["exp_code"] for h in a.get("/api/expense-heads").json()]
    assert len(codes) == len(set(codes)) == 11


def test_employee_expense_needs_a_head_and_is_reported_by_head(org):
    a = org(); e = emp(a); _, t = bank(a)
    reimb = t["REIMB TRAVEL ASHA"]
    r = a.post(f"/api/statements/txns/{reimb['id']}/links",
               json={"link_type": "EMPLOYEE", "ref_id": e, "purpose": "EXPENSE"})
    assert r.status_code == 422 and "expense head" in r.text
    h = a.post("/api/expense-heads", json={"exp_code": "EXP007", "name": "Travel"}).json()["id"]
    r = a.post(f"/api/statements/txns/{reimb['id']}/links",
               json={"link_type": "EMPLOYEE", "ref_id": e, "purpose": "EXPENSE", "expense_id": h})
    assert r.status_code == 201 and r.json()["expense"] == "EXP007 Travel"
    L = a.get("/api/statements/ledger?period=2026-08").json()
    assert L["employee_expense_by_head"] == [{"exp_code": "EXP007", "name": "Travel", "amount": 2500.0}]
    assert a.delete(f"/api/expense-heads/{h}").status_code == 409


def test_card_categories_come_from_the_expense_master(org):
    a = org()
    assert "Travel" in a.get("/api/statements/categories").json()     # standard list until set up
    a.post("/api/expense-heads", json={"exp_code": "E1", "name": "Client entertainment"})
    assert a.get("/api/statements/categories").json() == ["Client entertainment"]


def test_renaming_a_head_carries_card_spends_with_it(org):
    a = org(); cid = _card(a)
    h = a.post("/api/expense-heads", json={"exp_code": "E1", "name": "Travel"}).json()["id"]
    csv = b"Date,Description,Amount\n03/08/2026,INDIGO,8900.00\n"
    a.post(f"/api/statements/accounts/{cid}/upload?period=2026-08"
           "&default_allocation=COMPANY&default_category=Travel",
           files={"file": ("c.csv", csv, "text/csv")})
    a.put(f"/api/expense-heads/{h}", json={"exp_code": "E1", "name": "Air travel"})
    t = a.get(f"/api/statements/accounts/{cid}/txns?period=2026-08").json()[0]
    assert t["category"] == "Air travel"


# ------------------------------------------------------------ card PDF reading
@pytest.mark.skipif(shutil.which("tesseract") is None,
                    reason="this sample is a scan; reading it needs Tesseract OCR")
def test_rbl_two_column_card_statement_is_read_in_full(org):
    """The transactions sit beside the account summary, so most lines begin
    with summary text; the 'sample transaction' table on page 2 is an
    illustration from 2018-19 and must not be saved."""
    a = org(); cid = _card(a)
    r = a.post(f"/api/statements/accounts/{cid}/upload?period=2026-09",
               files={"file": ("RBL_Card.pdf", RBL.read_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    assert r.json()["statement_period"] == ["2026-08-13", "2026-09-12"]
    # a card statement's rows are listed under the month it was uploaded for,
    # though they run from 13 Aug to 12 Sep
    rows = a.get(f"/api/statements/accounts/{cid}/txns?period=2026-09").json()
    got = sorted((x["date"], x["debit"], x["credit"]) for x in rows)
    assert got == sorted([
        ("2026-08-13", 0.0, 307068.0),        # payment received
        ("2026-08-13", 200000.0, 0.0),        # two identical purchases, both kept
        ("2026-08-13", 200000.0, 0.0),
        ("2026-08-19", 21240.36, 0.0),
        ("2026-08-24", 99.0, 0.0),
        ("2026-09-12", 17.82, 0.0)])
    # the same file again adds nothing
    r = a.post(f"/api/statements/accounts/{cid}/upload?period=2026-09",
               files={"file": ("RBL_Card.pdf", RBL.read_bytes(), "application/pdf")})
    assert r.json()["saved"] == 0


# ------------------------------------------------------------ parsing details
def test_value_date_is_dropped_from_the_narration_without_changing_the_fingerprint():
    from app.routers.statements import parse_text, fingerprint
    t = parse_text("01-04-2026 01/04/2026 BY TRANSFER- TRANSFER FROM 4430 "
                   "40,889.10 1,40,889.10", "BANK")[0]
    assert t["descr"] == "BY TRANSFER- TRANSFER FROM 4430"
    old = dict(t, descr=t["raw"]); old.pop("raw")        # how v4.2 keyed the same row
    assert fingerprint(t) == fingerprint(old)


def test_identical_rows_in_one_file_are_both_saved(org):
    a = org()
    csv = (b"Date,Narration,Withdrawal,Deposit,Balance\n"
           b"02/08/2026,UPI TEA STALL,20.00,,980.00\n"
           b"02/08/2026,UPI TEA STALL,20.00,,960.00\n")
    aid, _ = bank(a, csv)
    assert len(a.get(f"/api/statements/accounts/{aid}/txns?period=2026-08").json()) == 2
