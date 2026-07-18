"""FastAPI backend for the Minecraft converter web UI."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
import tempfile
import time
from pathlib import Path

# Some Windows Python installs lack a .webp mapping, which makes StaticFiles
# serve villager preview renders as text/plain. Register it explicitly.
mimetypes.add_type("image/webp", ".webp")

import httpx
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
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
from converter.custom_models import load_cmd_override_map  # noqa: E402
from converter.implementors import schematic_file  # noqa: E402
from converter.item_converter import ItemConverter  # noqa: E402
from converter.snbt import Num, Str, TypedArr, snbt_parse  # noqa: E402
from converter.command_parsing import GIVE_RE, split_top_level_nbt  # noqa: E402
import builder as npc_builder  # noqa: E402  (npc-maker/builder.py)

PACK_DIR = _ROOT / "1_21_11_pack"
OLD_PACK_DIR = _ROOT / "1_20_1_pack"

# Default base item when a custom model has no override mapping in the old pack.
DEFAULT_BASE_ITEM = "paper"

app = FastAPI(title="MC Converter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Custom-item thumbnails are no longer served from the local pack — they come
# live from Dropbox via GET /api/texture/thumb/<stem> (see the Texture Pack
# section below), so an uploaded texture is visible without a redeploy.

# Vanilla item textures, for items that inherit the base game look. These are
# base-game assets that never change and aren't in the Dropbox pack (a resource
# pack only carries overrides), so they stay served from the repo.
BASE_TEXTURES_DIR = _ROOT / "base_textures"
if BASE_TEXTURES_DIR.is_dir():
    app.mount("/api/base-textures", StaticFiles(directory=str(BASE_TEXTURES_DIR)), name="base_textures")

# Villager biome/profession preview renders (mirrored from the wiki), served as
# /api/villager-textures/<biome>_<profession>.webp for the Villager Maker preview.
VILLAGER_TEXTURES_DIR = Path(__file__).resolve().parent / "villager_textures"
if VILLAGER_TEXTURES_DIR.is_dir():
    app.mount("/api/villager-textures", StaticFiles(directory=str(VILLAGER_TEXTURES_DIR)), name="villager_textures")

# Lazily-built, cached catalog of selectable custom models (stem + base item).
# Sourced live from Dropbox, so it carries a short TTL and is invalidated on
# upload — a newly-uploaded texture shows up in the editors without a redeploy.
_MODEL_CATALOG: list[dict] | None = None
_MODEL_CATALOG_AT: float = 0.0
_MODEL_CATALOG_TTL = 300  # seconds; backstop for uploads by another instance

# Lazily-built, cached list of vanilla base-item ids we have textures for. This
# is the set of valid base items the editors let a user pick from.
_BASE_ITEMS: list[str] | None = None


def _build_model_catalog() -> list[dict]:
    """Catalog of custom models a user can pick a texture from.

    Each entry is ``{stem, base_item, texture}``. The stem list comes live from
    the Dropbox pack's ``textures/custom`` folder (so uploads appear without a
    redeploy). ``base_item`` is the vanilla item the model was originally
    attached to, from the old pack's CMD overrides (historical, ships in the
    repo) — falling back to :data:`DEFAULT_BASE_ITEM` for stems with no override
    (e.g. brand-new uploads). ``texture`` is the Dropbox-backed thumb endpoint.
    """
    entries = _dbx.list_folder(_dbx_path(_CUSTOM_TEX))
    stems = sorted(
        Path(e["name"]).stem
        for e in entries
        if e.get(".tag") == "file" and e["name"].lower().endswith(".png")
    )
    # Invert (base, cmd) -> stem into stem -> base_item (first mapping wins).
    stem_to_base: dict[str, str] = {}
    for (base, _cmd), stem in load_cmd_override_map(OLD_PACK_DIR).items():
        stem_to_base.setdefault(stem, base)
    return [
        {
            "stem": s,
            "base_item": stem_to_base.get(s, DEFAULT_BASE_ITEM),
            "texture": f"/api/texture/thumb/{s}",
        }
        for s in stems
    ]


@app.get("/api/health")
def health():
    return {"status": "ok", "pack": str(PACK_DIR), "old_pack": str(OLD_PACK_DIR)}


@app.get("/api/items/models")
def item_models():
    """Return the searchable custom-model catalog (cached, short TTL)."""
    global _MODEL_CATALOG, _MODEL_CATALOG_AT
    now = time.time()
    if _MODEL_CATALOG is None or now - _MODEL_CATALOG_AT > _MODEL_CATALOG_TTL:
        try:
            _MODEL_CATALOG = _build_model_catalog()
            _MODEL_CATALOG_AT = now
        except _dbx.DropboxError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"models": _MODEL_CATALOG}


@app.get("/api/base-items")
def base_items():
    """Return the sorted list of vanilla base-item ids we have a texture for.

    These are exactly the items the editors can render as a base-game item
    (via the ``/api/base-textures`` mount), so it doubles as the set of valid
    base items a user may type/select in the Item Library and villager slots.
    """
    global _BASE_ITEMS
    if _BASE_ITEMS is None:
        if BASE_TEXTURES_DIR.is_dir():
            _BASE_ITEMS = sorted(p.stem for p in BASE_TEXTURES_DIR.glob("*.png"))
        else:
            _BASE_ITEMS = []
    return {"items": _BASE_ITEMS}


# ---------------------------------------------------------------------------
# Custom-item library — persisted in a shared Supabase `custom_items` table via
# its PostgREST API. Columns: id (uuid), manifest (jsonb), created_at.
#
# The whole item is stored as one `manifest` blob — the give-payload shape
# { base_item, count, components:{...} } — so arbitrary components (enchantments,
# attribute modifiers, …) survive even though the editor only exposes a few.
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
_ITEMS_TABLE = "custom_items"


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
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        # A paused/spun-down Supabase project refuses connections (surfaces as
        # ConnectError, e.g. "[Errno 16] Device or resource busy"). Give the user
        # an actionable message instead of the raw socket error.
        raise HTTPException(
            status_code=503,
            detail=(
                "Supabase database has been spun down. Spin it up again at "
                "https://supabase.com/dashboard/project/trhukvbjdijydyikhbpd"
            ),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Storage request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=f"Storage error: {resp.text}")
    if resp.status_code == 204 or not resp.content:
        return []
    return resp.json()


# The manifest is stored as the item string `minecraft:<id>[<components>]` (the
# `/give` item argument). The API serializes structured components → that string
# on write and parses it back to structured components on read, so the frontend
# only ever deals with JSON while the DB keeps the canonical item string.
def _structured_manifest(payload: dict) -> dict:
    return payload.get("manifest") if isinstance(payload.get("manifest"), dict) else payload


def _item_string(manifest: dict) -> str:
    """Structured manifest { base_item, components } → `minecraft:<id>[<comps>]`."""
    norm = npc_builder._norm_item(manifest)
    comps = {k: npc_builder._json_to_snbt(v, Num, Str) for k, v in norm["components"].items()}
    return f"minecraft:{norm['base_item']}{ItemConverter.render_components_bracket(comps)}"


def _row_out(row: dict) -> dict:
    """Parse a stored row's manifest string back into structured components."""
    m = row.get("manifest")
    if isinstance(m, str):
        try:
            return {**row, "manifest": _parse_item_string(m)}
        except Exception:  # noqa: BLE001
            return {**row, "manifest": _normalize_manifest(m, {})}
    return row


