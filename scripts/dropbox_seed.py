"""One-time seed: upload a texture-pack .zip's contents into the Dropbox
"Unzipped Texture Pack" folder (the app's source of truth).

Mac artifacts (__MACOSX/, .DS_Store) are skipped. Files land at
    <DROPBOX_UNZIPPED_DIR>/<path-inside-zip>
so pack.mcmeta / pack.png / assets/ end up at the folder root.

    python scripts/dropbox_seed.py path/to/pack.zip
    python scripts/dropbox_seed.py https://www.dropbox.com/.../pack.zip?dl=0

Requires DROPBOX_APP_KEY / APP_SECRET / REFRESH_TOKEN in .env.
"""
from __future__ import annotations

import io
import os
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "web" / "backend" / ".env", override=True)
except ImportError:
    pass

from web.backend import dropbox_client as dbx  # noqa: E402

WORKERS = 6  # modest concurrency to stay well under Dropbox rate limits


def _load_zip_bytes(src: str) -> bytes:
    if src.startswith("http://") or src.startswith("https://"):
        url = src.replace("dl=0", "dl=1")
        if "dl=" not in url:
            url += ("&" if "?" in url else "?") + "dl=1"
        print(f"Downloading {url} ...")
        resp = httpx.get(url, follow_redirects=True, timeout=300)
        resp.raise_for_status()
        return resp.content
    return Path(src).read_bytes()


def _upload_with_retry(client: httpx.Client, path: str, data: bytes, attempts: int = 4) -> None:
    for i in range(attempts):
        try:
            dbx.upload(path, data, overwrite=True, client=client)
            return
        except dbx.DropboxError as e:
            if "429" in str(e) or "too_many_requests" in str(e):
                time.sleep(2 * (i + 1))
                continue
            raise
    raise dbx.DropboxError(f"gave up after {attempts} attempts: {path}")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/dropbox_seed.py <zip-path-or-url>")
        return 1

    raw = _load_zip_bytes(sys.argv[1])
    zf = zipfile.ZipFile(io.BytesIO(raw))

    items = []
    for info in zf.infolist():
        name = info.filename
        if info.is_dir():
            continue
        if name.startswith("__MACOSX/") or name.endswith(".DS_Store") or "/__MACOSX/" in name:
            continue
        items.append((name, zf.read(info)))

    total = len(items)
    print(f"Seeding {total} files into {dbx.UNZIPPED_DIR!r} on Dropbox ...")

    done = {"n": 0, "errors": []}
    with httpx.Client() as client, ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {
            pool.submit(_upload_with_retry, client, f"{dbx.UNZIPPED_DIR}/{name}", data): name
            for name, data in items
        }
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                fut.result()
            except Exception as exc:  # noqa: BLE001
                done["errors"].append((name, str(exc)))
            done["n"] += 1
            if done["n"] % 100 == 0 or done["n"] == total:
                print(f"  {done['n']}/{total}")

    if done["errors"]:
        print(f"\nDONE with {len(done['errors'])} error(s):")
        for name, err in done["errors"][:20]:
            print(f"  ! {name}: {err}")
        return 1
    print("\nDone. All files uploaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
