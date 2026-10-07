"""Private OCR evidence; public contracts contain operational metadata only."""
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.cv_extraction import MAX_TEXT_CHARS, ExtractionContract, PdfPageText
from app.schemas.cv_upload import JobReference


class OcrPageText(PdfPageText):
    source_method: Literal["digital", "ocr"]


class CvOcrItem(ExtractionContract):
    upload_id: UUID
    ocr_status: Literal["ocr_extracted", "ocr_failed"]
    text_char_count: int = Field(ge=0, le=MAX_TEXT_CHARS)
    page_count: int = Field(ge=1, le=200)
    ocr_page_count: int = Field(ge=0, le=25)

    @model_validator(mode="after")
    def valid_counts(self):
        if self.ocr_page_count > self.page_count:
            raise ValueError("OCR count cannot exceed page count.")
        return self


class OcrCvDocument(CvOcrItem):
    text: str = Field(max_length=MAX_TEXT_CHARS, repr=False)
    source_units: tuple[OcrPageText, ...] = Field(max_length=25, repr=False)

    @model_validator(mode="after")
    def consistent_evidence(self):
        if self.text != "\n\n".join(unit.text for unit in self.source_units) or len(self.text) != self.text_char_count:
            raise ValueError("Text must match ordered evidence.")
        if self.source_units and [unit.page_number for unit in self.source_units] != list(range(1, self.page_count + 1)):
            raise ValueError("Page evidence must preserve document order.")
        if self.ocr_status == "ocr_extracted" and (not self.source_units or not self.text or self.ocr_page_count == 0):
            raise ValueError("Successful OCR must contain page evidence.")
        return self

    def public_metadata(self) -> CvOcrItem:
        return CvOcrItem(**{name: getattr(self, name) for name in CvOcrItem.model_fields})


class CvOcrResponse(ExtractionContract):
    status: Literal["processed"] = "processed"
    job_reference: JobReference
    batch_id: UUID
    attempted_count: int = Field(ge=0, le=20)
    files: tuple[CvOcrItem, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def consistent_count(self):
        if self.attempted_count != len(self.files):
            raise ValueError("Attempted count must match file metadata.")
        return self