@app.get("/api/items")
def list_items():
    rows = _supabase("GET", params={"select": "*", "order": "created_at.desc"})
    return {"items": [_row_out(r) for r in rows]}


@app.post("/api/items")
def create_item(payload: dict = Body(...)):
    rows = _supabase("POST", json={"manifest": _item_string(_structured_manifest(payload))})
    return {"item": _row_out(rows[0]) if rows else None}


@app.put("/api/items/{item_id}")
def update_item(item_id: str, payload: dict = Body(...)):
    rows = _supabase("PATCH", params={"id": f"eq.{item_id}"},
                     json={"manifest": _item_string(_structured_manifest(payload))})
    if not rows:
        raise HTTPException(status_code=404, detail="Item not found.")
    return {"item": _row_out(rows[0])}


@app.delete("/api/items/{item_id}")
def delete_item(item_id: str):
    _supabase("DELETE", params={"id": f"eq.{item_id}"})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Item import — parse /give commands and .schem files into item manifests.
# ---------------------------------------------------------------------------
def _snbt_to_json(node):
    """SNBT node tree (Num/Str/TypedArr/dict/list) → plain JSON values."""
    if isinstance(node, dict):
        return {k: _snbt_to_json(v) for k, v in node.items()}
    if isinstance(node, TypedArr):
        return [_snbt_to_json(x) for x in node.items]
    if isinstance(node, list):
        return [_snbt_to_json(x) for x in node]
    if isinstance(node, Num):
        # A 0/1 byte is Minecraft's boolean; surface it as a real bool.
        if node.suffix == "b" and node.value in (0, 1):
            return bool(node.value)
        return node.value
    if isinstance(node, Str):
        return node.value
    return node


