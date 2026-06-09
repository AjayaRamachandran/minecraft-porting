"""FastAPI backend for the Minecraft converter web UI."""
from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Locate converter package relative to web/backend/
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "convert_villager"))

from converter.cli import build_pipeline, process_mcfunction_file  # noqa: E402
from converter.implementors import schematic_file  # noqa: E402

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
