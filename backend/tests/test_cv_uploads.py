import asyncio
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest

from app.main import app
from app.api.routers import cv_uploads as route
from app.core.config import Settings
from app.services import cv_upload as service

REFERENCE = "TT-JOB-30BB2CDF9A5CCCA9"


def pdf_bytes():
    """Generate a blank one-page PDF, including a valid cross-reference table."""
    content = b"%PDF-1.4\n"
    offsets = []
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>"]
    for index, body in enumerate(objects, 1):
        offsets.append(len(content))
        content += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    start = len(content)
    content += b"xref\n0 4\n0000000000 65535 f \n"
    content += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return content + f"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()


PDF = pdf_bytes()


def docx_bytes(extra=None):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p/></w:body></w:document>')
        archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        if extra:
            archive.writestr(*extra)
    return output.getvalue()


def pdf(name="synthetic.pdf", content=PDF):
    return ("files", (name, content, "application/pdf"))


def docx():
    return ("files", ("synthetic.docx", docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))


async def send(files, reference=REFERENCE, **kwargs):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/v1/cv-uploads", data={"job_reference": reference}, files=files, **kwargs)


@pytest.fixture(autouse=True)
def private_test_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(route, "settings", Settings(_env_file=None, cv_upload_root=tmp_path / "private"))
    async def forbidden(*args, **kwargs):
        pytest.fail("CV intake must not make external network calls.")
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    return tmp_path / "private"


@pytest.mark.parametrize("files", [[pdf()], [docx()], [pdf(), docx()], [pdf(f"synthetic-{i}.pdf") for i in range(20)]])
def test_valid_batch_stores_opaque_files_and_safe_metadata(files, private_test_storage):
    response = asyncio.run(send(files))
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"status", "job_reference", "batch_id", "accepted_count", "files"}
    assert body["status"] == "uploaded"
    assert body["job_reference"] == REFERENCE
    assert body["accepted_count"] == len(files)
    assert UUID(body["batch_id"]).version == 4
    for item, (_, (_, content, _)) in zip(body["files"], files):
        assert set(item) == {"upload_id", "file_type", "size_bytes"}
        assert UUID(item["upload_id"]).version == 4
        assert item["size_bytes"] == len(content)
        path = private_test_storage / REFERENCE / body["batch_id"] / f'{item["upload_id"]}.{item["file_type"]}'
        assert path.read_bytes() == content
    assert "synthetic.pdf" not in response.text
    assert str(private_test_storage) not in response.text
    assert len(list(private_test_storage.rglob("*.pdf"))) + len(list(private_test_storage.rglob("*.docx"))) == len(files)


@pytest.mark.parametrize("files", [[], [pdf() for _ in range(21)]])
def test_invalid_count_is_rejected_without_storing(files, private_test_storage):
    # A text-only multipart request, rather than urlencoded data, exercises zero files.
    if not files:
        files = [("job_reference", (None, REFERENCE))]
        async def empty():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                return await client.post("/api/v1/cv-uploads", files=files)
        response = asyncio.run(empty())
    else:
        response = asyncio.run(send(files))
    assert response.status_code == 400
    assert not list(private_test_storage.rglob("*.pdf"))


@pytest.mark.parametrize("name,content,mime,code", [
    ("synthetic.exe", b"MZ", "application/octet-stream", "unsupported_file_type"),
    ("synthetic.pdf", b"MZ PRIVATE_CONTENT", "application/pdf", "invalid_file_signature"),
    ("synthetic.docx", PDF, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "malformed_docx"),
    ("synthetic.pdf", docx_bytes(), "application/pdf", "invalid_file_signature"),
    ("synthetic.docx", b"PK invalid", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "malformed_docx"),
    ("synthetic.docx", b"MZ executable prefix" + docx_bytes(), "application/octet-stream", "malformed_docx"),
    ("synthetic.pdf", PDF, "image/png", "unsupported_file_type"),
    ("synthetic.pdf", b"", "application/pdf", "invalid_file_signature"),
    ("synthetic.pdf", b"%PDF-1.4 invalid", "application/pdf", "invalid_file_signature"),
])
def test_extension_mime_and_content_validation(name, content, mime, code, private_test_storage):
    response = asyncio.run(send([("files", (name, content, mime))]))
    assert response.status_code in {400, 415}
    assert response.json()["code"] == code
    assert "PRIVATE_CONTENT" not in response.text
    assert not list(private_test_storage.rglob("*.*"))