def _maybe_json_text(value):
    """A text component may arrive as a JSON string (`'{"text":"x"}'`) or an SNBT
    compound. Normalize JSON strings into objects so the editor/preview agree."""
    if isinstance(value, str):
        s = value.strip()
        if s and s[0] in "{[\"":
            try:
                return json.loads(s)
            except ValueError:
                return value
    return value


def _split_top_level(s: str, sep: str) -> list[str]:
    """Split on `sep` only at bracket/brace depth 0, skipping quoted strings."""
    out, depth, in_str, start = [], 0, None, 0
    i = 0
    while i < len(s):
        c = s[i]
        if in_str is not None:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "\"'":
            in_str = c
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        elif c == sep and depth == 0:
            out.append(s[start:i])
            start = i + 1
        i += 1
    out.append(s[start:])
    return out


def _parse_component_bracket(bracket: str) -> dict:
    """Parse a modern `[k=v,k=v]` component bracket into a JSON components dict."""
    inner = bracket.strip()
    if inner.startswith("["):
        inner = inner[1:]
    if inner.endswith("]"):
        inner = inner[:-1]
    comps: dict = {}
    for part in _split_top_level(inner, ","):
        part = part.strip()
        if not part:
            continue
        eq = part.find("=")
        if eq < 0:
            continue
        key = part[:eq].strip()
        val = part[eq + 1:].strip()
        if not key.startswith("minecraft:") and ":" not in key:
            key = f"minecraft:{key}"
        comps[key] = _snbt_to_json(snbt_parse(val))
    return comps


def _normalize_manifest(base_item: str, components: dict) -> dict:
    """Build a clean structured manifest, normalizing text components to objects.
    A custom item has no inherent stack count, so none is stored."""
    comps = dict(components)
    if "minecraft:custom_name" in comps:
        comps["minecraft:custom_name"] = _maybe_json_text(comps["minecraft:custom_name"])
    if "minecraft:lore" in comps and isinstance(comps["minecraft:lore"], list):
        comps["minecraft:lore"] = [_maybe_json_text(x) for x in comps["minecraft:lore"]]
    if base_item.startswith("minecraft:"):
        base_item = base_item.split(":", 1)[1]
    return {"base_item": base_item, "components": comps}


def _parse_item_string(s: str) -> dict:
    """Item string `minecraft:<id>[<comps>]` → structured manifest."""
    s = (s or "").strip()
    b = s.find("[")
    item_id, bracket = (s, "") if b < 0 else (s[:b], s[b:])
    comps = _parse_component_bracket(bracket) if bracket.strip() else {}
    return _normalize_manifest(item_id.strip() or "paper", comps)


def _trade_item_manifests(manifest: dict) -> list[dict] | None:
    """If ``manifest`` is a villager spawn egg carrying trades, return the
    buy/buyB/sell item of every recipe as its own item manifest. Returns ``None``
    when the manifest isn't a trading villager egg, so the caller keeps the
    original item as-is (a plain egg, or an egg with no Offers/Recipes)."""
    if manifest.get("base_item") != "villager_spawn_egg":
        return None
    entity = (manifest.get("components") or {}).get("minecraft:entity_data")
    if not isinstance(entity, dict):
        return None
    offers = entity.get("Offers") if isinstance(entity.get("Offers"), dict) else {}
    recipes = offers.get("Recipes") if isinstance(offers.get("Recipes"), list) else []
    if not recipes:
        return None

    out: list[dict] = []
    for r in recipes:
        if not isinstance(r, dict):
            continue
        for slot in ("buy", "buyB", "sell"):
            it = r.get(slot)
            if not isinstance(it, dict):
                continue
            iid = str(it.get("id") or "").strip()
            if not iid:
                continue
            comps = it.get("components") if isinstance(it.get("components"), dict) else {}
            # Skip plain vanilla items (e.g. emerald payment) — only trade goods
            # carrying components are "custom" items worth adding to the library.
            if not comps:
                continue
            out.append(_normalize_manifest(iid, comps))
    return out


