"""Minimal Dropbox HTTP API v2 client.

Uses the app key/secret + a long-lived *refresh token* to mint short-lived
access tokens on demand (Dropbox access tokens expire after ~4h). We talk to
the raw HTTP API with httpx rather than the `dropbox` SDK to avoid adding a
dependency — httpx is already used across the backend.

Credentials come from the environment (loaded from .env by the caller):
    DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN

Folder layout on Dropbox (overridable via env):
    DROPBOX_UNZIPPED_DIR  default "/Unzipped Texture Pack"   (source of truth)
    DROPBOX_ZIPPED_PATH   default "/Zipped Texture Pack/pack.zip"
"""
from __future__ import annotations

import io
import json
import os
import time
import zipfile
from typing import Iterable

import httpx

TOKEN_URL = "https://api.dropbox.com/oauth2/token"
RPC_BASE = "https://api.dropboxapi.com/2"
CONTENT_BASE = "https://content.dropboxapi.com/2"

UNZIPPED_DIR = os.environ.get("DROPBOX_UNZIPPED_DIR", "/Unzipped Texture Pack").rstrip("/")
ZIPPED_PATH = os.environ.get("DROPBOX_ZIPPED_PATH", "/Zipped Texture Pack/pack.zip")


class DropboxError(RuntimeError):
    """Raised for any Dropbox API failure or missing configuration."""


# Module-level access-token cache. On Vercel this survives within a warm
# function instance; a cold start simply re-mints one (cheap).
_token: dict = {"value": None, "expires_at": 0.0}


def _creds() -> tuple[str, str, str]:
    key = os.environ.get("DROPBOX_APP_KEY", "").strip()
    secret = os.environ.get("DROPBOX_APP_SECRET", "").strip()
    refresh = os.environ.get("DROPBOX_REFRESH_TOKEN", "").strip()
    missing = [n for n, v in (
        ("DROPBOX_APP_KEY", key),
        ("DROPBOX_APP_SECRET", secret),
        ("DROPBOX_REFRESH_TOKEN", refresh),
    ) if not v]
    if missing:
        raise DropboxError(
            "Dropbox is not configured. Missing: " + ", ".join(missing)
            + ". Run scripts/dropbox_get_refresh_token.py and set the vars in .env."
        )
    return key, secret, refresh


