"""
Loads company knowledge (case studies + general info like services/FAQs)
from PDF/DOCX files into ChromaDB.

Folder structure expected:
  knowledge_base/case_studies/<category>_<anything>.pdf|docx
    - filename prefix (before first underscore) must match a valid
      ServiceCategory value, e.g. "web-development_retail-site.pdf"
  knowledge_base/general/<anything>.pdf|docx
    - services overview, FAQs, about-us, etc. (no category needed)

Run: python scripts/load_knowledge_base.py
"""
import sys
import os
import hashlib
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pypdf import PdfReader
from docx import Document as DocxDocument

from app.rag.chroma_client import get_knowledge_collection

VALID_CATEGORIES = {
    "web-development",
    "web-design",
    "graphic-design",
    "ai-automation",
    "custom-software",
}

CHUNK_SIZE = 1200  # characters per chunk
CHUNK_OVERLAP = 150

KB_ROOT = Path(__file__).parent.parent / "knowledge_base"
CASE_STUDIES_DIR = KB_ROOT / "case_studies"
GENERAL_DIR = KB_ROOT / "general"


def extract_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text_from_docx(path: Path) -> str:
    doc = DocxDocument(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return extract_text_from_pdf(path)
    elif path.suffix.lower() == ".docx":
        return extract_text_from_docx(path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Simple character-based chunking with overlap, splitting on paragraph boundaries where possible."""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk.strip())
        start = end - overlap
    return [c for c in chunks if c]


def make_id(source: str, chunk_index: int) -> str:
    digest = hashlib.sha256(f"{source}_{chunk_index}".encode()).hexdigest()[:16]
    return f"kb_{digest}"


def load_case_studies(collection):
    if not CASE_STUDIES_DIR.exists():
        print(f"No case_studies folder found at {CASE_STUDIES_DIR}, skipping.")
        return

    files = [f for f in CASE_STUDIES_DIR.iterdir() if f.suffix.lower() in (".pdf", ".docx")]
    if not files:
        print("No case study files found.")
        return

    documents, ids, metadatas = [], [], []

    for file in files:
        category = file.stem.split("_")[0]
        if category not in VALID_CATEGORIES:
            print(f"⚠️  Skipping '{file.name}' — filename prefix '{category}' is not a valid category. "
                  f"Valid: {', '.join(sorted(VALID_CATEGORIES))}")
            continue

        try:
            text = extract_text(file)
        except Exception as e:
            print(f"❌ Failed to extract text from '{file.name}': {e}")
            continue

        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            documents.append(chunk)
            ids.append(make_id(file.name, i))
            metadatas.append({"category": category, "type": "case_study", "source": file.name})

        print(f"✅ Loaded '{file.name}' → category: {category}, chunks: {len(chunks)}")

    if documents:
        collection.upsert(documents=documents, ids=ids, metadatas=metadatas)


def load_general_knowledge(collection):
    if not GENERAL_DIR.exists():
        print(f"No general folder found at {GENERAL_DIR}, skipping.")
        return

    files = [f for f in GENERAL_DIR.iterdir() if f.suffix.lower() in (".pdf", ".docx")]
    if not files:
        print("No general knowledge files found.")
        return

    documents, ids, metadatas = [], [], []

    for file in files:
        try:
            text = extract_text(file)
        except Exception as e:
            print(f"❌ Failed to extract text from '{file.name}': {e}")
            continue

        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            documents.append(chunk)
            ids.append(make_id(file.name, i))
            metadatas.append({"type": "knowledge", "source": file.name})

        print(f"✅ Loaded '{file.name}' → chunks: {len(chunks)}")

    if documents:
        collection.upsert(documents=documents, ids=ids, metadatas=metadatas)


def main():
    collection = get_knowledge_collection()
    print("--- Loading case studies ---")
    load_case_studies(collection)
    print("\n--- Loading general knowledge (services/FAQs) ---")
    load_general_knowledge(collection)
    print(f"\nDone. Total documents in collection: {collection.count()}")


if __name__ == "__main__":
    main()