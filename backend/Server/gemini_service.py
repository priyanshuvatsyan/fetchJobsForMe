"""Firebase Auth & Firestore Gemini client resolver."""

from __future__ import annotations

import json
import os
import firebase_admin
from firebase_admin import auth as fb_auth, credentials, firestore
from google import genai

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    service_account_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if service_account_env:
        cred = credentials.Certificate(json.loads(service_account_env))
        firebase_admin.initialize_app(cred)
    else:
        # Default credentials for local development or GCP environment
        try:
            firebase_admin.initialize_app()
        except Exception:
            pass


def get_user_gemini_client(auth_header: str | None) -> tuple[genai.Client, str]:
    """Verify Firebase ID token, fetch geminiApiKey from Firestore, and return (client, uid)."""
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("Missing or invalid Authorization header. Please sign in.")

    token = auth_header.split("Bearer ", 1)[1].strip()

    # 1. Verify token
    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception as exc:
        raise ValueError(f"Invalid or expired session token: {exc}") from exc

    uid = decoded.get("uid")
    if not uid:
        raise ValueError("Token missing user ID.")

    # 2. Fetch API key from Firestore: users/{uid}/settings/preferences
    db = firestore.client()
    doc_ref = db.collection("users").document(uid).collection("settings").document("preferences")
    doc_snap = doc_ref.get()

    if not doc_snap.exists:
        raise ValueError("User preferences not found in database.")

    data = doc_snap.to_dict() or {}
    api_key = data.get("geminiApiKey") or data.get("apiKey")

    if not api_key:
        raise ValueError("No Gemini API key found for this user. Please save one in Settings.")

    # 3. Initialize Google GenAI client
    client = genai.Client(api_key=api_key)
    return client, uid