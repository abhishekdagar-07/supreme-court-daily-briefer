"""Archives each day's judgments to Google Drive.

Uploads the day's PDFs + Word brief into  <My Drive>/Supreme Court Judgments/
<YYYY-MM Month>/<YYYY-MM-DD>/  — mirroring the local Desktop layout. Auth is an
OAuth refresh token owned by the user (so files count against the user's Drive,
which works on consumer Gmail). Run gdrive_setup.py once to obtain the token.

Uses the least-privilege `drive.file` scope: the app can only see/manage the
folders and files it creates, nothing else in your Drive.
"""
import logging
import config

log = logging.getLogger("gdrive")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def is_configured() -> bool:
    return bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET
                and config.GOOGLE_REFRESH_TOKEN)


def _service():
    # Imported lazily so the rest of the tool runs even if google libs aren't installed.
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=config.GOOGLE_REFRESH_TOKEN,
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _find_or_create_folder(svc, name: str, parent: str | None) -> str:
    safe = name.replace("'", "\\'")
    q = f"name = '{safe}' and mimeType = '{FOLDER_MIME}' and trashed = false"
    if parent:
        q += f" and '{parent}' in parents"
    res = svc.files().list(q=q, spaces="drive", fields="files(id,name)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    meta = {"name": name, "mimeType": FOLDER_MIME}
    if parent:
        meta["parents"] = [parent]
    return svc.files().create(body=meta, fields="id").execute()["id"]


def upload_day(date, file_paths, log=log) -> int:
    """Upload the given files into the dated Drive folder. Skips ones already there.
    Returns the number of files newly uploaded."""
    from googleapiclient.http import MediaFileUpload
    svc = _service()
    root = _find_or_create_folder(svc, config.MAIN_FOLDER_NAME, None)
    month = _find_or_create_folder(
        svc, f"{date.year}-{date.month:02d} {config.MONTH_NAMES[date.month]}", root)
    day = _find_or_create_folder(svc, date.strftime("%Y-%m-%d"), month)

    existing = {f["name"] for f in svc.files().list(
        q=f"'{day}' in parents and trashed = false",
        fields="files(name)").execute().get("files", [])}

    uploaded = 0
    for p in file_paths:
        if p is None or not p.exists() or p.name in existing:
            continue
        media = MediaFileUpload(str(p), resumable=False)
        svc.files().create(body={"name": p.name, "parents": [day]},
                           media_body=media, fields="id").execute()
        uploaded += 1
    log.info("Google Drive: uploaded %d file(s) to %s/%s",
             uploaded, config.MAIN_FOLDER_NAME, date.strftime("%Y-%m-%d"))
    return uploaded
