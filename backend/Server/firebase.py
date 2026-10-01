import os
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPOSITORY_ROOT / ".env")


def get_firebase_admin_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    credential_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
    if not credential_path:
        raise RuntimeError("Set FIREBASE_SERVICE_ACCOUNT_PATH in the repository .env.")

    credential_file = Path(credential_path)
    if not credential_file.is_absolute():
        credential_file = REPOSITORY_ROOT / credential_file
    if not credential_file.is_file():
        raise FileNotFoundError(f"Firebase service-account file not found: {credential_file}")

    return firebase_admin.initialize_app(
        credentials.Certificate(str(credential_file))
    )


def get_firestore_client():
    return firestore.client(app=get_firebase_admin_app())