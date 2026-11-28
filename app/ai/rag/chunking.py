import importlib
import io
import zipfile
from xml.etree import ElementTree


def extract_text_from_bytes(filename: str, content_type: str, raw_bytes: bytes) -> str:
    """Extract UTF-8 text from supported policy/knowledge files (.txt, .md, .csv, .json, .docx, optional .pdf)."""
    lower_name = (filename or "").lower()
    lower_type = (content_type or "").lower()

    if lower_name.endswith(".docx") or "wordprocessingml" in lower_type:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            if "word/document.xml" not in zf.namelist():
                raise ValueError("Invalid DOCX file: missing word/document.xml.")
            xml_bytes = zf.read("word/document.xml")
        root = ElementTree.fromstring(xml_bytes)
        paragraphs: list[str] = []
        for para in root.iter():
            if para.tag.endswith("}p"):
                texts = [node.text for node in para.iter() if node.tag.endswith("}t") and node.text]
                if texts:
                    paragraphs.append("".join(texts))
        return "\n".join(paragraphs).strip()

    if lower_name.endswith(".pdf") or "pdf" in lower_type:
        try:
            pypdf = importlib.import_module("pypdf")
        except ImportError as exc:
            raise ValueError(
                "PDF extraction requires 'pypdf'. Upload .txt, .md, .csv, .json, or .docx, or install pypdf."
            ) from exc
        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(p.strip() for p in pages if p.strip()).strip()

    if (
        lower_name.endswith((".txt", ".md", ".csv", ".json"))
        or lower_type.startswith("text/")
        or "json" in lower_type
    ):
        return raw_bytes.decode("utf-8", errors="replace").strip()

    raise ValueError(f"Unsupported document format for '{filename}'.")


def chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """Split text into overlapping chunks without breaking short paragraphs unnecessarily."""
    cleaned = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    step_floor = max(100, chunk_size - overlap)

    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        if end < len(cleaned):
            split_at = cleaned.rfind("\n\n", start + step_floor // 2, end)
            if split_at == -1:
                split_at = cleaned.rfind(". ", start + step_floor // 2, end)
            if split_at == -1:
                split_at = cleaned.rfind(" ", start + step_floor // 2, end)
            if split_at > start:
                end = split_at + 1

        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)

        if end >= len(cleaned):
            break
        start = max(start + 1, end - overlap)

    return chunks


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
