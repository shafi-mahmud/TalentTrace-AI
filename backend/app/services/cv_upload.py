"""Deterministic, bounded filesystem intake. No extraction or external calls."""
from pathlib import Path, PurePosixPath
import re
import shutil
import unicodedata
from uuid import uuid4
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

from starlette.datastructures import UploadFile

from app.core.config import REPOSITORY_ROOT
from app.schemas.cv_upload import CvBatchInput, CvUploadItem, CvUploadResponse

MAX_FILES = 20
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_BATCH_BYTES = 100 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
PUBLIC_ERRORS = {
    "invalid_job_reference": "Enter a valid TT-JOB reference.",
    "invalid_batch": "Select between 1 and 20 PDF/DOCX files.",
    "unsupported_file_type": "Only PDF and DOCX files with compatible content types are supported.",
    "invalid_filename": "An uploaded filename is not permitted.",
    "invalid_file_signature": "An uploaded file does not match its declared document type.",
    "malformed_docx": "An uploaded DOCX package is invalid or exceeds safe package limits.",
    "file_too_large": "An uploaded file exceeds the 10 MiB limit.",
    "batch_too_large": "The upload exceeds the permitted batch/request size.",
    "invalid_multipart": "Supply a multipart form with one Job Reference and files only.",
    "storage_failed": "CV intake could not store the batch. No upload was confirmed.",
}


class CvUploadError(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(PUBLIC_ERRORS[code])


def document_type(upload: UploadFile) -> str:
    name = upload.filename or ""
    if not name or len(name) > 255 or any(c in name for c in "/\\:") or any(
        unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in name
    ):
        raise CvUploadError("invalid_filename")
    extension = Path(name).suffix.lower()
    allowed = {
        ".pdf": {"application/pdf", "application/octet-stream"},
        ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream"},
    }
    if extension not in allowed or (upload.content_type or "").lower() not in allowed[extension]:
        raise CvUploadError("unsupported_file_type", 415)
    return extension[1:]


def validate_document(path: Path, file_type: str) -> None:
    if file_type == "pdf":
        with path.open("rb") as stream:
            header = stream.read(8)
            stream.seek(max(0, path.stat().st_size - 1024))
            tail = stream.read(1024)
        if not re.fullmatch(rb"%PDF-[12]\.[0-9]", header) or b"%%EOF" not in tail:
            raise CvUploadError("invalid_file_signature")
        return
    try:
        with path.open("rb") as stream:
            if stream.read(4) != b"PK\x03\x04":
                raise ValueError
        with ZipFile(path) as package:
            entries = package.infolist()
            names = {entry.filename for entry in entries}
            if not {"[Content_Types].xml", "word/document.xml"} <= names:
                raise ValueError
            if len(entries) > 2000 or len(names) != len(entries):
                raise ValueError
            if sum(entry.file_size for entry in entries) > 50 * 1024 * 1024:
                raise ValueError
            for entry in entries:
                name = entry.filename
                if (name.startswith("/") or "\\" in name or ":" in name
                    or ".." in PurePosixPath(name).parts
                    or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in name)
                    or entry.flag_bits & 1
                    or entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
                    or entry.file_size > MAX_FILE_BYTES
                    or entry.file_size > max(1, entry.compress_size) * 100
                    or name.lower().endswith("vbaproject.bin")
                    or name.lower().startswith("word/embeddings/")):
                    raise ValueError
            if any(package.getinfo(name).file_size == 0 for name in ("[Content_Types].xml", "word/document.xml")):
                raise ValueError
    except (BadZipFile, ValueError, NotImplementedError):
        raise CvUploadError("malformed_docx") from None


class CvUploadService:
    def __init__(self, storage_root: Path):
        root = storage_root if storage_root.is_absolute() else REPOSITORY_ROOT / storage_root
        self.root = root.resolve()
        # Repository-local storage must stay in the already ignored runtime data tree.
        if self.root == Path(self.root.anchor) or self.root == REPOSITORY_ROOT:
            raise CvUploadError("storage_failed", 500)
        if self.root.is_relative_to(REPOSITORY_ROOT) and not self.root.is_relative_to(REPOSITORY_ROOT / "data"):
            raise CvUploadError("storage_failed", 500)

    def store_batch(self, job_reference: str, files: list[UploadFile]) -> CvUploadResponse:
        try:
            job_reference = CvBatchInput(job_reference=job_reference).job_reference
        except ValueError:
            raise CvUploadError("invalid_job_reference", 422) from None
        if not 1 <= len(files) <= MAX_FILES:
            raise CvUploadError("invalid_batch")
        batch_id = uuid4()
        batch = self.root / job_reference / str(batch_id)
        created = False
        try:
            job_directory = batch.parent
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            job_directory.mkdir(exist_ok=True, mode=0o700)
            if job_directory.is_symlink() or job_directory.resolve().parent != self.root:
                raise OSError
            batch.mkdir(mode=0o700)
            created = True
            total, accepted = 0, []
            for upload in files:
                file_type = document_type(upload)
                upload_id = uuid4()
                destination = batch / f"{upload_id}.{file_type}"
                size = 0
                upload.file.seek(0)
                with destination.open("xb") as target:
                    while chunk := upload.file.read(CHUNK_BYTES):
                        size += len(chunk)
                        total += len(chunk)
                        if size > MAX_FILE_BYTES:
                            raise CvUploadError("file_too_large", 413)
                        if total > MAX_BATCH_BYTES:
                            raise CvUploadError("batch_too_large", 413)
                        target.write(chunk)
                if size == 0:
                    raise CvUploadError("invalid_file_signature")
                validate_document(destination, file_type)
                accepted.append(CvUploadItem(upload_id=upload_id, file_type=file_type, size_bytes=size))
            return CvUploadResponse(job_reference=job_reference, batch_id=batch_id,
                accepted_count=len(accepted), files=tuple(accepted))
        except Exception as error:
            if created:
                try:
                    shutil.rmtree(batch)
                except OSError:
                    raise CvUploadError("storage_failed", 500) from None
            if isinstance(error, CvUploadError):
                raise
            raise CvUploadError("storage_failed", 500) from None
