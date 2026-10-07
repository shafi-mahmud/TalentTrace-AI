"""Mocked OCR unit tests plus an optional real synthetic image-only integration."""
import asyncio
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
import pytest

from app.api.routers import cv_uploads as route
from app.core.config import Settings
from app.main import app
from app.services import cv_ocr as service
from app.services.cv_extraction import CvExtractionService
from test_cv_extraction import TEXT, REFERENCE, pdf_bytes, docx_bytes, stored


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    root = tmp_path / "private"
    monkeypatch.setattr(route, "settings", Settings(_env_file=None, ocr_tessdata_path=None, cv_upload_root=root))
    async def forbidden(*args, **kwargs):
        pytest.fail("OCR must not call external services.")
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    return root


@pytest.fixture
def fake_engine(monkeypatch, tmp_path):
    calls = []
    data = tmp_path / "tessdata"
    data.mkdir(); (data / "eng.traineddata").write_bytes(b"synthetic unit-test placeholder")
    monkeypatch.setattr(route, "settings", Settings(_env_file=None, ocr_tessdata_path=data, cv_upload_root=tmp_path / "private"))
    def recognize(page, tessdata):
        calls.append(page.number)
        return f"SYNTHETIC PAGE {page.number + 1} " + TEXT
    monkeypatch.setattr(service, "ocr_page_text", recognize)
    return data, calls


def request(batch_id, reference=REFERENCE):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(f"/api/v1/cv-uploads/{reference}/{batch_id}/ocr")
    return asyncio.run(send())


@pytest.mark.parametrize("kind,content", [("pdf", pdf_bytes()), ("docx", docx_bytes()), ("pdf", b"%PDF-1.4\nbroken\n%%EOF")], ids=["digital-pdf", "docx", "failed-pdf"])
def test_ineligible_files_are_noop_without_resolving_tesseract(private_storage, monkeypatch, kind, content):
    batch_id, _, _ = stored(private_storage, (kind, content))
    monkeypatch.setattr(service, "resolve_tessdata", lambda *a: pytest.fail("No OCR configuration needed"))
    monkeypatch.setattr(service, "ocr_page_text", lambda *a: pytest.fail("Ineligible file must not invoke OCR"))
    response = request(batch_id)
    assert response.status_code == 200
    assert response.json()["attempted_count"] == 0
    assert response.json()["files"] == []


def test_mixed_batch_only_attempts_eligible_pdf(private_storage, fake_engine):
    _, calls = fake_engine
    batch_id, batch, paths = stored(private_storage, ("pdf", pdf_bytes()), ("docx", docx_bytes()),
        ("pdf", pdf_bytes(("",))), ("pdf", b"%PDF-1.4\nbroken\n%%EOF"))
    originals = {path.name: path.read_bytes() for path in paths}
    response = request(batch_id)
    assert response.status_code == 200
    assert response.json()["attempted_count"] == 1
    assert response.json()["files"][0]["ocr_status"] == "ocr_extracted"
    assert response.json()["files"][0]["upload_id"] == paths[2].stem
    assert calls == [0]
    assert {path.name: path.read_bytes() for path in batch.iterdir()} == originals
    for private in ["SYNTHETIC", "traineddata", '"text"', "source_units", "path", "filename"]:
        assert private not in response.text


def test_ocr_evidence_order_source_methods_and_normalization(private_storage, fake_engine, monkeypatch):
    data, calls = fake_engine
    batch_id, _, paths = stored(private_storage, ("pdf", pdf_bytes((TEXT, "", ""))))
    original = paths[0].read_bytes()
    def recognize(page, tessdata):
        calls.append(page.number)
        return f" OCR PAGE {page.number + 1}\r\n" + TEXT + "\x00\x01 "
    monkeypatch.setattr(service, "ocr_page_text", recognize)
    result, = service.CvOcrService(private_storage, data).process_batch(REFERENCE, batch_id)
    assert result.ocr_status == "ocr_extracted"
    assert [unit.page_number for unit in result.source_units] == [1, 2, 3]
    assert [unit.source_method for unit in result.source_units] == ["digital", "ocr", "ocr"]
    assert result.source_units[0].text == CvExtractionService(private_storage).extract_batch(REFERENCE, batch_id)[0].source_units[0].text
    assert result.text == "\n\n".join(unit.text for unit in result.source_units)
    assert "\r" not in result.text and "\x00" not in result.text
    assert calls == [1, 2]
    assert result.ocr_page_count == 2
    assert "SYNTHETIC" not in repr(result)
    assert paths[0].read_bytes() == original


def test_total_threshold_failure_can_ocr_pages_above_page_threshold(private_storage, fake_engine):
    data, calls = fake_engine
    batch_id, _, _ = stored(private_storage, ("pdf", pdf_bytes(("A" * 30, "B" * 30))))
    assert CvExtractionService(private_storage).extract_batch(REFERENCE, batch_id)[0].extraction_status == "ocr_required"
    result, = service.CvOcrService(private_storage, data).process_batch(REFERENCE, batch_id)
    assert result.ocr_status == "ocr_extracted"
    assert calls == [0, 1]


