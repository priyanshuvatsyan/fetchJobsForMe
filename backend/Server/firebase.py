import os
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPOSITORY_ROOT / ".env")


def _service_account_file() -> Path | None:
    credential_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
    if not credential_path:
        return None
    credential_file = Path(credential_path)
    if not credential_file.is_absolute():
        credential_file = REPOSITORY_ROOT / credential_file
    return credential_file


def get_firebase_admin_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    credential_file = _service_account_file()
    if credential_file is None:
        raise RuntimeError("Set FIREBASE_SERVICE_ACCOUNT_PATH in the repository .env.")
    if not credential_file.is_file():
        raise FileNotFoundError(f"Firebase service-account file not found: {credential_file}")

    return firebase_admin.initialize_app(
        credentials.Certificate(str(credential_file))
    )


def get_firestore_client():
    return firestore.client(app=get_firebase_admin_app())


# Must run before any other module creates the default app without credentials.
if (_service_account_file() or Path()).is_file():
    get_firebase_admin_app()


def uid_from_authorization(header: str | None) -> str:
    """User id from the Firebase ID token the web app sends."""
    if not header or not str(header).startswith("Bearer "):
        raise ValueError("sign in is required")
    token = str(header).split("Bearer ", 1)[1].strip()
    if not token:
        raise ValueError("sign in is required")
    from firebase_admin import auth as fb_auth

    try:
        decoded = fb_auth.verify_id_token(token, app=get_firebase_admin_app())
    except Exception as exc:
        raise ValueError(f"sign in is required ({exc})") from exc
    uid = str((decoded or {}).get("uid") or "").strip()
    if not uid:
        raise ValueError("sign in is required")
    return uid