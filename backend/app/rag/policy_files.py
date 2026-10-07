"""Bounded local policy extraction, independent of databases and ML providers."""

from __future__ import annotations

import io
import logging
import stat
from contextlib import contextmanager
from pathlib import Path
from zipfile import ZipFile

from app.rag.contracts import MAX_POLICY_TEXT_LENGTH, _normalize_policy_text


SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt", ".md"})
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_PDF_STREAM_BYTES = 8 * 1024 * 1024
MAX_DOCX_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_DOCX_ENTRIES = 2048


class PolicyFileError(ValueError):
    """Controlled extraction failure containing no file path or document text."""


@contextmanager
def _quiet_parser():
    # Local parsers can include document details in diagnostics. This is a
    # synchronous local/preload tool, not a concurrently serving upload endpoint.
    original = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        yield
    finally:
        logging.disable(original)


def _join_text(parts) -> str:
    collected = []
    length = 0
    for part in parts:
        if not part:
            continue
        length += len(part) + (2 if collected else 0)
        if length > MAX_POLICY_TEXT_LENGTH:
            raise PolicyFileError("Extracted policy text exceeds the supported limit.")
        collected.append(part)
    return "\n\n".join(collected)


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader, apply_configuration

    try:
        with _quiet_parser(), apply_configuration(
            maximum_declared_stream_length=MAX_PDF_STREAM_BYTES,
            array_based_stream_maximum_output_length=MAX_PDF_STREAM_BYTES,
            zlib_maximum_output_length=MAX_PDF_STREAM_BYTES,
            lzw_maximum_output_length=MAX_PDF_STREAM_BYTES,
            run_length_maximum_output_length=MAX_PDF_STREAM_BYTES,
            page_tree_maximum_entries=MAX_PDF_PAGES + 1,
            xform_maximum_invocations_per_extraction=1000,
            jbig2dec_binary=None,
        ):
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted and not reader.decrypt(""):
                raise PolicyFileError("Password-protected PDFs are not supported.")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise PolicyFileError("PDF exceeds the supported page limit.")
            text = _join_text(page.extract_text() or "" for page in reader.pages)
    except PolicyFileError:
        raise
    except Exception:
        raise PolicyFileError("PDF could not be read safely.") from None
    if not text.strip():
        raise PolicyFileError(
            "PDF has no extractable text. Scanned/image-only PDFs require OCR, which is not implemented."
        )
    return text


def _extract_docx(data: bytes) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        # Bound the expanded archive before python-docx reads its XML parts.
        with ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (len(entries) > MAX_DOCX_ENTRIES
                    or sum(item.file_size for item in entries) > MAX_DOCX_EXPANDED_BYTES):
                raise PolicyFileError("DOCX archive exceeds the supported expansion limit.")
            if any(item.flag_bits & 1 or item.filename.lower().endswith("vbaproject.bin") for item in entries):
                raise PolicyFileError("Encrypted or macro-containing DOCX files are not supported.")
        with _quiet_parser():
            document = Document(io.BytesIO(data))

            def blocks():
                for block in document.iter_inner_content():
                    if isinstance(block, Paragraph):
                        value = block.text
                        # Map standard Word heading styles to the chunker's
                        # existing Markdown syntax; retain document block order.
                        style = block.style.name if block.style else ""
                        if style.startswith("Heading ") and style[8:].isdigit():
                            level = int(style[8:])
                            if 1 <= level <= 6 and value.strip():
                                value = "#" * level + " " + value.strip()
                        yield value
                    elif isinstance(block, Table):
                        for row in block.rows:
                            # Merged cells may appear repeatedly in a row.
                            seen = set()
                            values = []
                            for cell in row.cells:
                                if cell._tc not in seen:
                                    seen.add(cell._tc)
                                    values.append(cell.text)
                            if any(value.strip() for value in values):
                                yield " | ".join(values)
            return _join_text(blocks())
    except PolicyFileError:
        raise
    except Exception:
        raise PolicyFileError("DOCX could not be read safely.") from None


def extract_policy_text(file: str | Path) -> str:
    """Read one explicit regular local file; never copy it or follow resources."""
    try:
        path = Path(file)
        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise PolicyFileError("Supported policy formats are PDF, DOCX, TXT and Markdown.")
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise PolicyFileError("Policy input must be a regular file.")
        if info.st_size == 0:
            raise PolicyFileError("Policy file is empty.")
        if info.st_size > MAX_FILE_BYTES:
            raise PolicyFileError("Policy file exceeds the 5 MiB size limit.")
        # Bound the read as well, in case the file grows after the size check.
        with path.open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise PolicyFileError("Policy file exceeds the 5 MiB size limit.")
    except PolicyFileError:
        raise
    except (OSError, ValueError, TypeError):
        raise PolicyFileError("Policy file could not be opened safely.") from None

    if extension == ".pdf":
        text = _extract_pdf(data)
    elif extension == ".docx":
        text = _extract_docx(data)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise PolicyFileError("Text policy files must use UTF-8 encoding.") from None
    if len(text) > MAX_POLICY_TEXT_LENGTH:
        raise PolicyFileError("Extracted policy text exceeds the supported limit.")
    text = _normalize_policy_text(text)
    if not text:
        raise PolicyFileError("Policy has no meaningful extractable text.")
    if len(text) > MAX_POLICY_TEXT_LENGTH:
        raise PolicyFileError("Extracted policy text exceeds the supported limit.")
    return text
