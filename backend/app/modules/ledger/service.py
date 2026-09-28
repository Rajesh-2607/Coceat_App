"""Party (money) ledger and crate ledger. Append-only: entries are inserted, never changed.

Party existence is enforced by the composite foreign key (business_id, party_id), so an entry can never
point at another business's party. Callers (parties, later sales/payments) validate the party first.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.context import Ctx
from app.core.errors import Conflict, NotFound, Unprocessable
from app.modules.accounts.permissions import Perm
from app.modules.accounts.service import require_module, require_permission
from app.modules.audit import service as audit
from app.modules.inventory import service as inventory
from app.modules.ledger.models import CrateLedgerEntry, PartyLedgerEntry, Payment
from app.modules.ledger.schemas import (
    CrateAdjustmentIn,
    CrateBalanceOut,
    CrateEntryIn,
    CrateLedgerEntryOut,
    MethodTotal,
    PartyAdjustmentIn,
    PartyLedgerEntryOut,
    PaymentIn,
    PaymentOut,
)
from app.modules.platform.modules import ModuleKey

# --- party ledger ----------------------------------------------------------------------------------------


async def post_party_entry(
    ctx: Ctx,
    party_id: uuid.UUID,
    entry_type: str,
    amount_paise: int,
    *,
    note: str | None = None,
    reference_type: str | None = None,
    reference_id: str | None = None,
) -> PartyLedgerEntry:
    """Add one entry in the caller's transaction (no permission check: the calling service did that)."""
    entry = PartyLedgerEntry(
        party_id=party_id,
        entry_type=entry_type,
        amount_paise=amount_paise,
        note=note,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=ctx.actor.user_id,
    )
    ctx.db.add(entry)
    try:
        async with ctx.db.begin_nested():
            await ctx.db.flush()
    except IntegrityError as exc:
        raise NotFound("Party not found") from exc
    await ctx.db.refresh(entry)
    await audit.record(
        ctx,
        f"party_ledger.{entry_type}",
        entity_type="party_ledger_entry",
        entity_id=entry.id,
        after=PartyLedgerEntryOut.model_validate(entry),
    )
    return entry


