"""Local in-memory OCR fallback, only for primary-extraction OCR-required PDFs."""
from pathlib import Path
from uuid import UUID
import math
import os
from contextlib import redirect_stderr

import pymupdf

from app.schemas.cv_extraction import MAX_TEXT_CHARS, ExtractedCvDocument
from app.schemas.cv_ocr import OcrCvDocument, OcrPageText
from app.services.cv_extraction import (
    CvExtractionService, MIN_PDF_ALNUM, MIN_PAGE_ALNUM, MIN_MEANINGFUL_PAGE_RATIO,
    alnum_count, normalize_text, pdf_access,
)

OCR_DPI = 300
MAX_OCR_PAGES = 25
MAX_OCR_BATCH_PAGES = 100
MAX_OCR_PAGE_PIXELS = 25_000_000


class OcrNotConfigured(Exception):
    def __init__(self):
        super().__init__("OCR processing is not configured.")


def resolve_tessdata(configured: Path | None) -> Path:
    """Resolve lazily; discovery output/path errors never leave this boundary."""
    try:
        directory = Path(configured if configured is not None else pymupdf.get_tessdata()).resolve()
        english = directory / "eng.traineddata"
        if not directory.is_dir() or not english.is_file() or english.stat().st_size == 0:
            raise ValueError("English OCR data unavailable")
        with english.open("rb") as stream:
            stream.read(1)
        return directory
    except Exception:
        raise OcrNotConfigured() from None


def ocr_page_text(page, tessdata: Path) -> str:
    # Native Tesseract can write paths directly to stderr, bypassing Python logs.
    # Called only while holding shared pdf_access(); restore stderr immediately.
    with open(os.devnull, "w") as sink:
        saved_stderr = os.dup(2)
        try:
            os.dup2(sink.fileno(), 2)
            with redirect_stderr(sink):
                textpage = page.get_textpage_ocr(language="eng", dpi=OCR_DPI, full=True, tessdata=str(tessdata))
                return page.get_text("text", textpage=textpage, sort=True)
        finally:
            os.dup2(saved_stderr, 2)
            os.close(saved_stderr)


class CvOcrService:
    def __init__(self, storage_root: Path, tessdata_path: Path | None = None):
        self.extraction = CvExtractionService(storage_root)
        self.tessdata_path = tessdata_path

    def process_batch(self, job_reference: str, batch_id: UUID) -> tuple[OcrCvDocument, ...]:
        extracted = self.extraction.extract_batch_with_paths(job_reference, batch_id)
        return self.process_extracted(extracted)

    def process_extracted(self, extracted: tuple[tuple[Path, ExtractedCvDocument], ...]) -> tuple[OcrCvDocument, ...]:
        """Reuse freshly validated extraction within a request; no evidence persistence."""
        eligible = [(path, document) for path, document in extracted
            if document.file_type == "pdf" and document.extraction_status == "ocr_required"]
        if not eligible:
            return ()
        tessdata = resolve_tessdata(self.tessdata_path)
        results, remaining = [], MAX_OCR_BATCH_PAGES
        for path, primary in eligible:
            pages = len(primary.source_units)
            if pages > MAX_OCR_PAGES or pages > remaining:
                results.append(self._failed(primary))
                continue
            remaining -= pages
            results.append(self._ocr_document(path, primary, tessdata))
        return tuple(results)

    @staticmethod
    def _failed(primary: ExtractedCvDocument, attempted_pages: int = 0) -> OcrCvDocument:
        return OcrCvDocument(upload_id=primary.upload_id, ocr_status="ocr_failed", text="",
            text_char_count=0, page_count=len(primary.source_units), ocr_page_count=attempted_pages, source_units=())

    def _ocr_document(self, path: Path, primary: ExtractedCvDocument, tessdata: Path) -> OcrCvDocument:
        attempted = 0
        try:
            low_pages = {unit.page_number for unit in primary.source_units if alnum_count(unit.text) < MIN_PAGE_ALNUM}
            # A short document can fail the total threshold despite every page passing 20.
            selected = low_pages or {unit.page_number for unit in primary.source_units}
            units, chars = [], 0
            with pdf_access(), pymupdf.open(path) as document:
                if document.needs_pass or document.page_count != len(primary.source_units):
                    raise ValueError("PDF changed or unavailable")
                for page, digital in zip(document, primary.source_units):
                    method, text = "digital", digital.text
                    if digital.page_number in selected:
                        pixels = math.ceil(page.rect.width * OCR_DPI / 72) * math.ceil(page.rect.height * OCR_DPI / 72)
                        if not 0 < pixels <= MAX_OCR_PAGE_PIXELS:
                            raise ValueError("OCR render limit")
                        attempted += 1
                        text, method = normalize_text(ocr_page_text(page, tessdata)), "ocr"
                    chars += len(text) + (2 if units else 0)
                    if chars > MAX_TEXT_CHARS:
                        raise ValueError("OCR text limit")
                    units.append(OcrPageText(page_number=digital.page_number, text=text, source_method=method))
            text = "\n\n".join(unit.text for unit in units)
            recognized = [unit for unit in units if unit.source_method == "ocr"]
            sufficient = (sum(alnum_count(unit.text) for unit in units) >= MIN_PDF_ALNUM
                and sum(alnum_count(unit.text) >= MIN_PAGE_ALNUM for unit in units) / len(units) >= MIN_MEANINGFUL_PAGE_RATIO
                and any(alnum_count(unit.text) >= MIN_PAGE_ALNUM for unit in recognized))
            if not sufficient:
                return self._failed(primary, attempted)
            return OcrCvDocument(upload_id=primary.upload_id, ocr_status="ocr_extracted", text=text,
                text_char_count=len(text), page_count=len(units), ocr_page_count=attempted, source_units=tuple(units))
        except Exception:
            return self._failed(primary, attempted)
