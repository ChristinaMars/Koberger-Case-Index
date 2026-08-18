#!/usr/bin/env python3
"""
Scrape official Kohberger case PDFs from the Idaho Cases of Interest site.
Updated Aug 2026 for the current single-page + documentData JS structure.
"""

import os
import re
import time
import random
import argparse
from datetime import datetime
from urllib.parse import urlparse

import requests
from tqdm import tqdm

# Current live case page (Ada + Latah combined)
CASE_PAGE = "https://coi.isc.idaho.gov/docs/Cases/CR01-24-31665.html"

OUT_DIR = os.path.join("data", "pdfs")
FAILED_LOG = "failed_downloads.log"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
})


def get_all_pdf_links(since_date: str = None, new_only: bool = False):
    """
    Pull every PDF link out of the documentData JS object on the live COI page.
    Optional filters:
      - since_date: 'YYYY-MM-DD'  → only docs on/after that date
      - new_only: keep only items flagged isNew=true
    """
    print(f"Fetching {CASE_PAGE} ...")
    resp = session.get(CASE_PAGE, timeout=45)
    resp.raise_for_status()
    html = resp.text

    match = re.search(r"const documentData\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not match:
        raise RuntimeError("Could not find documentData object on page – site structure may have changed again.")

    js_blob = match.group(1)

    # Extract every document object with a simple regex (robust enough for this data)
    # Looks for blocks containing "date", "title", "link", "isNew"
    pattern = re.compile(
        r'\{\s*"date":\s*"([^"]+)"\s*,\s*"title":\s*"([^"]*)"\s*,\s*"link":\s*"([^"]+\.pdf)"\s*,\s*"isNew":\s*(true|false)',
        re.IGNORECASE
    )

    docs = []
    for m in pattern.finditer(js_blob):
        date_str, title, link, is_new = m.groups()
        docs.append({
            "date": date_str,
            "title": title.strip(),
            "link": link,
            "isNew": is_new.lower() == "true",
        })

    print(f"Raw documents found in documentData: {len(docs)}")

    # Dedupe by URL
    seen = set()
    unique = []
    for d in docs:
        if d["link"] not in seen:
            seen.add(d["link"])
            unique.append(d)

    print(f"Unique PDF links: {len(unique)}")

    # Apply filters
    if new_only:
        unique = [d for d in unique if d["isNew"]]
        print(f"After --new-only filter: {len(unique)}")

    if since_date:
        try:
            cutoff = datetime.strptime(since_date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("--since must be YYYY-MM-DD")
        filtered = []
        for d in unique:
            try:
                # dates come as MM/DD/YYYY
                doc_date = datetime.strptime(d["date"], "%m/%d/%Y").date()
                if doc_date >= cutoff:
                    filtered.append(d)
            except ValueError:
                # keep if we can't parse
                filtered.append(d)
        unique = filtered
        print(f"After --since {since_date} filter: {len(unique)}")

    # Return as (label, url) tuples for the downloader
    return [(d["title"] or os.path.basename(urlparse(d["link"]).path), d["link"]) for d in unique]


def log_failure(url: str, error: str):
    with open(FAILED_LOG, "a", encoding="utf-8") as f:
        f.write(f"{url}\t{error}\n")


def download_with_retry(url: str, out_path: str, max_retries: int = 3):
    """Download a single PDF with retries + backoff."""
    tmp_path = out_path + ".part"

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, stream=True, timeout=90)
            if resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} Server Error for url: {url}")
            resp.raise_for_status()

            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            if os.path.getsize(tmp_path) < 2048:
                raise ValueError("Downloaded file too small, likely error page")

            os.replace(tmp_path, out_path)
            return True

        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if attempt < max_retries:
                wait = 3 * attempt + random.uniform(0.0, 2.0)
                print(f"  [WARN] attempt {attempt}/{max_retries}: {e}")
                print(f"         Retrying after {wait:.1f}s ...")
                time.sleep(wait)
            else:
                print(f"  [FAIL] {url} after {max_retries} attempts: {e}")
                log_failure(url, str(e))
                return False


def download_pdfs(since_date: str = None, new_only: bool = False):
    os.makedirs(OUT_DIR, exist_ok=True)

    links = get_all_pdf_links(since_date=since_date, new_only=new_only)
    print(f"\nReady to process {len(links)} PDFs")

    downloaded = 0
    skipped = 0
    failed = 0

    for label, url in tqdm(links, desc="Downloading PDFs"):
        filename = os.path.basename(urlparse(url).path)
        # Clean up any query junk or weird encoding
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        # Make filename filesystem-safe
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)

        out_path = os.path.join(OUT_DIR, filename)

        if os.path.exists(out_path):
            skipped += 1
            continue

        success = download_with_retry(url, out_path)
        if success:
            downloaded += 1
            # Be polite
            time.sleep(1.2 + random.random() * 1.8)
        else:
            failed += 1

    print(f"\nDone. Downloaded: {downloaded}  |  Skipped (already had): {skipped}  |  Failed: {failed}")
    if failed:
        print(f"See {FAILED_LOG} for details.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Kohberger case PDFs from Idaho COI")
    parser.add_argument("--new-only", action="store_true",
                        help="Only grab documents currently flagged isNew=true")
    parser.add_argument("--since", metavar="YYYY-MM-DD",
                        help="Only grab documents dated on or after this date")
    args = parser.parse_args()

    download_pdfs(since_date=args.since, new_only=args.new_only)
