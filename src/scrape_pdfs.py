
import os
import time
import random
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# Latah County Idaho4 (CR29-22-2805) + Ada County restitution (CR01-24-31665)
LISTING_PAGES = [
    "https://coi.isc.idaho.gov/docs/Cases/CR29-22-2805-22.html",
    "https://coi.isc.idaho.gov/docs/Cases/CR29-22-2805-23.html",
    "https://coi.isc.idaho.gov/docs/Cases/CR29-22-2805-24.html",
    "https://coi.isc.idaho.gov/docs/Cases/CR01-24-31665-25.html",
]

OUT_DIR = os.path.join("data", "pdfs")
FAILED_LOG = "failed_downloads.log"

# Slow, polite session
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
})


def get_pdf_links_from_page(page_url: str):
    """Extract all PDF links from a single COI case page."""
    resp = session.get(page_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower():
            full_url = urljoin(page_url, href)
            label = a.get_text(strip=True) or os.path.basename(
                urlparse(full_url).path
            )
            links.append((label, full_url))
    return links


def get_all_pdf_links():
    """Extract and dedupe PDF links from all listing pages."""
    all_links = []

    for page in LISTING_PAGES:
        print(f"Scanning {page} ...")
        try:
            all_links.extend(get_pdf_links_from_page(page))
        except Exception as e:
            print(f"[ERROR] Could not read {page}: {e}")

    seen = set()
    unique = []
    for label, url in all_links:
        if url not in seen:
            seen.add(url)
            unique.append((label, url))

    return unique


def log_failure(url: str, error: str):
    with open(FAILED_LOG, "a", encoding="utf-8") as f:
        f.write(f"{url}\t{error}\n")


def download_with_retry(url: str, out_path: str, max_retries: int = 3):
    """Download a single PDF with retries + backoff, write to temp then rename."""
    tmp_path = out_path + ".part"

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, stream=True, timeout=60)
            # If server-side error, trigger retry
            if resp.status_code >= 500:
                raise requests.HTTPError(
                    f"{resp.status_code} Server Error for url: {url}"
                )

            resp.raise_for_status()

            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Basic sanity: very tiny files are probably error pages
            if os.path.getsize(tmp_path) < 2048:  # 2 KB
                raise ValueError("Downloaded file too small, likely error page")

            os.replace(tmp_path, out_path)
            return True

        except Exception as e:
            # Clean temp file if it exists
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

            if attempt < max_retries:
                wait = 3 * attempt + random.uniform(0.0, 2.0)
                print(f"  [WARN] {url} failed (attempt {attempt}/{max_retries}): {e}")
                print(f"         Retrying after {wait:.1f}s ...")
                time.sleep(wait)
            else:
                print(f"  [FAIL] {url} after {max_retries} attempts: {e}")
                log_failure(url, str(e))
                return False


def download_pdfs():
    os.makedirs(OUT_DIR, exist_ok=True)

    links = get_all_pdf_links()
    print(f"Found {len(links)} PDF links")

    for label, url in tqdm(links, desc="Downloading PDFs"):
        filename = os.path.basename(urlparse(url).path)
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        out_path = os.path.join(OUT_DIR, filename)

        if os.path.exists(out_path):
            continue  # already downloaded

        success = download_with_retry(url, out_path)

        # Be extra polite to the COI server
        # 1.5–3.5 seconds between *successful* downloads
        if success:
            time.sleep(1.5 + random.random() * 2.0)


if __name__ == "__main__":
    download_pdfs()

