"""One-time helper: obtain a long-lived Dropbox *refresh token*.

Run this once, locally. It reads DROPBOX_APP_KEY / DROPBOX_APP_SECRET from your
.env, walks you through the OAuth "offline" flow, and prints a refresh token to
paste into .env as DROPBOX_REFRESH_TOKEN.

    python scripts/dropbox_get_refresh_token.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlencode

import httpx

ROOT = Path(__file__).resolve().parent.parent

# Load .env the same way the backend does (repo root, then web/backend override).
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "web" / "backend" / ".env", override=True)
except ImportError:
    pass

APP_KEY = os.environ.get("DROPBOX_APP_KEY", "").strip()
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET", "").strip()

# Request these scopes explicitly so the resulting token is guaranteed to carry
# them, rather than relying on the app's default-enabled set. The app must have
# each of these enabled on its Permissions tab, or Dropbox rejects the consent.
SCOPES = [
    "files.content.write",
    "files.content.read",
    "files.metadata.read",
    "sharing.write",
    "sharing.read",
]


def main() -> int:
    if not APP_KEY or not APP_SECRET:
        print("ERROR: set DROPBOX_APP_KEY and DROPBOX_APP_SECRET in .env first.")
        return 1

    authorize_url = "https://www.dropbox.com/oauth2/authorize?" + urlencode({
        "client_id": APP_KEY,
        "response_type": "code",
        "token_access_type": "offline",  # <- this is what yields a refresh token
        "scope": " ".join(SCOPES),        # <- explicit scopes on the token
    })

    print("\n1) Open this URL in your browser and click 'Allow':\n")
    print("   " + authorize_url + "\n")
    print("2) Copy the authorization code Dropbox shows you.\n")
    code = input("Paste the authorization code here: ").strip()
    if not code:
        print("No code entered; aborting.")
        return 1

    resp = httpx.post(
        "https://api.dropbox.com/oauth2/token",
        data={"code": code, "grant_type": "authorization_code"},
        auth=(APP_KEY, APP_SECRET),
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"\nToken exchange failed ({resp.status_code}): {resp.text}")
        return 1

    data = resp.json()
    refresh = data.get("refresh_token")
    if not refresh:
        print("\nNo refresh_token in response (did you use token_access_type=offline?):")
        print(data)
        return 1

    print("\n" + "=" * 60)
    print("SUCCESS. Add this line to your .env (web/backend/.env):\n")
    print(f"DROPBOX_REFRESH_TOKEN={refresh}")
    print("=" * 60 + "\n")
    print("Also set the same three DROPBOX_* vars in your Vercel project's")
    print("Environment Variables so the deployed backend can authenticate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
