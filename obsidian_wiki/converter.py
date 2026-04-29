"""Document conversion pipeline for Obsidian wiki."""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from markitdown import MarkItDown

from obsidian_wiki.images import copy_relative_images, extract_base64_images, convert_pdf_with_images
from obsidian_wiki.state import HashRegistry

logger = logging.getLogger(__name__)


@dataclass
class ConvertResult:
    """Result returned by :func:`convert_document`."""

    raw_path: Path | None = None
    source_path: Path | None = None
    is_long_doc: bool = False
    skipped: bool = False
    file_hash: str | None = None


def get_pdf_page_count(path: Path) -> int:
    """Return the number of pages in the PDF at *path* using pymupdf."""
    with pymupdf.open(str(path)) as doc:
        return doc.page_count


def convert_document(src: Path, vault_dir: Path, config: dict) -> ConvertResult:
    """Convert a document and integrate it into the Obsidian vault.

    Steps:
    1. Hash-check — skip if already known.
    2. Copy source to ``raw/`` (optional, mirrors OpenKB layout).
    3. If PDF and page count >= threshold → mark as long doc (defer to indexer).
    4. If ``.md`` — read, process relative images, save to ``sources/``.
    5. Otherwise — run MarkItDown, extract base64 images, save to ``sources/``.
    6. Register hash in the registry.
    """
    state_dir = vault_dir / ".obsidian_wiki"
    state_dir.mkdir(parents=True, exist_ok=True)
    threshold: int = config.get("pageindex_threshold", 20)
    registry = HashRegistry(state_dir / "hashes.json")

    # 1. Hash check
    file_hash = HashRegistry.hash_file(src)
    if registry.is_known(file_hash):
        logger.info("Skipping already-known file: %s", src.name)
        return ConvertResult(skipped=True)

    # 2. Copy to raw/
    raw_dir = vault_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_dest = raw_dir / src.name
    if raw_dest.resolve() != src.resolve():
        shutil.copy2(src, raw_dest)

    # 3. PDF long-doc detection
    if src.suffix.lower() == ".pdf":
        page_count = get_pdf_page_count(src)
        if page_count >= threshold:
            logger.info("Long PDF detected (%d pages >= %d threshold): %s",
                         page_count, threshold, src.name)
            return ConvertResult(raw_path=raw_dest, is_long_doc=True, file_hash=file_hash)

    # 4/5. Convert to Markdown
    sources_dir = vault_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    images_dir = vault_dir / "sources" / "images" / src.stem
    images_dir.mkdir(parents=True, exist_ok=True)

    doc_name = src.stem

    if src.suffix.lower() == ".md":
        markdown = src.read_text(encoding="utf-8")
        markdown = copy_relative_images(markdown, src.parent, doc_name, images_dir)
    elif src.suffix.lower() == ".pdf":
        markdown = convert_pdf_with_images(src, doc_name, images_dir)
    else:
        mid = MarkItDown()
        result = mid.convert(str(src))
        markdown = result.text_content
        markdown = extract_base64_images(markdown, doc_name, images_dir)

    dest_md = sources_dir / f"{doc_name}.md"
    dest_md.write_text(markdown, encoding="utf-8")

    return ConvertResult(raw_path=raw_dest, source_path=dest_md, file_hash=file_hash)
