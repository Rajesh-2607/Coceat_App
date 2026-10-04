"""Set a username and password for a person, or create the first platform admin.

Login is username and password only, so every account needs one before it can sign in. Platform admins
add staff with passwords through the app; this script covers the people who have no login yet (the first
platform admin, or an account created before passwords existed).

The password is typed at a hidden prompt, never passed as an argument, so it stays out of shell history.
Run it with the same DATABASE_URL your environment uses. The change is recorded as an audit event.

    python scripts/set_login.py --phone 9999900001 --username admin --create-platform-admin --name "Platform admin"
    python scripts/set_login.py --phone 9000000011 --username kumaravel
"""

import argparse
import asyncio
import getpass
import re
import sys

from sqlalchemy import select

from app import models  # noqa: F401  (every table must be registered before the audit foreign keys resolve)
from app.core.context import RequestMeta
from app.core.db import get_sessionmaker
from app.core.security import hash_password, normalize_indian_mobile
from app.modules.accounts.models import User
from app.modules.accounts.schemas import PASSWORD_MIN_LENGTH, USERNAME_PATTERN
from app.modules.audit import service as audit


async def run(args: argparse.Namespace) -> int:
    phone = normalize_indian_mobile(args.phone)
    if phone is None:
        print("Enter a valid 10-digit mobile number.")
        return 2
    username = args.username.strip().lower()
    if not re.fullmatch(USERNAME_PATTERN, username):
        print("Usernames are 3-40 characters: a-z, 0-9, dot, underscore or dash.")
        return 2
    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat password: "):
        print("The passwords do not match.")
        return 2
    if len(password) < PASSWORD_MIN_LENGTH:
        print(f"The password must be at least {PASSWORD_MIN_LENGTH} characters.")
        return 2

    async with get_sessionmaker()() as db:
        taken = await db.scalar(select(User.id).where(User.username == username))
        user = await db.scalar(select(User).where(User.phone == phone))
        if taken is not None and (user is None or taken != user.id):
            print("That username is already taken.")
            return 1
        if user is None:
            if not args.create_platform_admin:
                print("No person has that number. Pass --create-platform-admin to create the first platform admin.")
                return 1
            user = User(phone=phone, name=args.name, language="en", is_platform_admin=True, is_active=True)
            db.add(user)
            await db.flush()
        user.username = username
        user.password_hash = hash_password(password)
        user.failed_logins = 0
        user.locked_until = None
        await audit.record_event(
            db,
            meta=RequestMeta(ip=None, user_agent="scripts/set_login.py", request_id=None),
            action="auth.set_login",
            actor_user_id=None,
            business_id=None,
            entity_type="user",
            entity_id=user.id,
            after={"username": username},
        )
        await db.commit()
    print(f"Login set for '{username}'.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phone", required=True, help="the person's mobile number (identifies the account)")
    parser.add_argument("--username", required=True)
    parser.add_argument("--create-platform-admin", action="store_true", help="create the account if it does not exist")
    parser.add_argument("--name", default="Platform admin", help="display name when creating an account")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
