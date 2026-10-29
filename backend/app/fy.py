
"""Financial year helpers.

The organisation sets the day its financial year starts (Company profile:
`fy_start_month`, `fy_start_day`; India's default is 1 April). A year is
labelled by the calendar years it spans — "2026-27" — or, when it starts on
1 January, by the single year — "2026".

A report `period` may be a month "YYYY-MM", a financial year label
"2026-27" / "FY2026-27", or blank for everything.

Reports may also use a financial_year and a quick date_range filter.
Supported date ranges: today, yesterday, this_week, this_month,
this_quarter, this_year. The quick date range is intersected with the
selected financial year. "this_year" means financial year to date.
"""

import re
from datetime import date, timedelta


FY_RE = re.compile(r"^(?:FY)?(\d{4})(?:-(\d{2}|\d{4}))?$", re.I)


def fy_start(tenant, year: int) -> date:
    """Return the start date of the financial year beginning in `year`."""
    month = tenant.fy_start_month or 4
    day = tenant.fy_start_day or 1
    return date(year, month, min(day, 28) if month == 2 else day)


def fy_label(tenant, d: date) -> str:
    """Return the financial-year label containing the given date."""
    year = d.year if d >= fy_start(tenant, d.year) else d.year - 1

    if (
        (tenant.fy_start_month or 4) == 1
        and (tenant.fy_start_day or 1) == 1
    ):
        return str(year)

    return f"{year}-{str(year + 1)[-2:]}"


def fy_bounds(tenant, label: str) -> tuple[date, date]:
    """Return inclusive start and end dates for a financial-year label."""
    match = FY_RE.match(label.strip())
    if not match:
        raise ValueError(
            f"{label!r} is not a financial year like 2026-27"
        )

    year = int(match.group(1))
    start = fy_start(tenant, year)
    end = fy_start(tenant, year + 1) - timedelta(days=1)

    return start, end


def current_fy(tenant, today: date | None = None) -> str:
    """Return the label for the current financial year."""
    return fy_label(tenant, today or date.today())



def in_period(
    tenant,
    d,
    period: str | None = None,
    *,
    financial_year: str | None = None,
    date_range: str | None = None,
    today: date | None = None,
) -> bool:
    """Filter by legacy period, financial year, and quick date range."""
    if d is None:
        return False

    doc_date = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
    today = today or date.today()

    # Keep existing monthly and financial-year callers working.
    if period:
        if is_month(period):
            return str(doc_date)[:7] == period
        start, end = fy_bounds(tenant, period)
        return start <= doc_date <= end

    start, end = date.min, date.max

    if financial_year:
        start, end = fy_bounds(tenant, financial_year)

    if date_range:
        if date_range == "today":
            range_start = range_end = today
        elif date_range == "yesterday":
            range_start = range_end = today - timedelta(days=1)
        elif date_range == "this_week":
            range_start = today - timedelta(days=today.weekday())
            range_end = today
        elif date_range == "this_month":
            range_start = today.replace(day=1)
            range_end = today
        elif date_range in ("this_quarter", "this_year"):
            fy_year = (
                today.year
                if today >= fy_start(tenant, today.year)
                else today.year - 1
            )
            fy_begin = fy_start(tenant, fy_year)

            if date_range == "this_year":
                range_start = fy_begin
            else:
                months_elapsed = (
                    (today.year - fy_begin.year) * 12
                    + today.month - fy_begin.month
                )
                month_index = fy_begin.month - 1 + (months_elapsed // 3) * 3
                year = fy_begin.year + month_index // 12
                month = month_index % 12 + 1
                range_start = date(year, month, 1)

            range_end = today
        else:
            raise ValueError(f"Unsupported date range: {date_range}")

        start = max(start, range_start)
        end = min(end, range_end)

    return start <= doc_date <= end



def is_month(period: str) -> bool:
    """Return whether a period string represents a calendar month.

    For example, 2026-04 is a month. Labels such as 2026-27 are treated
    as financial years rather than months.
    """
    match = re.fullmatch(r"(\d{4})-(\d{2})", period)
    if not match:
        return False

    year, month = int(match.group(1)), int(match.group(2))
    return 1 <= month <= 12 and month != (year + 1) % 100


def fy_labels_for(tenant, dates) -> list[str]:
    """Return available financial-year labels, including the current FY."""
    labels = {fy_label(tenant, d) for d in dates if d}
    labels.add(current_fy(tenant))
    return sorted(labels, reverse=True)
