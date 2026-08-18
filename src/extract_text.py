#!/usr/bin/env python3
"""
extract_text.py
===============
Extract plain text from every PDF in data/pdfs/ into data/text/.

Improvements over the original:
- Skips files that already have a non-empty .txt counterpart
- Better progress + error reporting
- Continues on individual page failures instead of dying
- Uses pypdf (or PyPDF2 fallback) more carefully
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        print("Need pypdf or PyPDF2.  pip install pypdf")
        sys.exit(1)

PDF_DIR = Path("data") / "pdfs"
TEXT_DIR = Path("data") / "text"


def extract_one(pdf_path: Path, txt_path: Path) -> bool:
    try:
        reader = PdfReader(str(pdf_path))
        parts = []

        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
                parts.append(text)
            except Exception as e:
                parts.append(f"\n[Error extracting page {i}: {e}]\n")

        full = "\n".join(parts).strip()

        with txt_path.open("w", encoding="utf-8", errors="replace") as f:
            f.write(full)

        return True

    except Exception as e:
        print(f"  [ERROR] {pdf_path.name}: {e}")
        return False


def main() -> None:
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    if not PDF_DIR.exists():
        print(f"No PDF directory at {PDF_DIR}. Run scrape_pdfs.py first.")
        return

    pdf_files = sorted(
        f for f in PDF_DIR.iterdir() if f.suffix.lower() == ".pdf" and f.stat().st_size > 0
    )

    print(f"Found {len(pdf_files)} PDFs")

    todo = []
    skipped = 0
    for pdf in pdf_files:
        txt = TEXT_DIR / (pdf.stem + ".txt")
        if txt.exists() and txt.stat().st_size > 50:
            skipped += 1
        else:
            todo.append((pdf, txt))

    print(f"Already extracted : {skipped}")
    print(f"Need to extract   : {len(todo)}")

    if not todo:
        print("Nothing new to extract.")
        return

    ok = 0
    for i, (pdf, txt) in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {pdf.name}")
        if extract_one(pdf, txt):
            ok += 1

    print(f"\n✔️  Extracted {ok}/{len(todo)} new files → {TEXT_DIR}/")


if __name__ == "__main__":
    main()