@pytest.mark.parametrize("mode", ["empty", "negligible", "punctuation", "exception", "too_long"])
def test_file_failure_safe_and_original_unchanged(private_storage, fake_engine, monkeypatch, mode, caplog, capsys):
    data, _ = fake_engine
    batch_id, batch, paths = stored(private_storage, ("pdf", pdf_bytes(("",))))
    original = paths[0].read_bytes()
    def failed(page, tessdata):
        if mode == "exception": raise RuntimeError("PRIVATE_OCR_PATH_OR_SECRET")
        return {"empty": "", "negligible": "tiny", "punctuation": "!" * 200,
            "too_long": "A" * (service.MAX_TEXT_CHARS + 1)}[mode]
    monkeypatch.setattr(service, "ocr_page_text", failed)
    response = request(batch_id)
    assert response.status_code == 200
    assert response.json()["files"][0]["ocr_status"] == "ocr_failed"
    assert response.json()["files"][0]["text_char_count"] == 0
    assert paths[0].read_bytes() == original
    assert list(batch.iterdir()) == paths
    captured = capsys.readouterr()
    assert "PRIVATE_OCR" not in response.text + caplog.text + captured.out + captured.err


def test_ocr_is_not_success_when_recognized_pages_recover_nothing(private_storage, fake_engine, monkeypatch):
    data, _ = fake_engine
    batch_id, _, _ = stored(private_storage, ("pdf", pdf_bytes((TEXT, "", ""))))
    monkeypatch.setattr(service, "ocr_page_text", lambda *a: "")
    result, = service.CvOcrService(private_storage, data).process_batch(REFERENCE, batch_id)
    assert result.ocr_status == "ocr_failed"


def test_page_limit_prevents_any_ocr_call(private_storage, fake_engine, monkeypatch):
    _, calls = fake_engine
    batch_id, _, _ = stored(private_storage, ("pdf", pdf_bytes(("",) * 26)))
    response = request(batch_id)
    assert response.status_code == 200
    assert response.json()["files"][0]["ocr_status"] == "ocr_failed"
    assert response.json()["files"][0]["ocr_page_count"] == 0
    assert calls == []


def test_render_and_batch_limits_are_controlled(private_storage, fake_engine, monkeypatch):
    _, calls = fake_engine
    batch_id, _, _ = stored(private_storage, ("pdf", pdf_bytes(("",))))
    monkeypatch.setattr(service, "MAX_OCR_PAGE_PIXELS", 1)
    assert request(batch_id).json()["files"][0]["ocr_status"] == "ocr_failed"
    assert calls == []
    monkeypatch.setattr(service, "MAX_OCR_PAGE_PIXELS", 25_000_000)
    monkeypatch.setattr(service, "MAX_OCR_BATCH_PAGES", 0)
    assert request(batch_id).json()["files"][0]["ocr_status"] == "ocr_failed"
    assert calls == []


def test_one_ocr_failure_does_not_prevent_another_success(private_storage, fake_engine, monkeypatch):
    _, calls = fake_engine
    batch_id, batch, paths = stored(private_storage, ("pdf", pdf_bytes(("",))), ("pdf", pdf_bytes(("",))))
    originals = {path.name: path.read_bytes() for path in paths}
    def recognize(page, tessdata):
        calls.append(page.number)
        if len(calls) == 1: raise RuntimeError("PRIVATE_PARSE_DETAIL")
        return TEXT
    monkeypatch.setattr(service, "ocr_page_text", recognize)
    response = request(batch_id)
    assert [file["ocr_status"] for file in response.json()["files"]] == ["ocr_failed", "ocr_extracted"]
    assert calls == [0, 0]
    assert {path.name: path.read_bytes() for path in batch.iterdir()} == originals


def test_explicit_valid_language_data_is_used_without_discovery(fake_engine, monkeypatch):
    data, _ = fake_engine
    monkeypatch.setattr(pymupdf, "get_tessdata", lambda: pytest.fail("Explicit path must take precedence"))
    assert service.resolve_tessdata(data) == data.resolve()


@pytest.mark.parametrize("mode", ["missing_directory", "missing_english", "empty_english"])
def test_bad_language_data_rejected_lazily(private_storage, tmp_path, monkeypatch, mode):
    data = tmp_path / "invalid-tessdata"
    if mode != "missing_directory": data.mkdir()
    if mode == "empty_english": (data / "eng.traineddata").write_bytes(b"")
    monkeypatch.setattr(route, "settings", Settings(_env_file=None, ocr_tessdata_path=data, cv_upload_root=private_storage))
    batch_id, _, _ = stored(private_storage, ("pdf", pdf_bytes(("",))))
    response = request(batch_id)
    assert response.status_code == 503
    assert response.json() == {"code": "ocr_not_configured", "message": "OCR processing is not configured."}
    assert str(data) not in response.text
    digital_id, _, _ = stored(private_storage, ("pdf", pdf_bytes()))
    assert request(digital_id).json()["attempted_count"] == 0


