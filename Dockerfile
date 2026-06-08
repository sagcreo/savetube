FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates unzip && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --force-reinstall \
    "yt-dlp[default] @ https://github.com/yt-dlp/yt-dlp/archive/refs/heads/master.zip"

COPY src/ src/

EXPOSE 6060

CMD ["python", "-m", "src.main"]
