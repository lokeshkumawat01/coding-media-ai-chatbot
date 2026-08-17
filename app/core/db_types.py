"""
Custom SQLAlchemy column type that transparently encrypts values on
write and decrypts on read. Use EncryptedText instead of Text for any
column holding sensitive free-text data.
"""
from sqlalchemy.types import TypeDecorator, Text

from app.core.encryption import encrypt_value, decrypt_value


class EncryptedText(TypeDecorator):
    """Stores TEXT encrypted at rest; transparent to application code."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return decrypt_value(value)