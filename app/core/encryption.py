"""
Symmetric field-level encryption using Fernet (AES-128-CBC + HMAC).
Used to encrypt sensitive free-text fields at rest (call notes, client
requirement descriptions, profile summaries) that are never queried
via WHERE clauses — fields used for lookups (e.g. phone_number) are
intentionally NOT encrypted here since encryption breaks equality search.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_fernet = Fernet(settings.field_encryption_key.encode())


def encrypt_value(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return "[unreadable — pre-encryption data]"