def test_unconfigured_path_can_use_discovery(fake_engine, monkeypatch):
    data, _ = fake_engine
    monkeypatch.setattr(pymupdf, "get_tessdata", lambda: str(data))
    assert service.resolve_tessdata(None) == data.resolve()


def test_discovery_failure_returns_controlled_503(private_storage, monkeypatch):
    def missing(): raise RuntimeError("PRIVATE_ENVIRONMENT_PATH")
    monkeypatch.setattr(pymupdf, "get_tessdata", missing)
    batch_id, _, _ = stored(private_storage, ("pdf", pdf_bytes(("",))))
    response = request(batch_id)
    assert response.status_code == 503
    assert "PRIVATE" not in response.text


@pytest.mark.parametrize("reference,batch", [("bad-reference", str(uuid4())), (REFERENCE, "bad-uuid")])
def test_invalid_identity_422_without_echo(reference, batch):
    response = request(batch, reference)
    assert response.status_code == 422
    assert reference not in response.text and batch not in response.text


def test_missing_batch_404_before_engine_lookup(monkeypatch):
    monkeypatch.setattr(service, "resolve_tessdata", lambda *a: pytest.fail("Batch validation must run first"))
    assert request(uuid4()).status_code == 404


@pytest.mark.parametrize("layout", ["filename", "directory", "symlink", "junction"])
def test_storage_validation_is_reused_before_ocr(private_storage, monkeypatch, layout):
    batch_id, batch, paths = stored(private_storage, ("pdf", pdf_bytes(("",))))
    if layout == "filename": paths[0].rename(batch / "untrusted.pdf")
    elif layout == "directory": (batch / "untrusted-directory").mkdir()
    else:
        name = "is_symlink" if layout == "symlink" else "is_junction"
        original = getattr(Path, name)
        monkeypatch.setattr(Path, name, lambda path: path == batch or original(path))
    monkeypatch.setattr(service, "resolve_tessdata", lambda *a: pytest.fail("Unsafe batch must not reach OCR"))
    assert request(batch_id).status_code == 400


def test_unexpected_service_error_sanitized(private_storage, monkeypatch):
    def failure(*args): raise RuntimeError("PRIVATE_ROOT_OR_TEXT")
    monkeypatch.setattr(service.CvOcrService, "process_batch", failure)
    response = request(uuid4())
    assert response.status_code == 500
    assert response.json()["code"] == "ocr_unavailable"
    assert "PRIVATE" not in response.text


def test_real_page_helper_uses_fixed_engine_options_and_suppresses_diagnostics(tmp_path, capfd):
    import sys, os
    class SyntheticPage:
        def get_textpage_ocr(self, **options):
            assert options == {"language": "eng", "dpi": 300, "full": True, "tessdata": str(tmp_path)}
            print("PRIVATE_TESSERACT_DETAIL", file=sys.stderr)
            os.write(2, b"PRIVATE_NATIVE_DETAIL\n")
            return "synthetic textpage"
        def get_text(self, kind, **options):
            assert kind == "text" and options == {"textpage": "synthetic textpage", "sort": True}
            return TEXT
    assert service.ocr_page_text(SyntheticPage(), tmp_path) == TEXT
    assert "PRIVATE" not in capfd.readouterr().err
    print("stderr restored", file=sys.stderr)
    assert "stderr restored" in capfd.readouterr().err


def test_real_synthetic_image_only_ocr_when_language_data_available(private_storage):
    try:
        data = service.resolve_tessdata(Settings().ocr_tessdata_path)
    except service.OcrNotConfigured:
        pytest.skip("Local Tesseract English language data is unavailable.")
    with pymupdf.open() as digital:
        page = digital.new_page()
        page.insert_text((50, 90), "SYNTHETIC ONLY NOT A REAL CV", fontsize=18)
        page.insert_text((50, 125), "Python FastAPI PostgreSQL Testing", fontsize=18)
        page.insert_text((50, 160), "Backend development REST API automated testing experience", fontsize=18)
        image = page.get_pixmap(dpi=150)
        with pymupdf.open() as scanned:
            scanned.new_page().insert_image(page.rect, pixmap=image)
            content = scanned.tobytes()
    batch_id, _, paths = stored(private_storage, ("pdf", content))
    assert CvExtractionService(private_storage).extract_batch(REFERENCE, batch_id)[0].extraction_status == "ocr_required"
    result, = service.CvOcrService(private_storage, data).process_batch(REFERENCE, batch_id)
    assert result.ocr_status == "ocr_extracted"
    assert all(word in result.text.casefold() for word in ["synthetic", "python", "fastapi", "testing"])
    assert paths[0].read_bytes() == content
