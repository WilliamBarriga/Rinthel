# whisper.cpp no publica una imagen oficial con el servidor HTTP (solo con
# el binario CLI "main" — el target `whisper-server` es de cmake, no del
# Makefile plano que usa ese Dockerfile oficial), así que lo compilamos acá
# desde una tag fija.
FROM ubuntu:24.04 AS build
WORKDIR /src

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential cmake git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Tag fija (no una branch en movimiento) — "qué versión de la fuente de
# verdad clonamos" no es un parámetro de usuario, mismo criterio que la
# branch de llama.cpp en rinthel_tui/lifecycle/install.py.
ARG WHISPER_CPP_TAG=b4938
RUN git clone --branch ${WHISPER_CPP_TAG} --depth 1 \
    https://github.com/ggml-org/whisper.cpp.git /src

# BUILD_SHARED_LIBS=OFF: enlaza libggml/libwhisper estático dentro del
# binario — sin esto whisper-server queda linkeado contra libwhisper.so
# (falla en runtime con "cannot open shared object file" si no se copian
# también las .so, más frágil que un binario autocontenido).
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_SERVER=ON \
        -DWHISPER_BUILD_EXAMPLES=ON -DBUILD_SHARED_LIBS=OFF && \
    cmake --build build -j"$(nproc)" --target whisper-server

# Modelo GGML — descarga verificada contra el sha256 real de Hugging Face
# (X-Linked-ETag / git-LFS oid, un valor genuino de upstream, a diferencia
# del tarball de un release de GitHub más abajo en TTS).
FROM ubuntu:24.04 AS model
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
ARG WHISPER_MODEL=ggml-base.bin
ARG WHISPER_MODEL_SHA256=60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe
RUN curl -fL -o /model.bin "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${WHISPER_MODEL}" && \
    echo "${WHISPER_MODEL_SHA256}  /model.bin" | sha256sum -c -

FROM ubuntu:24.04 AS runtime
WORKDIR /app

# ffmpeg: --convert de whisper-server lo shellea para pasar cualquier
# formato (el navegador graba webm/opus) a WAV 16kHz antes de transcribir.
# python3: corre proxy.py (auth/origin) delante de whisper-server, que no
# tiene forma de autenticar sus propias requests.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg python3 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=build /src/build/bin/whisper-server /usr/local/bin/whisper-server
COPY --from=model /model.bin /app/models/ggml-base.bin
COPY proxy.py entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

EXPOSE 8090
ENTRYPOINT ["/app/entrypoint.sh"]
