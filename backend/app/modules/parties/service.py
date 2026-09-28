"""Customers and suppliers (one table, told apart by ``kind``)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select

from app.core.context import Ctx
from app.core.errors import NotFound, Unprocessable
from app.core.security import normalize_indian_mobile
from app.core.service_utils import flush_unique
from app.modules.accounts.permissions import Perm
from app.modules.accounts.service import require_module, require_permission
from app.modules.audit import service as audit
from app.modules.ledger import service as ledger
from app.modules.ledger.schemas import (
    CrateAdjustmentIn,
    CrateLedgerEntryOut,
    PartyAdjustmentIn,
    PartyLedgerEntryOut,
)
from app.modules.parties.models import Party
from app.modules.parties.schemas import (
    PartyBalanceOut,
    PartyCreate,
    PartyKind,
    PartyOut,
    PartySummaryOut,
    PartyUpdate,
)
from app.modules.platform.modules import ModuleKey

_MODULE = {"customer": ModuleKey.CUSTOMERS, "supplier": ModuleKey.SUPPLIERS}
_TAKEN = "A {kind} with this phone number already exists"


def _view(ctx: Ctx, kind: PartyKind) -> None:
    require_module(ctx, _MODULE[kind])
    require_permission(ctx, Perm.PARTIES_VIEW)


def _manage(ctx: Ctx, kind: PartyKind) -> None:
    require_module(ctx, _MODULE[kind])
    require_permission(ctx, Perm.PARTIES_MANAGE)


def _phone(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    phone = normalize_indian_mobile(raw)
    if phone is None:
        raise Unprocessable("Enter a valid 10-digit mobile number", code="invalid_phone")
    return phone


async def _party(ctx: Ctx, kind: PartyKind, party_id: uuid.UUID) -> Party:
    party = await ctx.db.scalar(select(Party).where(Party.id == party_id, Party.kind == kind))
    if party is None:
        raise NotFound("Party not found")
    return party


async def _out(ctx: Ctx, parties: list[Party]) -> list[PartyOut]:
    ids = [p.id for p in parties]
    balances = await ledger.party_balances(ctx, ids)
    crates = await ledger.crates_held(ctx, ids)
    out: list[PartyOut] = []
    for p in parties:
        item = PartyOut.model_validate(p)
        item.balance_paise = balances[p.id]
        item.crates_held = crates[p.id]
        out.append(item)
    return out


async def list_parties(
    ctx: Ctx, kind: PartyKind, *, q: str | None = None, include_inactive: bool = False, limit: int = 200
) -> list[PartyOut]:
    _view(ctx, kind)
    stmt = select(Party).where(Party.kind == kind).order_by(Party.name).limit(limit)
    if not include_inactive:
        stmt = stmt.where(Party.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Party.name.ilike(like), Party.name_ta.ilike(like), Party.phone.ilike(like)))
    return await _out(ctx, list(await ctx.db.scalars(stmt)))


async def get_party(ctx: Ctx, kind: PartyKind, party_id: uuid.UUID) -> PartyOut:
    _view(ctx, kind)
    return (await _out(ctx, [await _party(ctx, kind, party_id)]))[0]


async def create_party(ctx: Ctx, kind: PartyKind, data: PartyCreate) -> PartyOut:
    _manage(ctx, kind)
    fields = data.model_dump(exclude={"opening_balance_paise"})
    fields["phone"] = _phone(data.phone)
    party = Party(kind=kind, **fields)
    ctx.db.add(party)
    await flush_unique(ctx, _TAKEN.format(kind=kind), "party_phone_taken")
    await ctx.db.refresh(party)
    if data.opening_balance_paise != 0:
        await ledger.post_party_entry(
            ctx,
            party.id,
            "opening",
            data.opening_balance_paise,
            note="Opening balance",
            reference_type="party",
            reference_id=str(party.id),
        )
    out = (await _out(ctx, [party]))[0]
    await audit.record(ctx, f"{kind}.create", entity_type=kind, entity_id=party.id, after=out)
    return out


async def update_party(ctx: Ctx, kind: PartyKind, party_id: uuid.UUID, data: PartyUpdate) -> PartyOut:
    _manage(ctx, kind)
    party = await _party(ctx, kind, party_id)
    before = (await _out(ctx, [party]))[0]
    clearable = {"name_ta", "phone", "address", "gstin", "credit_limit_paise", "notes"}
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field not in clearable:
            continue
        setattr(party, field, _phone(value) if field == "phone" else value)
    await flush_unique(ctx, _TAKEN.format(kind=kind), "party_phone_taken")
    await ctx.db.refresh(party)
    out = (await _out(ctx, [party]))[0]
    await audit.record(ctx, f"{kind}.update", entity_type=kind, entity_id=party.id, before=before, after=out)
    return out


# --- ledgers of one party --------------------------------------------------------------------------------


async def party_ledger(
    ctx: Ctx, kind: PartyKind, party_id: uuid.UUID, *, before_id: uuid.UUID | None, limit: int
) -> list[PartyLedgerEntryOut]:
    _view(ctx, kind)
    party = await _party(ctx, kind, party_id)
    return await ledger.list_party_entries(ctx, party.id, before_id=before_id, limit=limit)


async def adjust_balance(
    ctx: Ctx, kind: PartyKind, party_id: uuid.UUID, data: PartyAdjustmentIn
) -> PartyLedgerEntryOut:
    _manage(ctx, kind)
    if data.amount_paise == 0:
        raise Unprocessable("Adjustment cannot be zero", code="zero_adjustment")
    party = await _party(ctx, kind, party_id)
    return await ledger.adjust_party(ctx, party.id, data)


async def party_crates(
    ctx: Ctx, kind: PartyKind, party_id: uuid.UUID, *, before_id: uuid.UUID | None, limit: int
) -> list[CrateLedgerEntryOut]:
    _view(ctx, kind)
    party = await _party(ctx, kind, party_id)
    return await ledger.list_crate_entries(ctx, party.id, before_id=before_id, limit=limit)


async def adjust_party_crates(
    ctx: Ctx, kind: PartyKind, party_id: uuid.UUID, data: CrateAdjustmentIn
) -> CrateLedgerEntryOut:
    _view(ctx, kind)
    party = await _party(ctx, kind, party_id)
    return await ledger.adjust_crates(ctx, party.id, data)


async def party_names(ctx: Ctx, party_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """For display in other modules' views (crate balances, reports). No permission check: read-only labels."""
    if not party_ids:
        return {}
    rows = await ctx.db.execute(select(Party.id, Party.name).where(Party.id.in_(party_ids)))
    return {pid: name for pid, name in rows}