def test_arbitrary_zip_is_not_docx(private_test_storage):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("unrelated.txt", "Synthetic only")
    response = asyncio.run(send([("files", ("synthetic.docx", output.getvalue(), "application/octet-stream"))]))
    assert response.status_code == 400
    assert response.json()["code"] == "malformed_docx"


@pytest.mark.parametrize("member", ["../outside", "/absolute", "word/vbaProject.bin", "word/embeddings/payload.bin"])
def test_unsafe_docx_package_rejected(member):
    response = asyncio.run(send([("files", ("synthetic.docx", docx_bytes((member, b"synthetic")), "application/octet-stream"))]))
    assert response.status_code == 400
    assert response.json()["code"] == "malformed_docx"


def test_high_compression_docx_package_rejected():
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"synthetic")
        archive.writestr("word/document.xml", b"x" * (1024 * 1024))
    response = asyncio.run(send([("files", ("synthetic.docx", output.getvalue(), "application/octet-stream"))]))
    assert response.status_code == 400
    assert response.json()["code"] == "malformed_docx"


def test_duplicate_docx_members_rejected():
    with pytest.warns(UserWarning, match="Duplicate name"):
        content = docx_bytes(("word/document.xml", b"synthetic"))
    response = asyncio.run(send([("files", ("synthetic.docx", content, "application/octet-stream"))]))
    assert response.status_code == 400
    assert response.json()["code"] == "malformed_docx"


def test_response_and_logs_do_not_expose_uploaded_content(caplog):
    content = PDF.replace(b"%%EOF", b"% SYNTHETIC_PRIVATE_CONTENT\n%%EOF")
    response = asyncio.run(send([pdf("synthetic-private.pdf", content)]))
    assert response.status_code == 201
    for private in ["SYNTHETIC_PRIVATE_CONTENT", "synthetic-private.pdf"]:
        assert private not in response.text
        assert private not in caplog.text


@pytest.mark.parametrize("name", ["../../secret.pdf", r"..\..\secret.pdf", r"C:\private\secret.pdf", r"\\server\share\secret.pdf"])
def test_original_paths_never_influence_storage(name, private_test_storage):
    response = asyncio.run(send([pdf(name)]))
    # Some multipart clients/parsers strip Windows paths to a basename first.
    assert response.status_code in {400, 201}
    assert "secret.pdf" not in response.text
    if response.status_code == 201:
        body = response.json()
        item = body["files"][0]
        stored = private_test_storage / REFERENCE / body["batch_id"] / f'{item["upload_id"]}.pdf'
        assert stored.read_bytes() == PDF
        assert UUID(stored.stem).version == 4
    else:
        assert response.json()["code"] == "invalid_filename"
        assert not list(private_test_storage.rglob("*.pdf"))


@pytest.mark.parametrize("name", ["../../secret.pdf", r"..\..\secret.pdf", r"C:\private\secret.pdf", r"\\server\share\secret.pdf"])
def test_raw_traversal_filename_rejected_by_service(name, private_test_storage):
    from starlette.datastructures import Headers, UploadFile
    upload = UploadFile(BytesIO(PDF), filename=name, headers=Headers({"content-type": "application/pdf"}))
    with pytest.raises(service.CvUploadError, match="filename"):
        service.CvUploadService(private_test_storage).store_batch(REFERENCE, [upload])
    assert not list(private_test_storage.rglob("*.pdf"))


