"""
Credential encryption/decryption and provider credential access.
"""
import json
import base64
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ProviderCredential

def get_encryption_key() -> bytes:
    """Get or generate encryption key"""
    key_str = settings.ENCRYPTION_KEY
    # Ensure key is 32 bytes for Fernet
    key_bytes = key_str.encode()[:32].ljust(32, b'0')
    return base64.urlsafe_b64encode(key_bytes)

def encrypt_token(token: str) -> str:
    """Encrypt a token"""
    key = get_encryption_key()
    f = Fernet(key)
    encrypted = f.encrypt(token.encode())
    return encrypted.decode()

def decrypt_token(encrypted: str) -> str:
    """Decrypt a token"""
    key = get_encryption_key()
    f = Fernet(key)
    decrypted = f.decrypt(encrypted.encode())
    return decrypted.decode()


def get_provider_credentials(db: Session, user_id: str, provider_id: str) -> dict[str, Any] | None:
    """Return decrypted provider credentials dict for the given user and provider, or None."""
    cred = (
        db.query(ProviderCredential)
        .filter(
            ProviderCredential.user_id == user_id,
            ProviderCredential.provider_id == provider_id,
        )
        .first()
    )
    if not cred or not cred.value_encrypted:
        return None
    try:
        dec = decrypt_token(cred.value_encrypted)
        if isinstance(dec, str) and dec.strip().startswith("{"):
            return json.loads(dec)
        return {"apiKey": dec}
    except Exception:
        return None
