import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class AuditEvent(Base):
    """Append-only. UPDATE/DELETE are blocked by a trigger and revoked from the app role.

    Not a TenantMixin: login and platform events have no business. RLS lets the app read only its
    business's rows and insert rows for its business or with no business.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_business_seq", "business_id", "seq"),
        # RETURNING would be checked against the SELECT policy, which platform events (no business) fail
        {"implicit_returning": False},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    # server-assigned, strictly increasing: display order and keyset pagination
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    business_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("businesses.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(60))  # e.g. "location.create", "auth.login"
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