def test_individual_limit_enforced_while_streaming(monkeypatch, private_test_storage):
    monkeypatch.setattr(service, "MAX_FILE_BYTES", len(PDF) - 1)
    response = asyncio.run(send([pdf()]))
    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"
    assert not list(private_test_storage.rglob("*.pdf"))


def test_total_limit_rolls_back_previous_file(monkeypatch, private_test_storage):
    monkeypatch.setattr(service, "MAX_BATCH_BYTES", len(PDF) * 2 - 1)
    response = asyncio.run(send([pdf(), pdf()]))
    assert response.status_code == 413
    assert response.json()["code"] == "batch_too_large"
    assert not list(private_test_storage.rglob("*.pdf"))


def test_valid_then_invalid_removes_entire_batch(private_test_storage):
    response = asyncio.run(send([pdf(), pdf(content=b"PRIVATE_CONTENT")]))
    assert response.status_code == 400
    assert "PRIVATE_CONTENT" not in response.text
    assert not list(private_test_storage.rglob("*.pdf"))
    assert list((private_test_storage / REFERENCE).iterdir()) == []


def test_storage_failure_removes_previous_file(monkeypatch, private_test_storage):
    original = Path.open
    writes = 0
    def fail_second(path, mode="r", *args, **kwargs):
        nonlocal writes
        if mode == "xb":
            writes += 1
            if writes == 2:
                raise OSError("PRIVATE_STORAGE_PATH")
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail_second)
    response = asyncio.run(send([pdf(), pdf()]))
    assert response.status_code == 500
    assert "PRIVATE_STORAGE_PATH" not in response.text
    assert not list(private_test_storage.rglob("*.pdf"))


@pytest.mark.parametrize("reference", ["", "TT-JOB-0001", "tt-job-30bb2cdf9a5ccca9", "../PRIVATE_PATH", "TT-JOB-" + "F" * 17])
def test_invalid_reference_never_leaks_or_stores(reference, private_test_storage):
    response = asyncio.run(send([pdf()], reference))
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_job_reference"
    assert "PRIVATE_PATH" not in response.text
    assert not private_test_storage.exists()


def test_request_budget_rejects_declared_oversize_before_parsing(monkeypatch):
    monkeypatch.setattr(route, "MAX_REQUEST_BYTES", 100)
    response = asyncio.run(send([pdf()]))
    assert response.status_code == 413


def test_chunked_request_budget_works_without_content_length(monkeypatch):
    monkeypatch.setattr(route, "MAX_REQUEST_BYTES", 40)
    async def body():
        yield b"--demo\r\nContent-Disposition: form-data; name=\"job_reference\"\r\n\r\n"
        yield REFERENCE.encode() + b"\r\n--demo--\r\n"
    async def call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/v1/cv-uploads", content=body(), headers={"Content-Type": "multipart/form-data; boundary=demo"})
    assert asyncio.run(call()).status_code == 413


def test_json_upload_is_rejected():
    async def call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/v1/cv-uploads", json={"job_reference": REFERENCE, "files": []})
    assert asyncio.run(call()).status_code == 415


def test_unknown_form_field_and_duplicate_reference_rejected():
    async def call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/v1/cv-uploads", files=[pdf(), ("job_reference", (None, REFERENCE)), ("api_key", (None, "PRIVATE_CONTENT"))])
    response = asyncio.run(call())
    assert response.status_code == 400
    assert "PRIVATE_CONTENT" not in response.text


def test_storage_cannot_be_configured_under_frontend():
    with pytest.raises(service.CvUploadError):
        service.CvUploadService(service.REPOSITORY_ROOT / "frontend" / "private")


def test_openapi_describes_native_multipart_upload():
    operation = app.openapi()["paths"]["/api/v1/cv-uploads"]["post"]
    assert "multipart/form-data" in operation["requestBody"]["content"]
