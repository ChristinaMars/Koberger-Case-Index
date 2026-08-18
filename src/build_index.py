#!/usr/bin/env python3
"""
build_index.py
==============
Build a simple searchable JSON index of every extracted text file.
"""

from __future__ import annotations

import json
from pathlib import Path

TEXT_DIR = Path("data") / "text"
OUT_PATH = Path("index") / "index.json"


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def build_index() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not TEXT_DIR.exists():
        print(f"No text directory at {TEXT_DIR}. Run extract_text.py first.")
        return

    entries = []
    for txt_path in sorted(TEXT_DIR.glob("*.txt")):
        text = load_text(txt_path)
        preview = text[:450].replace("\n", " ").strip()

        entries.append(
            {
                "filename": txt_path.name,
                "title": txt_path.stem.replace("_", " ").replace("+", " "),
                "preview": preview,
                "chars": len(text),
                "path": str(txt_path),
            }
        )

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    print(f"Index built → {OUT_PATH}")
    print(f"Documents indexed: {len(entries)}")


if __name__ == "__main__":
    build_index()
