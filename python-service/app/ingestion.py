from dataclasses import asdict, dataclass
from pathlib import Path
import re
import json


# Locate the project root regardless of the terminal's working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_FILE = PROCESSED_DIR / "chunks.jsonl"

SUPPORTED_EXTENSIONS = {".md", ".txt"}


@dataclass
class DocumentChunk:
    chunk_id: str
    source: str
    chunk_index: int
    text: str


def clean_text(text: str) -> str:
    """Normalize whitespace while preserving paragraph boundaries."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_documents(
    documents_dir: Path = DOCUMENTS_DIR,
) -> list[dict[str, str]]:
    """Load supported text documents from a directory."""
    if not documents_dir.exists():
        raise FileNotFoundError(
            f"Documents directory not found: {documents_dir}"
        )

    documents = []

    for path in sorted(documents_dir.rglob("*")):
        if not path.is_file():
            continue

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        content = path.read_text(encoding="utf-8-sig")
        content = clean_text(content)

        if not content:
            continue

        documents.append(
            {
                "source": path.name,
                "text": content,
            }
        )

    return documents


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[str]:
    """
    Split text into overlapping character-based chunks.

    chunk_size and overlap are measured in characters, not tokens.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than chunk_size"
        )

    text = clean_text(text)

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Prefer ending at a word boundary when possible.
        if end < len(text):
            boundary = text.rfind(" ", start + chunk_size // 2, end)

            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        # Move backward to preserve context between neighboring chunks.
        start = max(end - overlap, start + 1)

    return chunks


def ingest_documents(
    documents_dir: Path = DOCUMENTS_DIR,
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[DocumentChunk]:
    """Load documents and produce chunks with source metadata."""
    documents = load_documents(documents_dir)
    results: list[DocumentChunk] = []

    for document in documents:
        source = document["source"]
        chunks = chunk_text(
            document["text"],
            chunk_size=chunk_size,
            overlap=overlap,
        )

        for index, chunk in enumerate(chunks):
            results.append(
                DocumentChunk(
                    chunk_id=f"{source}::chunk-{index:04d}",
                    source=source,
                    chunk_index=index,
                    text=chunk,
                )
            )

    return results

def save_chunks(
    chunks: list[DocumentChunk],
    output_file: Path = OUTPUT_FILE,
) -> None:
    """Save chunks as JSON Lines, one JSON object per line."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as file:
        for chunk in chunks:
            file.write(
                json.dumps(asdict(chunk), ensure_ascii=False) + "\n"
            )


if __name__ == "__main__":
    chunks = ingest_documents()
    save_chunks(chunks)

    print(f"Project root: {PROJECT_ROOT}")
    print(f"Documents directory: {DOCUMENTS_DIR}")
    print(f"Chunks generated: {len(chunks)}")
    print(f"Output saved to: {OUTPUT_FILE}")

    for chunk in chunks:
        print(f"\n[{chunk.chunk_id}]")
        print(f"Source: {chunk.source}")
        print(f"Characters: {len(chunk.text)}")
        print(f"Preview: {chunk.text[:150]}...")