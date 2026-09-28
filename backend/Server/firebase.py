import json
import os
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPOSITORY_ROOT / ".env")


def get_firebase_admin_app():
	try:
		return firebase_admin.get_app()
	except ValueError:
		pass

	service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
	if not service_account_json:
		raise RuntimeError(
			"Set FIREBASE_SERVICE_ACCOUNT_JSON in the repository .env "
			"to initialize Firebase Admin."
		)

	service_account_info = json.loads(service_account_json)
	return firebase_admin.initialize_app(
		credentials.Certificate(service_account_info)
	)
