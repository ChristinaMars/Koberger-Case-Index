import os
import json

TEXT_DIR = os.path.join("data", "text")
OUT_PATH = os.path.join("index", "index.json")

def load_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except:
        return ""

def build_index():
    entries = []

    for filename in sorted(os.listdir(TEXT_DIR)):
        if not filename.lower().endswith(".txt"):
            continue

        full_path = os.path.join(TEXT_DIR, filename)
        text = load_text(full_path)

        preview = text[:400].replace("\n", " ").strip()

        entry = {
            "filename": filename,
            "title": os.path.splitext(filename)[0].replace("_", " "),
            "preview": preview,
            "path": full_path
        }
        entries.append(entry)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

    print(f"Index built! {len(entries)} documents indexed.")
    print(f"Saved to {OUT_PATH}")

if __name__ == "__main__":
    build_index()

