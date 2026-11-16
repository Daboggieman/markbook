"""Dump the OpenAPI schema for the TS client codegen (Phase 6).

Usage (from apps/api): .venv/Scripts/python.exe scripts/dump_openapi.py
Writes ../../packages/api-client/openapi.json.

The generated package (@markbook/api-client) is the only place the web app
learns endpoint shapes — no hand-written API types. CI's breaking-change
check (05-testing-strategy.md) can diff this dump against the published one.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from app.main import create_app  # noqa: E402


def main() -> None:
    schema = create_app().openapi()
    out = Path(__file__).parents[3] / "packages" / "api-client" / "openapi.json"
    out.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"wrote {out} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
