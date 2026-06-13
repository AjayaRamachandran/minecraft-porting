"""CLI entry point for the NPC schematic builder.

Reads ``jsons/<name>.json``, builds a 1.21.11 command-block NPC schematic into
``schematics/<name>.schem``, and writes the human-readable command listing to
``output.txt``. All generation logic lives in :mod:`builder` (shared with the
web backend).

Usage:  python main.py [name]   (default: onk)
"""

import json
import os
import sys

import builder

filename = sys.argv[1] if len(sys.argv) > 1 else "onk"

with open(f"jsons/{filename}.json", encoding="utf-8") as fh:
    data = json.load(fh)

schem, output_text = builder.build(data)

with open("output.txt", "w", encoding="utf-8") as out:
    out.write(output_text)

schem.save(os.path.join(os.getcwd(), "schematics"), filename,
           getattr(__import__("mcschematic").Version, builder.SCHEM_VERSION_NAME))

print(f"Wrote schematics/{filename}.schem and output.txt")
