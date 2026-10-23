import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import get_settings


def _key() -> bytes:
    raw = base64.b64decode(get_settings().secret_key_b64 or "")
    if len(raw) != 32:
        raise RuntimeError("MEDGUARD_SECRET_KEY_B64 must be 32 random bytes, base64-encoded")
    return raw


def encrypt_secret(plaintext: str) -> str:
    nonce = os.urandom(12)
    return base64.b64encode(nonce + AESGCM(_key()).encrypt(nonce, plaintext.encode(), None)).decode()


def decrypt_secret(token: str) -> str:
    blob = base64.b64decode(token)
    return AESGCM(_key()).decrypt(blob[:12], blob[12:], None).decode()
