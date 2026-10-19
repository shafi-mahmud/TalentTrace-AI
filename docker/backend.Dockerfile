FROM python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/backend
COPY backend/requirements.txt /tmp/requirements.txt
# CPU-only PyTorch avoids downloading CUDA libraries. No model is downloaded.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip check
RUN useradd --uid 10001 --create-home app \
    && mkdir -p /app/data/cv_uploads /app/docker \
    && chown -R app:app /app/data
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY docker/backend_ready.py /app/docker/backend_ready.py
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
