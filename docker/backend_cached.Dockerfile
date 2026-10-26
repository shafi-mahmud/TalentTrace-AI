# Optional local acceleration only after exact pinned-package verification.
# Standard clean-machine builds keep using backend.Dockerfile.
ARG GROQ_DEPENDENCY_IMAGE
FROM ${GROQ_DEPENDENCY_IMAGE}
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libtesseract5 tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
ENV OCR_TESSDATA_PATH=/usr/share/tesseract-ocr/5/tessdata
COPY job-publishing-mcp/requirements.txt /tmp/job-publishing-requirements.txt
RUN python -m venv --without-pip --system-site-packages /app/job-publishing-mcp/.venv \
    && pip --python /app/job-publishing-mcp/.venv/bin/python install --no-cache-dir -r /tmp/job-publishing-requirements.txt \
    && pip --python /app/job-publishing-mcp/.venv/bin/python check
COPY job-publishing-mcp/talenttrace_job_publishing /app/job-publishing-mcp/talenttrace_job_publishing
# Discard old application sources inside this new image, preserving only packages.
RUN rm -rf /app/backend/app /app/backend/alembic
COPY --chown=10001:10001 backend/app /app/backend/app
COPY --chown=10001:10001 backend/alembic /app/backend/alembic
COPY backend/alembic.ini /app/backend/alembic.ini
COPY docker/backend_ready.py /app/docker/backend_ready.py
COPY docker/check_discord_mcp.py /app/docker/check_discord_mcp.py
USER 10001:10001
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
