"""Optional Google Drive upload for GitHub Actions.

Required environment variables:
  GDRIVE_SERVICE_ACCOUNT_JSON  full service-account JSON string
  GDRIVE_FOLDER_ID             destination folder ID shared with that service account
"""
import io
import json
import os
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def upload_or_replace(service, folder_id: str, local_path: Path):
    q = f"name='{local_path.name}' and '{folder_id}' in parents and trashed=false"
    found = service.files().list(q=q, fields="files(id,name)").execute().get("files", [])
    media = MediaFileUpload(str(local_path), resumable=False)
    if found:
        return service.files().update(fileId=found[0]["id"], media_body=media, fields="id,name,modifiedTime").execute()
    meta = {"name": local_path.name, "parents": [folder_id]}
    return service.files().create(body=meta, media_body=media, fields="id,name,modifiedTime").execute()


if __name__ == "__main__":
    raw = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")
    folder = os.environ.get("GDRIVE_FOLDER_ID")
    if not raw or not folder:
        raise SystemExit("Drive secrets not configured; skipping upload is safer than guessing.")
    creds = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    files = [
        Path("output/market_snapshot.csv"),
        Path("output/market_snapshot.json"),
        Path("output/theme_breadth.csv"),
        Path("output/leader_registry.csv"),
        Path("output/feature_history.csv"),
        Path("config/universe.csv"),
    ]
    for p in files:
        if p.exists():
            print(upload_or_replace(svc, folder, p))
