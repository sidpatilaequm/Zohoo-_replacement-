"""GST computation. Single source of truth for every document in the system.

Two rules drive everything:

1. Place of supply against the supplier's own state decides the split.
   Same state  -> CGST + SGST, IGST nil.
   Other state -> IGST, CGST and SGST nil.
   Never all three.

2. Tax is computed per line and rounded to two decimals per line, then
   summed. Rounding the total instead produces a figure that does not
   agree with the line detail printed on the invoice.
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

TWO = Decimal("0.01")


def q2(x: Decimal) -> Decimal:
    return Decimal(x).quantize(TWO, rounding=ROUND_HALF_UP)


@dataclass
class TaxLine:
    line_no: int
    material_id: int
    code: str
    descr: str
    descr2: str | None
    hsn: str
    uom: str
    qty: Decimal
    price: Decimal
    amount: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    rate: Decimal
    inclusive: bool = False
    gross: Decimal = Decimal("0")


@dataclass
class TaxResult:
    intra: bool
    taxable: Decimal = Decimal("0")
    cgst: Decimal = Decimal("0")
    sgst: Decimal = Decimal("0")
    igst: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    rounded: Decimal = Decimal("0")
    roundoff: Decimal = Decimal("0")
    lines: list[TaxLine] = field(default_factory=list)

    @property
    def tax(self) -> Decimal:
        return self.cgst + self.sgst + self.igst


def compute(lines, org_state: str, pos_state: str, taxable_supply: bool = True) -> TaxResult:
    """Compute GST per line.

    lines may contain:
      (line_no, material, qty, price)
      (line_no, material, qty, price, descr2)
      (line_no, material, qty, price, descr2, inclusive)

    taxable_supply=False switches tax off entirely.

    When a line is GST-inclusive, the quoted gross amount is preserved and
    GST is carved out of that amount rather than added on top.
    """
    intra = pos_state == org_state
    res = TaxResult(intra=intra)

    for ln in lines:
        line_no, m, qty, price = ln[0], ln[1], ln[2], ln[3]
        descr2 = ln[4] if len(ln) > 4 else None
        incl = bool(ln[5]) if len(ln) > 5 else bool(
            getattr(m, "price_inclusive", False)
        )

        descr = f"{m.descr} {descr2}".strip() if descr2 else m.descr

        qty = Decimal(str(qty))
        price = Decimal(str(price))
        gross = q2(qty * price)

        cg = Decimal(str(m.cgst_pct))
        sg = Decimal(str(m.sgst_pct))
        ig = Decimal(str(m.igst_pct))

        rate = (cg + sg) if intra else ig

        if not taxable_supply:
            amount = gross
            c = s = i = Decimal("0.00")
            rate = Decimal("0")
            incl = False

        elif incl:
            amount = q2(gross * 100 / (100 + rate)) if rate else gross
            carved = q2(gross - amount)

            if intra:
                if (cg + sg):
                    c = q2(carved * cg / (cg + sg))
                    s = q2(carved - c)
                else:
                    c = s = Decimal("0.00")
                i = Decimal("0.00")
            else:
                c = s = Decimal("0.00")
                i = carved

        else:
            amount = gross

            if intra:
                c = q2(amount * cg / 100)
                s = q2(amount * sg / 100)
                i = Decimal("0.00")
            else:
                c = s = Decimal("0.00")
                i = q2(amount * ig / 100)

            gross = q2(amount + c + s + i)

        res.lines.append(
            TaxLine(
                line_no,
                m.id,
                m.code,
                descr,
                descr2,
                m.hsn,
                m.uom,
                qty,
                price,
                amount,
                c,
                s,
                i,
                rate,
                inclusive=incl,
                gross=gross,
            )
        )

        res.taxable += amount
        res.cgst += c
        res.sgst += s
        res.igst += i

    res.taxable = q2(res.taxable)
    res.cgst = q2(res.cgst)
    res.sgst = q2(res.sgst)
    res.igst = q2(res.igst)

    res.total = q2(
        res.taxable + res.cgst + res.sgst + res.igst
    )

    res.rounded = res.total.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP
    )

    res.roundoff = q2(res.rounded - res.total)

    return res


def hsn_summary(res: TaxResult) -> list[dict]:
    """HSN-wise aggregation, required on the invoice and in GSTR-1."""
    agg: dict[tuple, dict] = {}
    for L in res.lines:
        k = (L.hsn, str(L.rate), L.uom)
        a = agg.setdefault(k, {"hsn": L.hsn, "rate": L.rate, "uom": L.uom,
                               "qty": Decimal("0"), "taxable": Decimal("0"),
                               "cgst": Decimal("0"), "sgst": Decimal("0"),
                               "igst": Decimal("0")})
        a["qty"] += L.qty
        a["taxable"] += L.amount
        a["cgst"] += L.cgst
        a["sgst"] += L.sgst
        a["igst"] += L.igst
    for a in agg.values():
        a["total_value"] = q2(a["taxable"] + a["cgst"] + a["sgst"] + a["igst"])
    return list(agg.values())


AMOUNT_WORDS_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
                     "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
                     "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
AMOUNT_WORDS_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty",
                     "Seventy", "Eighty", "Ninety"]


def in_words(n) -> str:
    """Indian numbering: crore, lakh, thousand."""
    n = int(Decimal(str(n)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if n == 0:
        return "Zero"
    def two(x): return AMOUNT_WORDS_ONES[x] if x < 20 else (
        AMOUNT_WORDS_TENS[x // 10] + (" " + AMOUNT_WORDS_ONES[x % 10] if x % 10 else ""))
    def three(x):
        out = ""
        if x >= 100:
            out += AMOUNT_WORDS_ONES[x // 100] + " Hundred"
            if x % 100:
                out += " "
        if x % 100:
            out += two(x % 100)
        return out
    parts, cr, n = [], n // 10_000_000, n % 10_000_000
    lakh, n = n // 100_000, n % 100_000
    th, n = n // 1000, n % 1000
    if cr:
        parts.append(three(cr) + " Crore")
    if lakh:
        parts.append(three(lakh) + " Lakh")
    if th:
        parts.append(three(th) + " Thousand")
    if n:
        parts.append(three(n))
    return " ".join(parts)