def _manifests_from_command(text: str, expand_villager_trades: bool = False) -> list[dict]:
    """Parse every /give line in `text` into manifests. Handles modern
    `item[components] count` and legacy `item{tag} count`.

    When ``expand_villager_trades`` is set, a trading villager spawn egg is
    replaced by the individual buy/sell items of its trades (used by the Item
    Library import, which harvests trade goods rather than the raw egg)."""
    out: list[dict] = []
    pipeline = build_pipeline(PACK_DIR, threshold=0.5, old_pack_dir=OLD_PACK_DIR)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = GIVE_RE.match(line)
        if not m:
            continue
        item_id = m.group("item")
        rest = m.group("rest").lstrip()
        comps: dict = {}
        count = 1
        if rest.startswith("["):
            depth, in_str, end = 0, None, -1
            for i, c in enumerate(rest):
                if in_str is not None:
                    if c == in_str:
                        in_str = None
                elif c in "\"'":
                    in_str = c
                elif c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end >= 0:
                comps = _parse_component_bracket(rest[:end + 1])
                trailing = rest[end + 1:].strip()
                if trailing.split():
                    try:
                        count = int(trailing.split()[0])
                    except ValueError:
                        pass
        elif rest.startswith("{"):
            nbt_text, trailing = split_top_level_nbt(rest)
            if nbt_text:
                tag = snbt_parse(nbt_text)
                if isinstance(tag, dict):
                    snbt_comps = pipeline.item.convert_tag_to_components(tag, item_id, "import")
                    comps = {k: _snbt_to_json(v) for k, v in snbt_comps.items()}
                trailing = trailing.strip()
                if trailing.split():
                    try:
                        count = int(trailing.split()[0])
                    except ValueError:
                        pass
        manifest = _normalize_manifest(item_id, comps)
        # A villager spawn egg is a container of trades, not a single custom
        # item — expand it into the buy/sell items of its Offers instead.
        trade_items = _trade_item_manifests(manifest) if expand_villager_trades else None
        if trade_items is not None:
            out.extend(trade_items)
        else:
            out.append(manifest)
    return out


# Block ids whose Items list we harvest when importing a schematic.
_CONTAINER_IDS = {
    "minecraft:chest", "minecraft:trapped_chest", "minecraft:barrel",
    "minecraft:dispenser", "minecraft:dropper", "minecraft:hopper",
    "minecraft:shulker_box", "minecraft:furnace", "minecraft:blast_furnace",
    "minecraft:smoker", "minecraft:crafter", "minecraft:decorated_pot",
}


def _manifests_from_schem(raw: bytes) -> list[dict]:
    """Parse every container item in a .schem into manifests."""
    import nbtlib  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "import.schem"
        path.write_bytes(raw)
        schem = nbtlib.load(str(path))
    root = schem.get("Schematic", schem)
    blocks = root.get("Blocks") if hasattr(root, "get") else None
    be_list = None
    if blocks is not None and hasattr(blocks, "get"):
        be_list = blocks.get("BlockEntities")
    if be_list is None:
        be_list = root.get("BlockEntities") if hasattr(root, "get") else None
    if not be_list:
        return []

    pipeline = build_pipeline(PACK_DIR, threshold=0.5, old_pack_dir=OLD_PACK_DIR)
    out: list[dict] = []
    for be in be_list:
        data = be.get("Data", be) if hasattr(be, "get") else be
        bid = str(be.get("Id") or be.get("id") or data.get("id") or "")
        if bid and bid not in _CONTAINER_IDS:
            continue
        items = data.get("Items") if hasattr(data, "get") else None
        if not items:
            continue
        for item_tag in items:
            try:
                node = snbt_parse(item_tag.snbt())
                modern = pipeline.item.convert_item_nbt(node, "import")
            except Exception:  # noqa: BLE001
                continue
            id_node = modern.get("id")
            item_id = id_node.value if isinstance(id_node, Str) else "minecraft:paper"
            comps_node = modern.get("components")
            comps = {k: _snbt_to_json(v) for k, v in comps_node.items()} if isinstance(comps_node, dict) else {}
            # Skip plain vanilla items — only items carrying components are "custom".
            if not comps:
                continue
            out.append(_normalize_manifest(item_id, comps))
    return out


