"""Sales reports — by customer, by material and by employee (who created the
invoice) — over Today, This week/month/quarter/year, the previous
day/week/month/quarter, the same day/week/month/quarter last year, last year,
or custom start and end dates; optionally compared with a year earlier."""
from datetime import date

from fastapi import APIRouter, Depends, Query

from ..deps import Ctx, need, need_any
from ..sales_report import (all_ranges, comparison_range, resolve_range, sales_report,
                            with_comparison)

router = APIRouter(prefix="/reports/sales", tags=["reports"])


@router.get("/ranges")
def ranges(today: date | None = Query(None, description="The caller's local date; defaults to the server's"),
           ctx: Ctx = Depends(need_any("reports", "saved", "proforma", "customers"))):
    """The preset ranges with the dates each one covers today. Only dates, so
    any screen that filters by period can use them."""
    return all_ranges(ctx.tenant, today or date.today())


@router.get("")
def sales(group: str = Query(..., description="customer, material or employee"),
          range: str = Query("this_month", description="today, this_week, this_month, this_quarter, "
                             "this_year, yesterday, prev_week, prev_month, prev_quarter, "
                             "ly_today, ly_week, ly_month, ly_quarter, prev_year or custom"),
          start: date | None = Query(None, description="Custom range start (YYYY-MM-DD)"),
          end: date | None = Query(None, description="Custom range end (YYYY-MM-DD)"),
          today: date | None = Query(None, description="The caller's local date; defaults to the server's"),
          compare: bool = Query(False, description="Add the same period a year earlier to every row"),
          ctx: Ctx = Depends(need("reports"))):
    today = today or date.today()
    r = resolve_range(ctx.tenant, range, today, start, end)
    out = sales_report(ctx, group, r["start"], r["end"])
    if compare:
        p = comparison_range(r, today)
        out = with_comparison(out, sales_report(ctx, group, p["start"], p["end"]), p)
    return {"range": r, **out}
