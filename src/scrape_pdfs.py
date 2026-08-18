#!/usr/bin/env python3
"""
scrape_pdfs.py
==============
Updated scraper for the Idaho Cases of Interest redesign (2025/2026).

Official source:
  https://coi.isc.idaho.gov/docs/Cases/CR01-24-31665.html

The page embeds a large JavaScript object (`documentData`) containing every
public PDF for both Latah County CR29-22-2805 and Ada County CR01-24-31665.
This script parses that object, downloads any PDFs that are not already present
in data/pdfs/, and is polite to the court server.

Usage:
  python src/scrape_pdfs.py
  python src/scrape_pdfs.py --new-only          # only docs marked isNew=true
  python src/scrape_pdfs.py --since 2025-07-01  # only docs on/after this date
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COI_URL = "https://coi.isc.idaho.gov/docs/Cases/CR01-24-31665.html"

OUT_DIR = Path("data") / "pdfs"
FAILED_LOG = Path("failed_downloads.log")
NEW_LOG = Path("new_downloads.log")

# Polite defaults
MIN_DELAY = 1.4
MAX_DELAY = 3.2
MAX_RETRIES = 4
TIMEOUT = 60

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

session = requests.Session()
session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://coi.isc.idaho.gov/",
    }
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log_line(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def sanitize_filename(name: str) -> str:
    """Make a filesystem-safe filename while keeping it readable."""
    name = unquote(name)
    # Replace common problematic characters
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    # Keep length reasonable
    if len(name) > 180:
        stem, ext = os.path.splitext(name)
        name = stem[:160] + ext
    return name


def filename_from_url(url: str) -> str:
    path = urlparse(url).path
    base = os.path.basename(path)
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return sanitize_filename(base)


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse MM/DD/YYYY. Returns None on failure."""
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y")
    except Exception:
        return None


def extract_documents(html: str) -> List[dict]:
    """
    Pull every document entry out of the embedded documentData object.
    Falls back to a simpler regex if the primary pattern misses anything.
    """
    pattern = (
        r'\{\s*"date":\s*"([^"]+)",\s*"title":\s*"([^"]+)",'
        r'\s*"link":\s*"([^"]+)",\s*"isNew":\s*(true|false),'
        r'\s*"fileType":\s*"([^"]+)"\s*\}'
    )
    matches = re.findall(pattern, html)

    docs = []
    seen_urls = set()

    for date, title, link, is_new, file_type in matches:
        if file_type.upper() != "PDF":
            continue
        if link in seen_urls:
            continue
        seen_urls.add(link)

        docs.append(
            {
                "date": date,
                "title": title.strip(),
                "url": link,
                "is_new": is_new == "true",
                "filename": filename_from_url(link),
            }
        )

    # Fallback: catch any PDF links the structured parse might have missed
    for m in re.finditer(
        r'https://coi\.isc\.idaho\.gov/docs/[^"\s]+\.pdf',
        html,
        re.IGNORECASE,
    ):
        url = m.group(0)
        if url not in seen_urls:
            seen_urls.add(url)
            docs.append(
                {
                    "date": "UNKNOWN",
                    "title": os.path.basename(urlparse(url).path),
                    "url": url,
                    "is_new": False,
                    "filename": filename_from_url(url),
                }
            )

    return docs


def download_with_retry(url: str, out_path: Path) -> bool:
    """Download one PDF with retries + exponential-ish backoff."""
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, stream=True, timeout=TIMEOUT)

            if resp.status_code >= 500:
                raise requests.HTTPError(
                    f"{resp.status_code} Server Error for url: {url}"
                )
            if resp.status_code == 404:
                print(f"  [404] {url}")
                log_line(FAILED_LOG, f"{url}\t404 Not Found")
                return False

            resp.raise_for_status()

            with tmp_path.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            size = tmp_path.stat().st_size
            if size < 1500:  # almost certainly an error page
                raise ValueError(f"File too small ({size} bytes) – likely error page")

            tmp_path.replace(out_path)
            return True

        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

            if attempt < MAX_RETRIES:
                wait = (2 ** attempt) + random.uniform(0.5, 2.0)
                print(f"  [WARN] attempt {attempt}/{MAX_RETRIES} failed: {e}")
                print(f"         retrying in {wait:.1f}s ...")
                time.sleep(wait)
            else:
                print(f"  [FAIL] {url} after {MAX_RETRIES} attempts: {e}")
                log_line(FAILED_LOG, f"{url}\t{e}")
                return False

    return False


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------


def fetch_page() -> str:
    print(f"Fetching {COI_URL} ...")
    resp = session.get(COI_URL, timeout=30)
    resp.raise_for_status()
    return resp.text


def run(
    new_only: bool = False,
    since: Optional[str] = None,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    html = fetch_page()
    docs = extract_documents(html)
    print(f"Parsed {len(docs)} PDF entries from COI page")

    # Optional filters
    if new_only:
        docs = [d for d in docs if d["is_new"]]
        print(f"Filtered to isNew=true → {len(docs)} docs")

    if since:
        cutoff = datetime.strptime(since, "%Y-%m-%d")
        filtered = []
        for d in docs:
            dt = parse_date(d["date"])
            if dt is None or dt >= cutoff:
                filtered.append(d)
        docs = filtered
        print(f"Filtered to date >= {since} → {len(docs)} docs")

    # Deduplicate by final local filename (rare collisions)
    seen_names: dict[str, str] = {}
    unique_docs = []
    for d in docs:
        name = d["filename"]
        if name in seen_names:
            # collision – append short hash of URL
            h = hashlib.md5(d["url"].encode()).hexdigest()[:6]
            stem, ext = os.path.splitext(name)
            name = f"{stem}_{h}{ext}"
            d = dict(d, filename=name)
        seen_names[name] = d["url"]
        unique_docs.append(d)

    already = 0
    to_download = []
    for d in unique_docs:
        out_path = OUT_DIR / d["filename"]
        if out_path.exists() and out_path.stat().st_size > 1500:
            already += 1
        else:
            to_download.append(d)

    print(f"Already on disk : {already}")
    print(f"Need to download: {len(to_download)}")

    if not to_download:
        print("Nothing new to grab. All caught up.")
        return

    success = 0
    for d in tqdm(to_download, desc="Downloading PDFs"):
        out_path = OUT_DIR / d["filename"]
        print(f"\n→ {d['date']}  {d['title'][:80]}")
        print(f"  {d['url']}")

        ok = download_with_retry(d["url"], out_path)
        if ok:
            success += 1
            log_line(
                NEW_LOG,
                f"{datetime.now().isoformat()}\t{d['date']}\t{d['title']}\t{d['filename']}\t{d['url']}",
            )
            # polite pause only on success
            time.sleep(MIN_DELAY + random.random() * (MAX_DELAY - MIN_DELAY))

    print(f"\nDone. Successfully downloaded {success}/{len(to_download)} new PDFs.")
    if success:
        print(f"New files logged to {NEW_LOG}")
        print("Next: run  python src/extract_text.py  then  python src/build_index.py")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape official Kohberger case PDFs from Idaho COI"
    )
    parser.add_argument(
        "--new-only",
        action="store_true",
        help="Only download documents currently flagged isNew=true on the COI page",
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Only download documents dated on or after this date",
    )
    args = parser.parse_args()

    run(new_only=args.new_only, since=args.since)


if __name__ == "__main__":
    main()
