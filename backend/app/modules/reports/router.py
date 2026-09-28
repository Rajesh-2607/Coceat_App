from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import WorkspaceCtx
from app.modules.reports import service
from app.modules.reports.schemas import (
    DayBookOut,
    GstReportOut,
    HomeOut,
    OutstandingOut,
    SalesReportOut,
    WastageReportOut,
)
from app.modules.sales.service import today_ist

router = APIRouter(prefix="/w", tags=["reports"])


@router.get("/home", response_model=HomeOut)
async def home(ctx: WorkspaceCtx) -> HomeOut:
    return await service.home(ctx)


Since = Annotated[date, Query(alias="from")]
Until = Annotated[date, Query(alias="to")]


@router.get("/reports/daybook", response_model=DayBookOut)
async def day_book(ctx: WorkspaceCtx, day: Annotated[date | None, Query(alias="date")] = None) -> DayBookOut:
    return await service.day_book(ctx, day or today_ist())


@router.get("/reports/sales", response_model=SalesReportOut)
async def sales_report(ctx: WorkspaceCtx, date_from: Since, date_to: Until) -> SalesReportOut:
    return await service.sales_report(ctx, date_from, date_to)


@router.get("/reports/gst", response_model=GstReportOut)
async def gst_report(ctx: WorkspaceCtx, date_from: Since, date_to: Until) -> GstReportOut:
    return await service.gst_report(ctx, date_from, date_to)


@router.get("/reports/outstanding", response_model=OutstandingOut)
async def outstanding_report(ctx: WorkspaceCtx) -> OutstandingOut:
    return await service.outstanding_report(ctx)


@router.get("/reports/wastage", response_model=WastageReportOut)
async def wastage_report(ctx: WorkspaceCtx, date_from: Since, date_to: Until) -> WastageReportOut:
    return await service.wastage_report(ctx, date_from, date_to)
