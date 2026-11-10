FROM python:3.13-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
ENV NLTK_DATA=/usr/local/share/nltk_data
RUN pip install --no-cache-dir . \
    && python -m nltk.downloader -e -d /usr/local/share/nltk_data wordnet
COPY alembic.ini ./
COPY migrations ./migrations
COPY entrypoint.sh /app/entrypoint.sh
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
