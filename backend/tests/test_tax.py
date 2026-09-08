from decimal import Decimal
from app.tax import compute, hsn_summary, in_words


class Mat:
    def __init__(s, i, code, sg=9, cg=9, ig=18, hsn="998314", uom="LIC"):
        s.id, s.code, s.descr, s.hsn, s.uom = i, code, code, hsn, uom
        s.sgst_pct, s.cgst_pct, s.igst_pct = sg, cg, ig


M1, M2 = Mat(1, "A"), Mat(2, "B", hsn="998313", uom="HRS")
L = [(1, M1, Decimal("10"), Decimal("1250")), (2, M2, Decimal("4"), Decimal("4500"))]


def test_intra_state_splits_cgst_and_sgst():
    r = compute(L, "29", "29")
    assert r.intra and r.cgst == Decimal("2745.00") == r.sgst and r.igst == 0


def test_inter_state_charges_igst_only():
    r = compute(L, "29", "33")
    assert not r.intra and r.igst == Decimal("5490.00") and r.cgst == 0 and r.sgst == 0


def test_total_tax_is_identical_either_way():
    assert compute(L, "29", "29").tax == compute(L, "29", "33").tax


def test_never_all_three_heads():
    for pos in ("29", "33", "27"):
        r = compute(L, "29", pos)
        assert not (r.cgst and r.igst) and not (r.sgst and r.igst)


def test_unregistered_supply_bears_no_tax():
    assert compute(L, "29", "33", taxable_supply=False).tax == 0


def test_rounding_is_per_line_then_summed():
    m = Mat(3, "C")
    r = compute([(i, m, Decimal("1"), Decimal("33.33")) for i in (1, 2, 3)], "29", "29")
    assert r.taxable == Decimal("99.99") and r.cgst == Decimal("9.00")


def test_hsn_summary_reconciles():
    r = compute(L, "29", "33")
    h = hsn_summary(r)
    assert len(h) == 2 and sum(x["taxable"] for x in h) == r.taxable


def test_words_use_the_indian_system():
    assert in_words(35990) == "Thirty Five Thousand Nine Hundred Ninety"
    assert in_words(12345678).startswith("One Crore Twenty Three Lakh")
