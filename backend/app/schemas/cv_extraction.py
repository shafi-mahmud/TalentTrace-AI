"""Private extraction evidence and separate content-free public metadata."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.cv_upload import JobReference

MAX_TEXT_CHARS = 500_000
MAX_SOURCE_UNITS = 10_000
ExtractionStatus = Literal["text_extracted", "ocr_required", "extraction_failed"]


class ExtractionContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class PdfPageText(ExtractionContract):
    page_number: int = Field(ge=1, le=200)
    text: str = Field(max_length=MAX_TEXT_CHARS, repr=False)


class DocxTextBlock(ExtractionContract):
    block_index: int = Field(ge=1, le=MAX_SOURCE_UNITS)
    block_type: Literal["paragraph", "table_cell"]
    text: str = Field(max_length=MAX_TEXT_CHARS, repr=False)


class ExtractedCvDocument(ExtractionContract):
    upload_id: UUID
    file_type: Literal["pdf", "docx"]
    extraction_status: ExtractionStatus
    text: str = Field(max_length=MAX_TEXT_CHARS, repr=False)
    text_char_count: int = Field(ge=0, le=MAX_TEXT_CHARS)
    source_units: tuple[PdfPageText | DocxTextBlock, ...] = Field(max_length=MAX_SOURCE_UNITS, repr=False)

    @model_validator(mode="after")
    def consistent_evidence(self):
        unit_type = PdfPageText if self.file_type == "pdf" else DocxTextBlock
        if any(not isinstance(unit, unit_type) for unit in self.source_units):
            raise ValueError("Source units must match the document type.")
        if self.text != "\n\n".join(unit.text for unit in self.source_units) or self.text_char_count != len(self.text):
            raise ValueError("Text must match its ordered source evidence.")
        if self.file_type == "docx" and self.extraction_status == "ocr_required":
            raise ValueError("DOCX is not routed to OCR.")
        return self

    def public_metadata(self) -> "CvExtractionItem":
        return CvExtractionItem(upload_id=self.upload_id, file_type=self.file_type,
            extraction_status=self.extraction_status, text_char_count=self.text_char_count,
            source_unit_count=len(self.source_units), ocr_recommended=self.extraction_status == "ocr_required")


class CvExtractionItem(ExtractionContract):
    upload_id: UUID
    file_type: Literal["pdf", "docx"]
    extraction_status: ExtractionStatus
    text_char_count: int = Field(ge=0, le=MAX_TEXT_CHARS)
    source_unit_count: int = Field(ge=0, le=MAX_SOURCE_UNITS)
    ocr_recommended: bool


class CvExtractionResponse(ExtractionContract):
    status: Literal["processed"] = "processed"
    job_reference: JobReference
    batch_id: UUID
    processed_count: int = Field(ge=1, le=20)
    files: tuple[CvExtractionItem, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def consistent_count(self):
        if self.processed_count != len(self.files):
            raise ValueError("Processed count must match file metadata.")
        return self