def _dedupe_manifests(manifests: list[dict]) -> list[dict]:
    seen, out = set(), []
    for m in manifests:
        key = json.dumps(m, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


@app.post("/api/items/import")
async def import_items(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
):
    """Parse give commands and/or a .schem into item manifests and save them all."""
    manifests: list[dict] = []
    try:
        if file is not None:
            raw = await file.read()
            manifests += _manifests_from_schem(raw)
        if text and text.strip():
            manifests += _manifests_from_command(text, expand_villager_trades=True)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not parse import: {exc}") from exc

    if not manifests:
        raise HTTPException(status_code=400, detail="No items found to import.")

    manifests = _dedupe_manifests(manifests)
    rows = _supabase("POST", json=[{"manifest": _item_string(m)} for m in manifests])
    return {"items": [_row_out(r) for r in rows], "count": len(rows)}


@app.post("/api/items/give-command")
def give_command(payload: dict = Body(...)):
    """Render a manifest as a copy-pasteable `/give @p …` command."""
    try:
        body = npc_builder._give_command(npc_builder._norm_item(_structured_manifest(payload)))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not render command: {exc}") from exc
    return {"command": f"/{body}"}


# ---------------------------------------------------------------------------
# Villager Maker — render a trading-villager spawn egg as a /give command.
#
# The output is a single `villager_spawn_egg` carrying `minecraft:entity_data`
# with a non-moving, invulnerable villager (Silent/NoAI/PersistenceRequired) and
# an `Offers.Recipes` list built from the editor's drag-and-drop trade slots.
# Item components round-trip through the same SNBT renderer the Item Library
# uses, so custom names, models, lore, enchantments, etc. survive verbatim.
# ---------------------------------------------------------------------------
VILLAGER_LEVEL = 99          # high enough that every trade tier is unlocked
VILLAGER_DEFAULT_MAX_USES = 99999999


def _villager_recipe_item(payload: object) -> dict | None:
    """A give-payload ``{base_item, count, components}`` → a recipe item
    ``{id, count, components}`` (villager trades reference items by ``id``)."""
    if not isinstance(payload, dict) or not payload.get("base_item"):
        return None
    norm = npc_builder._norm_item(payload)
    item = {"id": f"minecraft:{norm['base_item']}", "count": norm["count"]}
    if norm["components"]:  # omit an empty component compound for plain items
        item["components"] = norm["components"]
    return item


@app.post("/api/villager/give-command")
def villager_give_command(payload: dict = Body(...)):
    """Build a ``/give`` command for a static trading villager spawn egg."""
    try:
        ItemConverter, Num, Str = npc_builder._converter_imports()

        name_comp = payload.get("name") or None  # a Minecraft text component
        biome = str(payload.get("biome") or "plains").replace("minecraft:", "")
        profession = str(payload.get("profession") or "none").replace("minecraft:", "")
        level = int(payload.get("level") or VILLAGER_LEVEL)

        recipes: list[dict] = []
        for t in payload.get("trades") or []:
            buy = _villager_recipe_item(t.get("buy"))
            buy_b = _villager_recipe_item(t.get("buyB"))
            sell = _villager_recipe_item(t.get("sell"))
            if not buy or not sell:  # a valid trade needs at least buy + sell
                continue
            recipe = {"maxUses": int(t.get("max_uses") or VILLAGER_DEFAULT_MAX_USES), "buy": buy}
            if buy_b:
                recipe["buyB"] = buy_b
            recipe["sell"] = sell
            recipes.append(recipe)

        # A non-moving, unkillable, persistent villager.
        entity: dict = {
            "id": "minecraft:villager",
            "Silent": True,
            "Invulnerable": True,
            "PersistenceRequired": True,
            "NoAI": True,
            "Willing": True,
            "VillagerData": {
                "level": level,
                "profession": f"minecraft:{profession}",
                "type": f"minecraft:{biome}",
            },
        }
        if name_comp:
            entity["CustomName"] = name_comp
        if recipes:
            entity["Offers"] = {"Recipes": recipes}

        top: dict = {"minecraft:entity_data": entity}
        if name_comp:
            top["minecraft:custom_name"] = name_comp

        comps = {k: npc_builder._json_to_snbt(v, Num, Str) for k, v in top.items()}
        bracket = ItemConverter.render_components_bracket(comps)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not render command: {exc}") from exc
    return {"command": f"/give @p minecraft:villager_spawn_egg{bracket} 1"}


def _slot_from_recipe_item(it: object) -> dict | None:
    """Recipe item ``{id, count, components}`` → editor give-payload
    ``{base_item, count, components}``. Returns ``None`` for a missing slot."""
    if not isinstance(it, dict):
        return None
    iid = str(it.get("id") or "").replace("minecraft:", "")
    if not iid:
        return None
    return {"base_item": iid, "count": int(it.get("count") or 1), "components": it.get("components") or {}}


@app.post("/api/villager/import")
def villager_import(payload: dict = Body(...)):
    """Parse a villager-spawn-egg ``/give`` command back into editor state."""
    text = str(payload.get("command") or "").strip()
    try:
        manifests = _manifests_from_command(text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not parse command: {exc}") from exc
    if not manifests:
        raise HTTPException(status_code=400, detail="No /give command found.")

    comps = manifests[0].get("components") or {}
    entity = comps.get("minecraft:entity_data")
    if not isinstance(entity, dict):
        raise HTTPException(status_code=400, detail="Command has no villager entity_data.")

    vdata = entity.get("VillagerData") if isinstance(entity.get("VillagerData"), dict) else {}
    biome = str(vdata.get("type") or "plains").replace("minecraft:", "")
    profession = str(vdata.get("profession") or "none").replace("minecraft:", "")
    name = entity.get("CustomName") or comps.get("minecraft:custom_name") or None

    offers = entity.get("Offers") if isinstance(entity.get("Offers"), dict) else {}
    recipes = offers.get("Recipes") if isinstance(offers.get("Recipes"), list) else []
    trades = []
    for r in recipes:
        if not isinstance(r, dict):
            continue
        trades.append({
            "buy": _slot_from_recipe_item(r.get("buy")),
            "buyB": _slot_from_recipe_item(r.get("buyB")),
            "sell": _slot_from_recipe_item(r.get("sell")),
            "max_uses": int(r.get("maxUses") or VILLAGER_DEFAULT_MAX_USES),
        })

    return {"name": name, "biome": biome, "profession": profession, "trades": trades}


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


# ---------------------------------------------------------------------------
# Texture Pack — manage the Dropbox-hosted server resource pack.
#
# Custom items follow a 3-file convention keyed on <name> (all relative to
# the Unzipped Texture Pack folder on Dropbox):
#   assets/minecraft/items/custom/<name>.json    -> item model definition
#   assets/minecraft/models/custom/<name>.json   -> model (parent + layer0)
#   assets/minecraft/textures/custom/<name>.png   -> the image
# "Sync" repacks the whole Unzipped folder into a clean pack.zip and returns a
# direct-download link for Apex Hosting to pull.
# ---------------------------------------------------------------------------
import re as _re  # local alias; module already imports plenty

try:
    from web.backend import dropbox_client as _dbx
except ImportError:  # running from web/backend/ directly
    import dropbox_client as _dbx  # type: ignore

_CUSTOM_TEX = "assets/minecraft/textures/custom"
_CUSTOM_MODEL = "assets/minecraft/models/custom"
_CUSTOM_ITEM = "assets/minecraft/items/custom"
_VALID_PARENTS = {"generated", "handheld"}
_NAME_RE = _re.compile(r"[^a-z0-9_.-]")


def _texture_name(filename: str) -> str:
    """Derive a Minecraft-safe custom-item name from an uploaded filename."""
    stem = Path(filename or "").stem.strip().lower().replace(" ", "_")
    stem = _NAME_RE.sub("", stem)
    return stem


def _model_json(name: str, parent: str) -> bytes:
    doc = {
        "parent": f"minecraft:item/{parent}",
        "textures": {"layer0": f"minecraft:custom/{name}"},
    }
    return json.dumps(doc, indent=2).encode("utf-8")


def _item_def_json(name: str) -> bytes:
    doc = {"model": {"type": "minecraft:model", "model": f"minecraft:custom/{name}"}}
    return json.dumps(doc, indent=2).encode("utf-8")


def _dbx_path(*parts: str) -> str:
    return _dbx.UNZIPPED_DIR + "/" + "/".join(parts)


@app.get("/api/texture/list")
def texture_list():
    """Names of custom textures currently in the Unzipped pack (sorted)."""
    try:
        entries = _dbx.list_folder(_dbx_path(_CUSTOM_TEX))
    except _dbx.DropboxError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    names = sorted(
        Path(e["name"]).stem
        for e in entries
        if e.get(".tag") == "file" and e["name"].lower().endswith(".png")
    )
    return {"textures": names, "count": len(names)}


@app.get("/api/texture/thumb/{name}")
def texture_thumb(name: str):
    """Redirect to a short-lived Dropbox link for a custom texture PNG, so the
    browser loads the image straight from Dropbox's CDN (and lazy-loads)."""
    safe = _texture_name(name)
    if not safe:
        raise HTTPException(status_code=400, detail="invalid texture name")
    try:
        link = _dbx.temporary_link(_dbx_path(_CUSTOM_TEX, f"{safe}.png"))
    except _dbx.DropboxError as exc:
        code = 404 if "not_found" in str(exc) else 502
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    # Let the browser cache the redirect itself for ~50 min so repeat views
    # don't re-hit this function (which matters on serverless, where we have no
    # reliable shared server-side cache). The window stays well under Dropbox's
    # ~4h link expiry so a cached redirect never points at a dead link.
    return RedirectResponse(link, status_code=302,
                            headers={"Cache-Control": "public, max-age=3000"})


@app.post("/api/texture/upload")
async def texture_upload(
    files: list[UploadFile] = File(...),
    parent: str = Form(default="generated"),
    overwrite: bool = Form(default=True),
) -> JSONResponse:
    """Upload PNG(s): derive name, write the 2 JSON files + the PNG into the
    Unzipped pack on Dropbox. Returns a per-file result list."""
    if parent not in _VALID_PARENTS:
        raise HTTPException(status_code=400, detail=f"parent must be one of {sorted(_VALID_PARENTS)}")

    results = []
    for f in files:
        name = _texture_name(f.filename or "")
        try:
            data = await f.read()
            if not name:
                raise ValueError("could not derive a valid name from filename")
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                raise ValueError("not a PNG file")
            _dbx.upload(_dbx_path(_CUSTOM_TEX, f"{name}.png"), data, overwrite=overwrite)
            _dbx.upload(_dbx_path(_CUSTOM_MODEL, f"{name}.json"), _model_json(name, parent),
                        overwrite=overwrite)
            _dbx.upload(_dbx_path(_CUSTOM_ITEM, f"{name}.json"), _item_def_json(name),
                        overwrite=overwrite)
            results.append({"filename": f.filename, "name": name, "status": "ok"})
        except _dbx.DropboxError as exc:
            msg = "already exists" if "already exists" in str(exc) else str(exc)
            results.append({"filename": f.filename, "name": name, "status": "error", "error": msg})
        except Exception as exc:  # noqa: BLE001 — surface per-file, keep going
            results.append({"filename": f.filename, "name": name, "status": "error", "error": str(exc)})

    ok = sum(1 for r in results if r["status"] == "ok")
    if ok:
        # New textures landed — drop the cached catalog so this instance picks
        # them up immediately (other warm instances catch up within the TTL).
        global _MODEL_CATALOG
        _MODEL_CATALOG = None
    return JSONResponse({"results": results, "ok": ok, "total": len(results)})


@app.post("/api/texture/sync")
def texture_sync() -> JSONResponse:
    """Pull the whole Unzipped pack, repack it cleanly, upload as pack.zip, and
    return a direct-download link for Apex to pull."""
    try:
        raw = _dbx.download_zip(_dbx.UNZIPPED_DIR)
        packed = _dbx.repack_folder_zip(raw)
        _dbx.upload(_dbx.ZIPPED_PATH, packed, overwrite=True)
        link = _dbx.shared_link(_dbx.ZIPPED_PATH)
    except _dbx.DropboxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return JSONResponse({"link": link, "bytes": len(packed), "path": _dbx.ZIPPED_PATH})


# ---------------------------------------------------------------------------
# SPA catch-all — serve index.html for any non-API path so that path-based
# routing (e.g. /npc, /items) works on direct load or page refresh.
# Only active when the frontend dist folder is present (production build).
# ---------------------------------------------------------------------------
_DIST_INDEX = _ROOT / "web" / "frontend" / "dist" / "index.html"

if _DIST_INDEX.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST_INDEX.parent / "assets")), name="spa_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str, request: Request):  # noqa: ARG001
        return FileResponse(str(_DIST_INDEX))
