"""Sales reports — by customer, by material and by employee (who created the
invoice) — over Today, This week/month/quarter/year, the previous
month/quarter/year, or custom start and end dates."""
from datetime import date

from fastapi import APIRouter, Depends, Query

from ..deps import Ctx, need
from ..sales_report import all_ranges, resolve_range, sales_report

router = APIRouter(prefix="/reports/sales", tags=["reports"])


@router.get("/ranges")
def ranges(today: date | None = Query(None, description="The caller's local date; defaults to the server's"),
           ctx: Ctx = Depends(need("reports"))):
    """The preset ranges with the dates each one covers today."""
    return all_ranges(ctx.tenant, today or date.today())


@router.get("")
def sales(group: str = Query(..., description="customer, material or employee"),
          range: str = Query("this_month", description="today, this_week, this_month, this_quarter, "
                             "this_year, prev_month, prev_quarter, prev_year or custom"),
          start: date | None = Query(None, description="Custom range start (YYYY-MM-DD)"),
          end: date | None = Query(None, description="Custom range end (YYYY-MM-DD)"),
          today: date | None = Query(None, description="The caller's local date; defaults to the server's"),
          ctx: Ctx = Depends(need("reports"))):
    r = resolve_range(ctx.tenant, range, today or date.today(), start, end)
    return {"range": r, **sales_report(ctx, group, r["start"], r["end"])}
