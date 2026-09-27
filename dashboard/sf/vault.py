"""
Encrypt/decrypt bundles with SF_STATE_KEY (AES-256-GCM, key from PBKDF2-SHA256).

Used for everything that has to leave this server but must stay private: the Google
data GitHub Actions hands back, and the daily backup of config + history on Drive.
"""

import base64
import hashlib
import io
import json
import os
import secrets
import tarfile

MAGIC = b"SFV1"


def _key(passphrase, salt):
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 310_000, 32)


def encrypt_bytes(data, passphrase):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    return MAGIC + salt + iv + AESGCM(_key(passphrase, salt)).encrypt(iv, data, None)


def decrypt_bytes(blob, passphrase):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob.startswith(MAGIC):
        raise ValueError("not an SF vault file")
    salt, iv, ct = blob[4:20], blob[20:32], blob[32:]
    return AESGCM(_key(passphrase, salt)).decrypt(iv, ct, None)


def encrypt_json(obj, passphrase):
    return encrypt_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"), passphrase)


def decrypt_json(blob, passphrase):
    return json.loads(decrypt_bytes(blob, passphrase).decode("utf-8"))


def tar_dirs(paths, root):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in paths:
            if os.path.exists(p):
                tar.add(p, arcname=os.path.relpath(p, root))
    return buf.getvalue()


def untar(blob, root):
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        tar.extractall(root, filter="data")


def b64(b):
    return base64.b64encode(b).decode()
