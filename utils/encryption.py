# ============================================================
# DESTINATION: /opt/forex_bot/utils/encryption.py
# AES/Fernet encryption for broker API keys at rest
# ============================================================
import base64
import os
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings


def _get_fernet() -> Fernet:
    """Build Fernet cipher from the configured ENCRYPTION_KEY."""
    raw_key = settings.ENCRYPTION_KEY
    if not raw_key:
        raise ValueError("ENCRYPTION_KEY is not set in settings / .env")

    # If the key is already base64-url Fernet format (44 bytes), use directly.
    try:
        return Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)
    except Exception:
        # Derive a Fernet key from the raw secret using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'forex_bot_static_salt_v1',   # deterministic so decryption works
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(
            kdf.derive(raw_key.encode() if isinstance(raw_key, str) else raw_key)
        )
        return Fernet(key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a base64-encoded token."""
    if not plaintext:
        return ''
    f = _get_fernet()
    return f.encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt_value(token: str) -> str:
    """Decrypt a Fernet token back to plaintext."""
    if not token:
        return ''
    f = _get_fernet()
    try:
        return f.decrypt(token.encode('utf-8')).decode('utf-8')
    except InvalidToken as exc:
        raise ValueError(f"Decryption failed — invalid or tampered token: {exc}") from exc


def generate_fernet_key() -> str:
    """
    Helper to generate a fresh Fernet key.
    Run once on setup:  python -c "from utils.encryption import generate_fernet_key; print(generate_fernet_key())"
    """
    return Fernet.generate_key().decode('utf-8')
