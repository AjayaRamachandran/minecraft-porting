"""FastAPI backend for the Minecraft converter web UI."""
from __future__ import annotations

import base64
import os
import sys
import tempfile
from pathlib import Path

import httpx
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Locate converter package relative to web/backend/
_ROOT = Path(__file__).resolve().parent.parent.parent

# Load Supabase creds from .env if present — repo root first, then web/backend
# (the latter overrides). python-dotenv ships with uvicorn[standard]; tolerate
# its absence so the converter still runs.
try:
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv(_ROOT / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
except ImportError:
    pass
sys.path.insert(0, str(_ROOT / "convert_villager"))
sys.path.insert(0, str(_ROOT / "npc-maker"))

from converter.cli import build_pipeline, process_mcfunction_file  # noqa: E402
from converter.custom_models import load_custom_index, load_cmd_override_map  # noqa: E402
from converter.implementors import schematic_file  # noqa: E402
import builder as npc_builder  # noqa: E402  (npc-maker/builder.py)

PACK_DIR = _ROOT / "1_21_11_pack"
OLD_PACK_DIR = _ROOT / "1_20_1_pack"
TEXTURES_DIR = PACK_DIR / "assets" / "minecraft" / "textures"

# Default base item when a custom model has no override mapping in the old pack.
DEFAULT_BASE_ITEM = "paper"

app = FastAPI(title="MC Converter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Serve resource-pack textures so the Item Library can show thumbnails, e.g.
# GET /api/textures/custom/<stem>.png.
if TEXTURES_DIR.is_dir():
    app.mount("/api/textures", StaticFiles(directory=str(TEXTURES_DIR)), name="textures")

# Lazily-built, cached catalog of selectable custom models (stem + base item).
_MODEL_CATALOG: list[dict] | None = None


def _build_model_catalog() -> list[dict]:
    """Catalog of custom models a user can pick a texture from.

    Each entry is ``{stem, base_item, texture}``. ``base_item`` is the vanilla
    item the model was originally attached to (from the old pack's overrides),
    falling back to :data:`DEFAULT_BASE_ITEM`. ``texture`` is the path the
    frontend loads from the ``/api/textures`` mount.
    """
    stems = load_custom_index(PACK_DIR)
    # Invert (base, cmd) -> stem into stem -> base_item (first mapping wins).
    stem_to_base: dict[str, str] = {}
    for (base, _cmd), stem in load_cmd_override_map(OLD_PACK_DIR).items():
        stem_to_base.setdefault(stem, base)
    return [
        {
            "stem": s,
            "base_item": stem_to_base.get(s, DEFAULT_BASE_ITEM),
            "texture": f"/api/textures/custom/{s}.png",
        }
        for s in stems
    ]


@app.get("/api/health")
def health():
    return {"status": "ok", "pack": str(PACK_DIR), "old_pack": str(OLD_PACK_DIR)}


@app.get("/api/items/models")
def item_models():
    """Return the searchable custom-model catalog (cached after first call)."""
    global _MODEL_CATALOG
    if _MODEL_CATALOG is None:
        try:
            _MODEL_CATALOG = _build_model_catalog()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"models": _MODEL_CATALOG}


# ---------------------------------------------------------------------------
# Custom-item library — persisted in a shared Supabase `custom_items` table via
# its PostgREST API. Columns: id (uuid), name, base_item, model_stem, count,
# custom_name (jsonb), lore (jsonb), custom_data (jsonb), created_at.
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
_ITEMS_TABLE = "custom_items"
# Columns a client is allowed to write (id/created_at are server-managed).
_ITEM_FIELDS = ("name", "base_item", "model_stem", "count", "custom_name", "lore", "custom_data")


def _supabase(method: str, *, params: dict | None = None, json: object | None = None) -> list:
    """Call the Supabase REST endpoint for ``custom_items`` and return rows.

    Raises 503 if creds aren't configured, or surfaces the upstream error.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(
            status_code=503,
            detail="Item library storage is not configured (set SUPABASE_URL / SUPABASE_KEY).",
        )
    url = f"{SUPABASE_URL}/rest/v1/{_ITEMS_TABLE}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        resp = httpx.request(method, url, params=params, json=json, headers=headers, timeout=15.0)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Storage request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=f"Storage error: {resp.text}")
    if resp.status_code == 204 or not resp.content:
        return []
    return resp.json()


def _clean_item(payload: dict) -> dict:
    """Keep only writable columns from a client payload."""
    return {k: payload[k] for k in _ITEM_FIELDS if k in payload}


@app.get("/api/items")
def list_items():
    rows = _supabase("GET", params={"select": "*", "order": "created_at.desc"})
    return {"items": rows}


@app.post("/api/items")
def create_item(payload: dict = Body(...)):
    rows = _supabase("POST", json=_clean_item(payload))
    return {"item": rows[0] if rows else None}


@app.put("/api/items/{item_id}")
def update_item(item_id: str, payload: dict = Body(...)):
    rows = _supabase("PATCH", params={"id": f"eq.{item_id}"}, json=_clean_item(payload))
    if not rows:
        raise HTTPException(status_code=404, detail="Item not found.")
    return {"item": rows[0]}


@app.delete("/api/items/{item_id}")
def delete_item(item_id: str):
    _supabase("DELETE", params={"id": f"eq.{item_id}"})
    return {"ok": True}


@app.post("/api/npc/generate")
def npc_generate(payload: dict = Body(...)) -> JSONResponse:
    """Build a 1.21.11 NPC schematic from editor/JSON state.

    Accepts either builder format (1.0 legacy or 1.1); the result is migrated to
    1.1. Returns the ``.schem`` (base64), the normalized 1.1 JSON, and the
    human-readable command listing.
    """
    import mcschematic  # noqa: PLC0415

    try:
        normalized = npc_builder.normalize(payload)
        schem, commands = npc_builder.build(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    name = normalized.get("npc_variable_initial") or "npc"
    version = getattr(mcschematic.Version, npc_builder.SCHEM_VERSION_NAME)
    with tempfile.TemporaryDirectory() as tmpdir:
        schem.save(tmpdir, name, version)
        raw = (Path(tmpdir) / f"{name}.schem").read_bytes()

    return JSONResponse({
        "filename": f"{name}.schem",
        "schem_base64": base64.b64encode(raw).decode(),
        "normalized": normalized,
        "commands": commands,
    })


@app.post("/api/convert")
async def convert(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    filename: str = Form(default="input.mcfunction"),
) -> JSONResponse:
    if file is None and not text:
        raise HTTPException(status_code=400, detail="Provide a file upload or text input.")

    pipeline = build_pipeline(PACK_DIR, threshold=0.5, old_pack_dir=OLD_PACK_DIR)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        if file:
            in_name = file.filename or "input.schem"
            in_path = tmp / in_name
            in_path.write_bytes(await file.read())
        else:
            in_name = filename or "input.mcfunction"
            in_path = tmp / in_name
            in_path.write_text(text, encoding="utf-8")

        out_name = "converted_" + in_path.name
        out_path = tmp / out_name

        try:
            suffix = in_path.suffix.lower()
            if suffix == ".schem":
                schematic_file.convert_file(in_path, out_path, pipeline)
                raw = out_path.read_bytes()
                return JSONResponse({
                    "filename": out_name,
                    "is_binary": True,
                    "content": base64.b64encode(raw).decode(),
                    "warnings": pipeline.warnings,
                })
            elif suffix == ".mcfunction":
                process_mcfunction_file(in_path, out_path, pipeline)
                return JSONResponse({
                    "filename": out_name,
                    "is_binary": False,
                    "content": out_path.read_text(encoding="utf-8"),
                    "warnings": pipeline.warnings,
                })
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
