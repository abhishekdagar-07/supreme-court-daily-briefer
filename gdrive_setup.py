"""One-time helper to authorize Google Drive and print a refresh token.

Prerequisites (do these once in the Google Cloud Console, signed in as the Gmail
account whose Drive should hold the archive — adv.abhishekdagar@gmail.com):

  1. https://console.cloud.google.com  ->  create a project (any name).
  2. APIs & Services -> Library -> search "Google Drive API" -> Enable.
  3. APIs & Services -> OAuth consent screen -> User type "External" -> fill the
     app name + your email -> add YOUR email under "Test users".
  4. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID ->
     Application type "Desktop app" -> Create. Copy the Client ID and Client secret.
  5. Put them in .env:
        GOOGLE_CLIENT_ID=....apps.googleusercontent.com
        GOOGLE_CLIENT_SECRET=....
  6. Run:  py gdrive_setup.py
     A browser opens; sign in and click Allow. The script prints a refresh token.
  7. Add the printed line to .env:  GOOGLE_REFRESH_TOKEN=....
     Then tell me, and I'll load all three into GitHub for the cloud job.
"""
import config

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main():
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first "
              "(steps are in the comments at the top of this file).")
        return
    from google_auth_oauthlib.flow import InstalledAppFlow
    client_config = {"installed": {
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }}
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    if not creds.refresh_token:
        print("No refresh token returned. Revoke prior access and retry with prompt=consent.")
        return
    print("\n" + "=" * 60)
    print("SUCCESS — add this line to your .env:\n")
    print("GOOGLE_REFRESH_TOKEN=" + creds.refresh_token)
    print("=" * 60)


if __name__ == "__main__":
    main()
