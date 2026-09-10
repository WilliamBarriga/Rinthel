# rhasspy/piper está archivado (solo lectura desde 2025-10-06) — su último
# release (2023.11.14-2) nunca va a cambiar, así que pinearlo acá es
# definitivo, no un pin "hasta la próxima versión".
FROM python:3.12-slim AS runtime
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Binario piper — ni whisper.cpp ni el Piper archivado publican checksums
# oficiales para sus release tarballs de GitHub; este sha256 es un pin
# propio (detecta corrupción/tampering posterior al pin, no es una
# atestación de upstream).
ARG PIPER_RELEASE=2023.11.14-2
ARG PIPER_SHA256=a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992
RUN curl -fL -o /tmp/piper.tar.gz \
    "https://github.com/rhasspy/piper/releases/download/${PIPER_RELEASE}/piper_linux_x86_64.tar.gz" && \
    echo "${PIPER_SHA256}  /tmp/piper.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/piper.tar.gz -C /app && \
    rm /tmp/piper.tar.gz

# Voces ES/EN — descarga verificada contra el sha256 real de Hugging Face
# (git-LFS oid, valor genuino de upstream, no un pin propio).
RUN mkdir -p /app/voices && \
    curl -fL -o /app/voices/es_AR-daniela-high.onnx \
      "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_AR/daniela/high/es_AR-daniela-high.onnx" && \
    echo "7ceb1fc0dab349418c5b54a639ae9ee595212d7c9ea422220d8419163d5cc985  /app/voices/es_AR-daniela-high.onnx" | sha256sum -c - && \
    curl -fL -o /app/voices/es_AR-daniela-high.onnx.json \
      "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_AR/daniela/high/es_AR-daniela-high.onnx.json" && \
    echo "aedbf69647e1d754c62ecf8e0366ca5f16af3e768e3c6b5329af6eb6bde3852b  /app/voices/es_AR-daniela-high.onnx.json" | sha256sum -c - && \
    curl -fL -o /app/voices/en_US-hfc_female-medium.onnx \
      "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx" && \
    echo "914c473788fc1fa8b63ace1cdcdb44588f4ae523d3ab37df1536616835a140b7  /app/voices/en_US-hfc_female-medium.onnx" | sha256sum -c - && \
    curl -fL -o /app/voices/en_US-hfc_female-medium.onnx.json \
      "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx.json" && \
    echo "03f1fa0622b80463283592d97aca9f6e89aec345a5c56b7257723e0093c58b6c  /app/voices/en_US-hfc_female-medium.onnx.json" | sha256sum -c -

COPY server.py /app/server.py

EXPOSE 8091
ENTRYPOINT ["python3", "/app/server.py", "--host", "0.0.0.0", "--port", "8091", \
            "--piper-bin", "/app/piper/piper", \
            "--voice-es", "/app/voices/es_AR-daniela-high.onnx", \
            "--voice-en", "/app/voices/en_US-hfc_female-medium.onnx"]
