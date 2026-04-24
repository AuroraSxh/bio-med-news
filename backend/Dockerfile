FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app

# All runtime deps ship manylinux wheels (psycopg[binary], httpx, etc.),
# so no system build tools are needed. This keeps the image lean and avoids
# OOMs on small VMs where `apt-get install build-essential` spikes to ~1.6 GB.

# Copy only dependency manifest first so the pip-install layer is cached
# across code-only changes.
COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefer-binary .

# Application code (changes frequently — kept as last layer)
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
