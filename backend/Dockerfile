FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --disable-pip-version-check -r requirements.txt

# Playwright 要求浏览器二进制与 Python 包版本匹配；小体积 CJK 字体提供中日韩字形。
RUN printf 'Acquire::Retries "5";\n' > /etc/apt/apt.conf.d/80-retries

RUN python -m playwright install-deps chromium

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-wqy-zenhei fonts-arphic-ukai \
    && rm -rf /var/lib/apt/lists/*

# 将下载与系统依赖分层，重试浏览器下载时复用前两层。
RUN PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=120000 python -m playwright install chromium

RUN addgroup --system app && adduser --system --ingroup app app
RUN chown -R app:app /ms-playwright
RUN mkdir -p /tmp/.cache && chown app:app /tmp/.cache

ENV XDG_CACHE_HOME=/tmp/.cache

COPY --chown=app:app . .

USER app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
