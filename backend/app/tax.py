"""GST computation. Single source of truth for every document in the system.

Two rules drive everything:

1. Place of supply against the supplier's own state decides the split.
   Same state  -> CGST + SGST, IGST nil.
   Other state -> IGST, CGST and SGST nil.
   Never all three.

2. Tax is computed per line and rounded to two decimals per line, then
   summed. Rounding the total instead produces a figure that does not
   agree with the line detail printed on the invoice.

Discounts (v4.6). A discount shown on the invoice reduces the taxable
value (CGST Act s.15(3)(a)), so it is taken off *before* tax, line by line:

- a line discount (a percentage, or an amount in rupees) comes off that line;
- an overall discount (percentage or amount) is then spread over the lines in
  proportion to what each is worth after its own discount, so every line still
  carries its own taxable value, rate and tax — which GSTR-1 and the HSN
  summary need. Paise left over by the spread go to the largest line, so the
  shares add up to the overall discount exactly.

Discounts are in the same basis as the price: off the GST-inclusive figure on
an inclusive line, off the pre-tax figure on an exclusive one.
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
    # v4.6 — discount detail, all in rupees
    list_value: Decimal = Decimal("0")     # qty x price, as quoted
    line_disc: Decimal = Decimal("0")      # this line's own discount, as quoted
    overall_disc: Decimal = Decimal("0")   # its share of the overall discount, as quoted
    value: Decimal = Decimal("0")          # qty x price before discount, without GST
    discount: Decimal = Decimal("0")       # value - amount: every discount, without GST
    unit_rate: Decimal = Decimal("0")      # price without GST (= price on exclusive lines)
    disc_type: str | None = None
    disc_value: Decimal = Decimal("0")


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
    # v4.6 — discounts
    gross: Decimal = Decimal("0")             # sum of line values, without GST
    discount: Decimal = Decimal("0")          # gross - taxable
    line_discount: Decimal = Decimal("0")     # line discounts, as quoted
    overall_discount: Decimal = Decimal("0")  # overall discount, as quoted
    disc_type: str | None = None
    disc_value: Decimal = Decimal("0")

    @property
    def tax(self) -> Decimal:
        return self.cgst + self.sgst + self.igst


def disc_amount(base: Decimal, disc_type, disc_value) -> Decimal:
    """Rupees off `base` for a discount spec, never more than `base`."""
    v = Decimal(str(disc_value or 0))
    if not disc_type or v <= 0 or base <= 0:
        return Decimal("0.00")
    amt = q2(base * v / 100) if disc_type == "PCT" else q2(v)
    return min(amt, q2(base))


def spread(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` over `weights` pro rata, to the paisa, adding up exactly."""
    base = sum(weights)
    if total <= 0 or base <= 0:
        return [Decimal("0.00")] * len(weights)
    shares = [q2(total * w / base) for w in weights]
    diff = q2(total - sum(shares))
    if diff:
        big = max(range(len(weights)), key=lambda k: weights[k])
        shares[big] = q2(shares[big] + diff)
    return shares


def compute(lines, org_state: str, pos_state: str, taxable_supply: bool = True,
            discount=None) -> TaxResult:
    """Compute GST per line.

    lines may contain:
      (line_no, material, qty, price)
      (line_no, material, qty, price, descr2)
      (line_no, material, qty, price, descr2, inclusive)
      (line_no, material, qty, price, descr2, inclusive, (disc_type, disc_value))

    discount, when given, is the overall (disc_type, disc_value).
    disc_type is "PCT" or "AMT".

    taxable_supply=False switches tax off entirely.

    When a line is GST-inclusive, the quoted gross amount is preserved and
    GST is carved out of that amount rather than added on top.
    """
    intra = pos_state == org_state
    res = TaxResult(intra=intra)

    # pass 1 — what each line is worth as quoted, and its own discount
    prep = []
    for ln in lines:
        line_no, m, qty, price = ln[0], ln[1], ln[2], ln[3]
        descr2 = ln[4] if len(ln) > 4 else None
        incl = bool(ln[5]) if len(ln) > 5 else bool(
            getattr(m, "price_inclusive", False)
        )
        ld = ln[6] if len(ln) > 6 and ln[6] else (None, 0)
        if not taxable_supply:
            incl = False
        qty = Decimal(str(qty))
        price = Decimal(str(price))
        list_value = q2(qty * price)
        line_disc = disc_amount(list_value, ld[0], ld[1])
        prep.append((line_no, m, qty, price, descr2, incl, ld, list_value, line_disc))

    # pass 2 — spread the overall discount over what is left on each line
    after = [p[7] - p[8] for p in prep]
    od_type, od_value = discount if discount else (None, 0)
    overall = disc_amount(sum(after, Decimal("0")), od_type, od_value)
    shares = spread(overall, after)

    for (line_no, m, qty, price, descr2, incl, ld, list_value, line_disc), share in zip(prep, shares):
        descr = f"{m.descr} {descr2}".strip() if descr2 else m.descr
        net = q2(list_value - line_disc - share)

        cg = Decimal(str(m.cgst_pct))
        sg = Decimal(str(m.sgst_pct))
        ig = Decimal(str(m.igst_pct))

        rate = (cg + sg) if intra else ig

        if not taxable_supply:
            amount = gross = net
            value = list_value
            c = s = i = Decimal("0.00")
            rate = Decimal("0")

        elif incl:
            amount = q2(net * 100 / (100 + rate)) if rate else net
            carved = q2(net - amount)
            value = q2(list_value * 100 / (100 + rate)) if rate else list_value
            gross = net

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
            amount = net
            value = list_value

            if intra:
                c = q2(amount * cg / 100)
                s = q2(amount * sg / 100)
                i = Decimal("0.00")
            else:
                c = s = Decimal("0.00")
                i = q2(amount * ig / 100)

            gross = q2(amount + c + s + i)

        unit_rate = price if not incl or not rate else (
            q2(value / qty) if qty else Decimal("0.00"))

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
                list_value=list_value,
                line_disc=line_disc,
                overall_disc=share,
                value=value,
                discount=q2(value - amount),
                unit_rate=unit_rate,
                disc_type=ld[0] if line_disc else None,
                disc_value=Decimal(str(ld[1] or 0)) if line_disc else Decimal("0"),
            )
        )

        res.taxable += amount
        res.cgst += c
        res.sgst += s
        res.igst += i
        res.gross += value
        res.line_discount += line_disc

    res.taxable = q2(res.taxable)
    res.cgst = q2(res.cgst)
    res.sgst = q2(res.sgst)
    res.igst = q2(res.igst)
    res.gross = q2(res.gross)
    res.discount = q2(res.gross - res.taxable)
    res.line_discount = q2(res.line_discount)
    res.overall_discount = overall
    if overall:
        res.disc_type, res.disc_value = od_type, Decimal(str(od_value))

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
