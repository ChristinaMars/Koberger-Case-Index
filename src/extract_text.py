import os
from PyPDF2 import PdfReader

PDF_DIR = os.path.join("data", "pdfs")
TEXT_DIR = os.path.join("data", "text")


def extract_text_from_pdf(pdf_path, txt_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""

        for page in reader.pages:
            try:
                text += page.extract_text() or ""
            except Exception as e:
                text += f"\n[Error extracting page: {e}]\n"

        # Write out clean text
        with open(txt_path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(text)

    except Exception as e:
        print(f"[ERROR] Cannot process {pdf_path}: {e}")


def main():
    os.makedirs(TEXT_DIR, exist_ok=True)

    pdf_files = [
        f for f in os.listdir(PDF_DIR)
        if f.lower().endswith(".pdf")
    ]

    print(f"Found {len(pdf_files)} PDFs to extract")

    for pdf in pdf_files:
        pdf_path = os.path.join(PDF_DIR, pdf)
        txt_path = os.path.join(TEXT_DIR, pdf.replace(".pdf", ".txt"))

        print(f"Extracting {pdf} ...")
        extract_text_from_pdf(pdf_path, txt_path)

    print("\n✔️ Extraction complete!")
    print("   Text saved to data/text/")


if __name__ == "__main__":
    main()

