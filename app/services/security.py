"""Transaction-PIN hashing/verification and an audit trail.

PINs are never stored in the clear: we use PBKDF2-HMAC-SHA256 with a random
per-PIN salt (standard-library only, no extra dependencies).
"""
from __future__ import annotations

import hashlib
import hmac
import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog, User

_ITERATIONS = 200_000
_ALGO = "sha256"


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(_ALGO, pin.encode(), salt, _ITERATIONS)
    return f"pbkdf2_{_ALGO}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, dk_hex = stored.split("$")
        expected = bytes.fromhex(dk_hex)
        dk = hashlib.pbkdf2_hmac(
            _ALGO, pin.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)


def is_valid_pin(pin: str) -> bool:
    return pin.isdigit() and 4 <= len(pin) <= 8


class SecurityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_pin(self, user_id: int, pin: str) -> None:
        user = await self._session.get(User, user_id)
        if user is None:
            user = User(id=user_id)
            self._session.add(user)
        user.pin_hash = hash_pin(pin)
        await self.audit(user_id, "set_pin")

    async def check_pin(self, user_id: int, pin: str) -> bool:
        user = await self._session.get(User, user_id)
        if user is None or user.pin_hash is None:
            return False
        ok = verify_pin(pin, user.pin_hash)
        await self.audit(user_id, "pin_check", "ok" if ok else "fail")
        return ok

    async def has_pin(self, user_id: int) -> bool:
        user = await self._session.get(User, user_id)
        return user is not None and user.pin_hash is not None

    async def audit(self, user_id: int, action: str, detail: str = "") -> None:
        self._session.add(
            AuditLog(user_id=user_id, action=action, detail=detail)
        )
