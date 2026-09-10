"""Financial year helpers.

The organisation sets the day its financial year starts (Company profile:
`fy_start_month`, `fy_start_day`; India's default is 1 April). A year is
labelled by the calendar years it spans — "2026-27" — or, when it starts on
1 January, by the single year — "2026".

A report `period` may be a month "YYYY-MM", a financial year label
"2026-27" / "FY2026-27", or blank for everything.
"""
import re
from datetime import date, timedelta

FY_RE = re.compile(r"^(?:FY)?(\d{4})(?:-(\d{2}|\d{4}))?$", re.I)


def fy_start(tenant, year: int) -> date:
    m, d = tenant.fy_start_month or 4, tenant.fy_start_day or 1
    return date(year, m, min(d, 28) if m == 2 else d)


def fy_label(tenant, d: date) -> str:
    y = d.year if d >= fy_start(tenant, d.year) else d.year - 1
    if (tenant.fy_start_month or 4) == 1 and (tenant.fy_start_day or 1) == 1:
        return str(y)
    return f"{y}-{str(y + 1)[-2:]}"


def fy_bounds(tenant, label: str) -> tuple[date, date]:
    m = FY_RE.match(label.strip())
    if not m:
        raise ValueError(f"{label!r} is not a financial year like 2026-27")
    y = int(m.group(1))
    start = fy_start(tenant, y)
    end = fy_start(tenant, y + 1) - timedelta(days=1)
    return start, end


def current_fy(tenant, today: date | None = None) -> str:
    return fy_label(tenant, today or date.today())


def in_period(tenant, d, period: str | None) -> bool:
    """Month 'YYYY-MM', financial year '2026-27', or None for all."""
    if not period:
        return True
    s = str(d)[:10]
    if is_month(period):
        return s[:7] == period
    a, b = fy_bounds(tenant, period)
    return a <= date.fromisoformat(s) <= b


def is_month(period: str) -> bool:
    """'2026-04' is a month; '2026-27' and 'FY2026-27' are financial years.
    The one ambiguous form (e.g. '2011-12') is read as a year — send 'FY…'
    or a month with the day, to be explicit."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", period)
    if not m:
        return False
    y, mm = int(m.group(1)), int(m.group(2))
    return 1 <= mm <= 12 and mm != (y + 1) % 100


def fy_labels_for(tenant, dates) -> list[str]:
    labels = {fy_label(tenant, d) for d in dates if d}
    labels.add(current_fy(tenant))
    return sorted(labels, reverse=True)
