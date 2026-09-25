"""Import every model so Base.metadata is complete (for Alembic and mapper configuration)."""

from app.core.idempotency import IdempotencyRecord
from app.modules.accounts.models import Membership, OtpChallenge, User, UserSession
from app.modules.audit.models import AuditEvent
from app.modules.inventory.models import Location
from app.modules.platform.models import Business, VerticalTemplate

__all__ = [
    "AuditEvent",
    "Business",
    "IdempotencyRecord",
    "Location",
    "Membership",
    "OtpChallenge",
    "User",
    "UserSession",
    "VerticalTemplate",
]
