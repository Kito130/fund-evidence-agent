FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore \
    FUND_AGENT_MODE=MOCK_ONLY

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home \
       --home-dir /home/app --shell /usr/sbin/nologin app

WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --requirement requirements.lock
COPY . /app
RUN pip install --no-build-isolation --no-deps . \
    && chown -R app:app /app /home/app
ENV PYTHONPATH=/app/src

USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"

CMD ["python", "-m", "uvicorn", "fund_agent_v2.api:app", "--host", "0.0.0.0", "--port", "8000"]
