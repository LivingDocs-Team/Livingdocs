FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY code-analyzer/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY app/ ./app/

# Run as an unprivileged user.
RUN useradd --system --no-create-home --uid 10001 analyzer
# LD-402: evidences and submissions are saved here (the analyzer-data volume in compose.yaml);
# the folder must belong to the unprivileged user or the first save fails.
RUN mkdir -p /app/data && chown analyzer /app/data
ENV SUBMISSIONS_FILE=/app/data/submissions.json
USER analyzer

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
