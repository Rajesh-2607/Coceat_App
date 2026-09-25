import uuid
from datetime import datetime

from sqlalchemy import ARRAY, CheckConstraint, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    """Platform table: one person, identified by phone, may belong to several businesses."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("language IN ('en', 'ta')", name="language"),)

    phone: Mapped[str] = mapped_column(String(16), unique=True)  # E.164
    name: Mapped[str] = mapped_column(String(120))
    name_ta: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(2), default="ta")
    is_platform_admin: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)


class Membership(IdMixin, TimestampMixin, Base):
    """Platform table (looked up across businesses at login); the only source of a user's current business."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "business_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="RESTRICT"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    # None = all locations; otherwise the only locations this member may act on
    location_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(PG_UUID(as_uuid=True)))
    is_active: Mapped[bool] = mapped_column(default=True)


class OtpChallenge(IdMixin, Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (
        Index("ix_otp_challenges_phone_created", "phone", "created_at"),
        Index("ix_otp_challenges_ip_created", "ip_hash", "created_at"),
    )

    phone: Mapped[str] = mapped_column(String(16))
    code_hash: Mapped[str] = mapped_column(String(64))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]


class UserSession(IdMixin, Base):
    """Opaque server-side sessions: revocable instantly, unlike JWTs. Only the token's hash is stored."""

    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    business_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime] = mapped_column(index=True)
    revoked_at: Mapped[datetime | None]
