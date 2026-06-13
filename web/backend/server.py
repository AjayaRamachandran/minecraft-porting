"""FastAPI backend for the Minecraft converter web UI."""
from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Locate converter package relative to web/backend/
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "convert_villager"))
sys.path.insert(0, str(_ROOT / "npc-maker"))

from converter.cli import build_pipeline, process_mcfunction_file  # noqa: E402
from converter.implementors import schematic_file  # noqa: E402
import builder as npc_builder  # noqa: E402  (npc-maker/builder.py)

PACK_DIR = _ROOT / "1_21_11_pack"
OLD_PACK_DIR = _ROOT / "1_20_1_pack"

app = FastAPI(title="MC Converter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "pack": str(PACK_DIR), "old_pack": str(OLD_PACK_DIR)}


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
