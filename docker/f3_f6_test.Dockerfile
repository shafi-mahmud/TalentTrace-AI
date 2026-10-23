# Explicit test-only image. Build the production backend image first.
ARG BACKEND_TEST_BASE=talenttrace-docker-demo-backend:latest
FROM ${BACKEND_TEST_BASE} AS integration
USER root
RUN pip install --no-cache-dir pytest==9.1.1 && pip check
# Replace application code with this checkout; never use stale base-image source.
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/tests ./tests
COPY docker/f3_f6_container.py ./test_f3_f6_container.py
USER 10001:10001
ENV PYTHONPATH=/app/backend:/app/backend/tests HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
CMD ["python", "-B", "-m", "pytest", "test_f3_f6_container.py", "tests/test_capture_epoch_contract.py", "-q", "-p", "no:cacheprovider", "--tb=short"]
