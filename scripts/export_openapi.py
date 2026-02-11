#!/usr/bin/env python3
"""
Export the FastAPI OpenAPI schema to a JSON file.
Run from the plimate-server directory:
  poetry run python scripts/export_openapi.py
  PYTHONPATH=. python scripts/export_openapi.py -o openapi.json
Output defaults to openapi.json; use -o/--output to set a path.
"""
import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on path when running script directly
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export OpenAPI schema to JSON")
    parser.add_argument(
        "-o",
        "--output",
        default="openapi.json",
        help="Output JSON file path (default: openapi.json)",
    )
    args = parser.parse_args()

    schema = app.openapi()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print(f"Exported OpenAPI schema to {out_path.absolute()}")


if __name__ == "__main__":
    main()