def _access_token() -> str:
    """Return a valid access token, refreshing if expired (60s safety margin)."""
    if _token["value"] and time.time() < _token["expires_at"] - 60:
        return _token["value"]
    key, secret, refresh = _creds()
    resp = httpx.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh},
        auth=(key, secret),
        timeout=30,
    )
    if resp.status_code != 200:
        raise DropboxError(f"Token refresh failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    _token["value"] = data["access_token"]
    _token["expires_at"] = time.time() + int(data.get("expires_in", 14400))
    return _token["value"]


def _auth_header() -> dict:
    return {"Authorization": f"Bearer {_access_token()}"}


def _rpc(endpoint: str, body: dict, *, client: httpx.Client | None = None) -> dict:
    """Call a JSON-in/JSON-out RPC endpoint (api.dropboxapi.com)."""
    c = client or httpx
    resp = c.post(
        f"{RPC_BASE}{endpoint}",
        headers={**_auth_header(), "Content-Type": "application/json"},
        content=json.dumps(body),
        timeout=120,
    )
    if resp.status_code != 200:
        raise DropboxError(f"{endpoint} failed ({resp.status_code}): {resp.text}")
    return resp.json() if resp.content else {}


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------
def upload(path: str, data: bytes, *, overwrite: bool = True,
           client: httpx.Client | None = None) -> dict:
    """Upload bytes to `path` (single-shot; fine for files < 150 MB).

    Parent folders are created automatically by Dropbox. `overwrite=False`
    fails with a conflict if the path already exists (autorename disabled)."""
    c = client or httpx
    arg = {
        "path": path,
        "mode": "overwrite" if overwrite else "add",
        "autorename": False,
        "mute": True,
    }
    resp = c.post(
        f"{CONTENT_BASE}/files/upload",
        headers={
            **_auth_header(),
            "Dropbox-API-Arg": json.dumps(arg),
            "Content-Type": "application/octet-stream",
        },
        content=data,
        timeout=300,
    )
    if resp.status_code == 409:
        raise DropboxError(f"already exists: {path}")
    if resp.status_code != 200:
        raise DropboxError(f"upload failed for {path} ({resp.status_code}): {resp.text}")
    return resp.json()


def list_folder(path: str, *, recursive: bool = False) -> list[dict]:
    """Return all entries under `path`, following pagination. Empty if missing."""
    try:
        page = _rpc("/files/list_folder", {"path": path, "recursive": recursive})
    except DropboxError as e:
        if "not_found" in str(e):
            return []
        raise
    entries = list(page.get("entries", []))
    while page.get("has_more"):
        page = _rpc("/files/list_folder/continue", {"cursor": page["cursor"]})
        entries.extend(page.get("entries", []))
    return entries


def download_zip(path: str) -> bytes:
    """Download a whole folder as a .zip in one call.

    Dropbox limits: the resulting zip must be <= 20 GB and the folder <= 10,000
    files. Note the archive nests everything under the folder's own name."""
    resp = httpx.post(
        f"{CONTENT_BASE}/files/download_zip",
        headers={**_auth_header(), "Dropbox-API-Arg": json.dumps({"path": path})},
        timeout=300,
    )
    if resp.status_code != 200:
        raise DropboxError(f"download_zip failed for {path} ({resp.status_code}): {resp.text}")
    return resp.content


# Opportunistic in-memory cache of minted temporary links. On Vercel this only
# helps while a single function instance stays warm (cold starts wipe it and
# concurrent instances don't share it), so nothing load-bearing depends on it —
# the real caching happens in the browser via Cache-Control on the redirect.
# Dropbox temporary links live ~4h; we expire ours early with a safety margin.
_LINK_TTL = 3.5 * 3600
_link_cache: dict[str, tuple[str, float]] = {}


def temporary_link(path: str) -> str:
    """Return a short-lived (~4h) direct link to a file, usable as an <img> src.
    Cheaper than a shared link for previews; requires files.content.read.

    Reuses a cached link for `path` if one was minted recently (best-effort;
    see :data:`_link_cache`)."""
    hit = _link_cache.get(path)
    if hit and time.time() < hit[1]:
        return hit[0]
    data = _rpc("/files/get_temporary_link", {"path": path})
    link = data["link"]
    _link_cache[path] = (link, time.time() + _LINK_TTL)
    return link


def shared_link(path: str) -> str:
    """Return a direct-download (dl=1) link for `path`, creating one if needed."""
    try:
        data = _rpc("/sharing/create_shared_link_with_settings", {"path": path})
        url = data["url"]
    except DropboxError as e:
        if "shared_link_already_exists" not in str(e):
            raise
        listing = _rpc("/sharing/list_shared_links", {"path": path, "direct_only": True})
        links = listing.get("links", [])
        if not links:
            raise DropboxError(f"no shared link found for {path}")
        url = links[0]["url"]
    # Force direct download: dropbox uses ?dl=0 for preview, ?dl=1 to download.
    return _direct(url)


def _direct(url: str) -> str:
    if "dl=0" in url:
        return url.replace("dl=0", "dl=1")
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}dl=1"


# ---------------------------------------------------------------------------
# Zip repacking (used by sync)
# ---------------------------------------------------------------------------
_JUNK = ("__MACOSX/", ".DS_Store")


def _is_junk(name: str) -> bool:
    return name.startswith("__MACOSX/") or name.endswith(".DS_Store") or "/__MACOSX/" in name


def repack_folder_zip(raw: bytes) -> bytes:
    """Given the bytes from download_zip (nested under the folder name), strip
    the leading folder component and all Mac artifacts, producing a resource
    pack with pack.mcmeta / assets/ at the archive root."""
    src = zipfile.ZipFile(io.BytesIO(raw))
    out_buf = io.BytesIO()
    wrote_mcmeta = False
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            name = info.filename
            if info.is_dir() or _is_junk(name):
                continue
            # Strip the single leading "<folder>/" component Dropbox adds.
            rel = name.split("/", 1)[1] if "/" in name else name
            if not rel or _is_junk(rel):
                continue
            dst.writestr(rel, src.read(info))
            if rel == "pack.mcmeta":
                wrote_mcmeta = True
    if not wrote_mcmeta:
        raise DropboxError(
            "repack produced no pack.mcmeta at root — the Unzipped folder may be "
            "empty or malformed."
        )
    return out_buf.getvalue()