async def summary(ctx: Ctx, kind: PartyKind, *, top: int = 3) -> PartySummaryOut:
    """Totals for the Home page (needs the same access as the party list)."""
    _view(ctx, kind)
    rows = list(
        (
            await ctx.db.execute(select(Party.id, Party.name, Party.name_ta).where(Party.kind == kind, Party.is_active))
        ).all()
    )
    balances = await ledger.party_balances(ctx, [r[0] for r in rows])
    owing = sorted(
        (
            PartyBalanceOut(party_id=pid, name=name, name_ta=name_ta, balance_paise=balances[pid])
            for pid, name, name_ta in rows
            if balances[pid] > 0
        ),
        key=lambda b: -b.balance_paise,
    )
    return PartySummaryOut(
        count=len(rows),
        owed_to_us_paise=sum(b for b in balances.values() if b > 0),
        we_owe_paise=-sum(b for b in balances.values() if b < 0),
        top_owing=owing[:top],
    )


@dataclass(frozen=True, slots=True)
class PartyBillingInfo:
    """What a bill or purchase needs to know about the party (checked and snapshotted by the calling service)."""

    id: uuid.UUID
    name: str
    name_ta: str | None
    phone: str | None
    gstin: str | None
    address: str | None
    credit_limit_paise: int | None
    balance_paise: int  # > 0: they owe us


async def party_for_document(ctx: Ctx, kind: PartyKind, party_id: uuid.UUID) -> PartyBillingInfo:
    """A customer (for a bill) or supplier (for a purchase) that exists in this business and is active.

    No permission check: the sales / purchases service that calls this has already checked its own.
    """
    party = await _party(ctx, kind, party_id)
    if not party.is_active:
        raise Unprocessable("This party is no longer active", code="party_inactive")
    balance = (await ledger.party_balances(ctx, [party.id]))[party.id]
    return PartyBillingInfo(
        party.id, party.name, party.name_ta, party.phone, party.gstin, party.address, party.credit_limit_paise, balance
    )


async def outstanding(ctx: Ctx, kind: PartyKind) -> list[PartyBalanceOut]:
    """Active parties with a non-zero balance, biggest first (customers owe us, we owe suppliers)."""
    _view(ctx, kind)
    rows = list(
        (
            await ctx.db.execute(select(Party.id, Party.name, Party.name_ta).where(Party.kind == kind, Party.is_active))
        ).all()
    )
    balances = await ledger.party_balances(ctx, [r[0] for r in rows])
    out = [
        PartyBalanceOut(party_id=pid, name=name, name_ta=name_ta, balance_paise=balances[pid])
        for pid, name, name_ta in rows
        if balances[pid] != 0
    ]
    return sorted(out, key=lambda b: -abs(b.balance_paise))