async def party_balances(ctx: Ctx, party_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Net balance per party in paise: > 0 the party owes us, < 0 we owe the party."""
    if not party_ids:
        return {}
    rows = await ctx.db.execute(
        select(PartyLedgerEntry.party_id, func.sum(PartyLedgerEntry.amount_paise))
        .where(PartyLedgerEntry.party_id.in_(party_ids))
        .group_by(PartyLedgerEntry.party_id)
    )
    found = {pid: int(total) for pid, total in rows}
    return {pid: found.get(pid, 0) for pid in party_ids}


async def list_party_entries(
    ctx: Ctx, party_id: uuid.UUID, *, before_id: uuid.UUID | None, limit: int
) -> list[PartyLedgerEntryOut]:
    stmt = (
        select(PartyLedgerEntry)
        .where(PartyLedgerEntry.party_id == party_id)
        .order_by(PartyLedgerEntry.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(PartyLedgerEntry.id < before_id)
    return [PartyLedgerEntryOut.model_validate(r) for r in await ctx.db.scalars(stmt)]


async def adjust_party(ctx: Ctx, party_id: uuid.UUID, data: PartyAdjustmentIn) -> PartyLedgerEntryOut:
    entry = await post_party_entry(ctx, party_id, "adjustment", data.amount_paise, note=data.note)
    return PartyLedgerEntryOut.model_validate(entry)


# --- crate ledger ----------------------------------------------------------------------------------------


def _crates_view(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.CRATES_VIEW)


def _crates_manage(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.CRATES_MANAGE)


async def _post_crate_entry(
    ctx: Ctx,
    party_id: uuid.UUID,
    entry_type: str,
    quantity: int,
    *,
    location_id: uuid.UUID | None,
    note: str | None,
) -> CrateLedgerEntryOut:
    if location_id is not None:
        await inventory.require_location(ctx, location_id)
    entry = CrateLedgerEntry(
        party_id=party_id,
        location_id=location_id,
        entry_type=entry_type,
        quantity=quantity,
        note=note,
        created_by=ctx.actor.user_id,
    )
    ctx.db.add(entry)
    try:
        async with ctx.db.begin_nested():
            await ctx.db.flush()
    except IntegrityError as exc:  # unknown party or location (composite FK / tenant-checked FK)
        raise NotFound("Party or location not found") from exc
    await ctx.db.refresh(entry)
    out = CrateLedgerEntryOut.model_validate(entry)
    await audit.record(
        ctx, f"crate_ledger.{entry_type}", entity_type="crate_ledger_entry", entity_id=entry.id, after=out
    )
    return out


async def record_crates(ctx: Ctx, data: CrateEntryIn) -> CrateLedgerEntryOut:
    _crates_manage(ctx)
    signed = data.quantity if data.direction == "issued" else -data.quantity
    return await _post_crate_entry(
        ctx, data.party_id, data.direction, signed, location_id=data.location_id, note=data.note
    )


async def adjust_crates(ctx: Ctx, party_id: uuid.UUID, data: CrateAdjustmentIn) -> CrateLedgerEntryOut:
    _crates_manage(ctx)
    if data.quantity == 0:
        raise Unprocessable("Adjustment cannot be zero", code="zero_adjustment")
    return await _post_crate_entry(ctx, party_id, "adjustment", data.quantity, location_id=None, note=data.note)


async def crate_balances(ctx: Ctx, *, only_outstanding: bool = True) -> list[CrateBalanceOut]:
    _crates_view(ctx)
    total = func.sum(CrateLedgerEntry.quantity)
    stmt = select(CrateLedgerEntry.party_id, total).group_by(CrateLedgerEntry.party_id)
    if only_outstanding:
        stmt = stmt.having(total != 0)
    rows = await ctx.db.execute(stmt.order_by(total.desc()))
    return [CrateBalanceOut(party_id=pid, crates_held=int(q)) for pid, q in rows]


async def crates_held(ctx: Ctx, party_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not party_ids:
        return {}
    rows = await ctx.db.execute(
        select(CrateLedgerEntry.party_id, func.sum(CrateLedgerEntry.quantity))
        .where(CrateLedgerEntry.party_id.in_(party_ids))
        .group_by(CrateLedgerEntry.party_id)
    )
    found = {pid: int(q) for pid, q in rows}
    return {pid: found.get(pid, 0) for pid in party_ids}


async def list_crate_entries(
    ctx: Ctx, party_id: uuid.UUID, *, before_id: uuid.UUID | None, limit: int
) -> list[CrateLedgerEntryOut]:
    _crates_view(ctx)
    stmt = (
        select(CrateLedgerEntry)
        .where(CrateLedgerEntry.party_id == party_id)
        .order_by(CrateLedgerEntry.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(CrateLedgerEntry.id < before_id)
    return [CrateLedgerEntryOut.model_validate(r) for r in await ctx.db.scalars(stmt)]


# --- payments and document reversal -----------------------------------------------------------------------


async def record_payment(
    ctx: Ctx,
    *,
    party_id: uuid.UUID | None,
    direction: str,
    method: str,
    amount_paise: int,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
    post_to_ledger: bool = True,
    reversal_of: uuid.UUID | None = None,
) -> Payment:
    """Add a payment (and, for a party, its ledger entry) in the caller's transaction.

    Money received from a party lowers what they owe (negative ledger amount); money paid to them raises it.
    """
    payment = Payment(
        party_id=party_id,
        direction=direction,
        method=method,
        amount_paise=amount_paise,
        reference_type=reference_type,
        reference_id=reference_id,
        reversal_of=reversal_of,
        note=note,
        created_by=ctx.actor.user_id,
    )
    ctx.db.add(payment)
    try:
        async with ctx.db.begin_nested():
            await ctx.db.flush()
    except IntegrityError as exc:
        raise NotFound("Party not found") from exc
    await ctx.db.refresh(payment)
    if party_id is not None and post_to_ledger:
        await post_party_entry(
            ctx,
            party_id,
            "payment_in" if direction == "in" else "payment_out",
            -amount_paise if direction == "in" else amount_paise,
            note=note,
            reference_type=reference_type or "payment",
            reference_id=reference_id or str(payment.id),
        )
    await audit.record(
        ctx,
        f"payment.{direction}",
        entity_type="payment",
        entity_id=payment.id,
        after=PaymentOut.model_validate(payment),
    )
    return payment


def _money_view(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.MONEY)
    require_permission(ctx, Perm.MONEY_VIEW)


def _money_record(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.MONEY)
    require_permission(ctx, Perm.MONEY_RECORD)


async def create_payment(ctx: Ctx, data: PaymentIn) -> PaymentOut:
    _money_record(ctx)
    payment = await record_payment(
        ctx,
        party_id=data.party_id,
        direction=data.direction,
        method=data.method,
        amount_paise=data.amount_paise,
        note=data.note,
    )
    return PaymentOut.model_validate(payment)


async def list_payments(
    ctx: Ctx, *, party_id: uuid.UUID | None, before_id: uuid.UUID | None, limit: int
) -> list[PaymentOut]:
    _money_view(ctx)
    stmt = select(Payment).order_by(Payment.id.desc()).limit(limit)
    if party_id is not None:
        stmt = stmt.where(Payment.party_id == party_id)
    if before_id is not None:
        stmt = stmt.where(Payment.id < before_id)
    return [PaymentOut.model_validate(p) for p in await ctx.db.scalars(stmt)]


async def reverse_payment(ctx: Ctx, payment_id: uuid.UUID, reason: str) -> PaymentOut:
    """Undo a stand-alone payment with an equal and opposite one. Bill payments are undone by voiding the bill."""
    _money_record(ctx)
    original = await ctx.db.scalar(select(Payment).where(Payment.id == payment_id))
    if original is None:
        raise NotFound("Payment not found")
    if original.reference_type in ("bill", "purchase", "sale_return"):
        raise Unprocessable("Void or correct the bill instead", code="payment_belongs_to_document")
    if original.reversal_of is not None:
        raise Unprocessable("A reversal cannot be reversed", code="not_reversible")
    if await ctx.db.scalar(select(Payment.id).where(Payment.reversal_of == original.id)) is not None:
        raise Conflict("This payment was already reversed", code="already_reversed")
    entry = await ctx.db.scalar(
        select(PartyLedgerEntry).where(
            PartyLedgerEntry.reference_type == "payment", PartyLedgerEntry.reference_id == str(original.id)
        )
    )
    reversal = await record_payment(
        ctx,
        party_id=original.party_id,
        direction="out" if original.direction == "in" else "in",
        method=original.method,
        amount_paise=original.amount_paise,
        note=reason,
        post_to_ledger=False,
        reversal_of=original.id,
        reference_type="payment",
        reference_id=str(original.id),
    )
    if entry is not None and original.party_id is not None:
        await _reverse_entry(ctx, entry, reason)
    return PaymentOut.model_validate(reversal)


async def _reverse_entry(ctx: Ctx, entry: PartyLedgerEntry, note: str | None) -> None:
    reversal = PartyLedgerEntry(
        party_id=entry.party_id,
        entry_type="reversal",
        amount_paise=-entry.amount_paise,
        reference_type=entry.reference_type,
        reference_id=entry.reference_id,
        reversal_of=entry.id,
        note=note,
        created_by=ctx.actor.user_id,
    )
    ctx.db.add(reversal)
    await ctx.db.flush()


async def reverse_document(ctx: Ctx, reference_type: str, reference_id: str, note: str) -> None:
    """Undo everything a bill or purchase posted: its party-ledger entries and its payments.

    Each is answered by an opposite entry that points back at the original (never edited or deleted).
    Payments are reversed without extra ledger entries because the ledger entries themselves are reversed.
    """
    reversed_entries = select(PartyLedgerEntry.reversal_of).where(PartyLedgerEntry.reversal_of.is_not(None))
    entries = await ctx.db.scalars(
        select(PartyLedgerEntry).where(
            PartyLedgerEntry.reference_type == reference_type,
            PartyLedgerEntry.reference_id == reference_id,
            PartyLedgerEntry.reversal_of.is_(None),
            PartyLedgerEntry.id.not_in(reversed_entries),
        )
    )
    for entry in list(entries):
        await _reverse_entry(ctx, entry, note)
    reversed_payments = select(Payment.reversal_of).where(Payment.reversal_of.is_not(None))
    payments = await ctx.db.scalars(
        select(Payment).where(
            Payment.reference_type == reference_type,
            Payment.reference_id == reference_id,
            Payment.reversal_of.is_(None),
            Payment.id.not_in(reversed_payments),
        )
    )
    for payment in list(payments):
        await record_payment(
            ctx,
            party_id=payment.party_id,
            direction="out" if payment.direction == "in" else "in",
            method=payment.method,
            amount_paise=payment.amount_paise,
            reference_type=reference_type,
            reference_id=reference_id,
            note=note,
            post_to_ledger=False,
            reversal_of=payment.id,
        )


async def payment_totals(ctx: Ctx, start: datetime, end: datetime) -> list[MethodTotal]:
    """Money received and paid per method in [start, end). Reversals count against the original direction."""
    _money_view(ctx)
    rows = await ctx.db.execute(
        select(Payment.method, Payment.direction, func.sum(Payment.amount_paise))
        .where(Payment.created_at >= start, Payment.created_at < end)
        .group_by(Payment.method, Payment.direction)
    )
    received: dict[str, int] = {}
    paid: dict[str, int] = {}
    for method, direction, total in rows:
        (received if direction == "in" else paid)[method] = int(total)
    methods = sorted(set(received) | set(paid))
    return [MethodTotal(method=m, received_paise=received.get(m, 0), paid_paise=paid.get(m, 0)) for m in methods]
