import asyncio
import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status
from starlette.responses import JSONResponse, Response

from app.core.deps import IdempotencyKey, WorkspaceCtx
from app.core.idempotency import run_idempotent
from app.modules.sales import service
from app.modules.sales.pdf import render_html, render_pdf
from app.modules.sales.schemas import BillOut, BillSummaryOut, ReturnIn, ReturnOut, SaleIn, VoidIn

router = APIRouter(prefix="/w/bills", tags=["sales"])


@router.get("", response_model=list[BillSummaryOut])
async def list_bills(
    ctx: WorkspaceCtx,
    q: Annotated[str | None, Query(max_length=60)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    party_id: Annotated[uuid.UUID | None, Query()] = None,
    bill_status: Annotated[str | None, Query(alias="status", pattern="^(active|void)$")] = None,
    before_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[BillSummaryOut]:
    return await service.list_bills(
        ctx,
        q=q,
        date_from=date_from,
        date_to=date_to,
        party_id=party_id,
        status=bill_status,
        before_id=before_id,
        limit=limit,
    )


@router.post("", response_model=BillOut, status_code=status.HTTP_201_CREATED)
async def create_sale(body: SaleIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(ctx, key, "bill.create", body, lambda: service.create_sale(ctx, body), status_code=201)


@router.get("/{bill_id}", response_model=BillOut)
async def get_bill(bill_id: uuid.UUID, ctx: WorkspaceCtx) -> BillOut:
    return await service.get_bill(ctx, bill_id)


@router.post("/{bill_id}/void", response_model=BillOut)
async def void_bill(bill_id: uuid.UUID, body: VoidIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(ctx, key, f"bill.void:{bill_id}", body, lambda: service.void_bill(ctx, bill_id, body))


@router.get("/{bill_id}/returns", response_model=list[ReturnOut])
async def list_returns(bill_id: uuid.UUID, ctx: WorkspaceCtx) -> list[ReturnOut]:
    return await service.list_returns(ctx, bill_id)


@router.post("/{bill_id}/returns", response_model=ReturnOut, status_code=status.HTTP_201_CREATED)
async def create_return(bill_id: uuid.UUID, body: ReturnIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx,
        key,
        f"bill.return:{bill_id}",
        body,
        lambda: service.create_return(ctx, bill_id, body),
        status_code=201,
    )


@router.get("/{bill_id}/pdf")
async def bill_pdf(
    bill_id: uuid.UUID,
    ctx: WorkspaceCtx,
    paper: Annotated[Literal["a4", "thermal"], Query(alias="format")] = "a4",
    lang: Annotated[Literal["en", "ta"], Query()] = "en",
) -> Response:
    """The bill as a PDF: A4 for the office, 80 mm for the thermal printer. Same permission as viewing the bill."""
    bill = await service.get_bill(ctx, bill_id)
    await ctx.db.rollback()  # read-only: give the connection back before the slow rendering starts
    html = render_html(bill, fmt=paper, lang=lang)
    pdf = await asyncio.to_thread(render_pdf, html)  # CPU-bound: never on the event loop
    filename = bill.bill_number.replace("/", "-")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}.pdf"', "Cache-Control": "private, no-store"},
    )
