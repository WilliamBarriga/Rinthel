#!/usr/bin/env bash
set -euo pipefail
trap 'echo "VOICE_SETUP_ERROR: setup or service failed (line $LINENO)" >&2' ERR
export DEBIAN_FRONTEND=noninteractive
cd /voice
if [ ! -f /usr/local/share/pithagoras-voice-deps ]; then
  echo 'VOICE_STAGE: Installing build tools'
  dpkg --configure -a
  apt-get update
  apt-get install -y --no-install-recommends git cmake ninja-build build-essential curl ca-certificates python3 libssl-dev aria2 espeak-ng
  touch /usr/local/share/pithagoras-voice-deps
fi
checkout() {
  local directory="$1" repository="$2" revision="$3"
  if [ ! -d "$directory/.git" ]; then git clone "$repository" "$directory"; fi
  git -C "$directory" fetch --tags origin
  git -C "$directory" checkout "$revision"
  git -C "$directory" submodule update --init --recursive
}
echo 'VOICE_STAGE: Preparing pinned audio runtime'
checkout audio https://github.com/0xShug0/audio.cpp.git 5ba81ac54fb071b835680973f8868546b4db372b
if [ ! -x audio/build/portal/bin/audiocpp_server ] || ! grep -q 'AUDIOCPP_BUILD_NATIVE_MODEL_MANAGER:BOOL=ON' audio/build/portal/CMakeCache.txt; then
  echo 'VOICE_STAGE: Building CPU speech runtime'
  (cd audio && bash scripts/build_linux.sh --native-model-manager --system-openssl --cuda off --vulkan off --hip off --build-dir /voice/audio/build/portal --build-type Release --model-set custom --models pocket_tts,kokoro_tts --target audiocpp_server --jobs 4) 2>&1 | tr '\r' '\n'
fi
echo 'VOICE_STAGE: Preparing CPU speech recognition'
checkout whisper https://github.com/ggml-org/whisper.cpp.git a2b36eb677918d4f9ab1db7b8a7ff968563ed163
if [ ! -x whisper/build/bin/whisper-server ]; then
  cmake -S whisper -B whisper/build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=OFF -DWHISPER_BUILD_SERVER=ON
  cmake --build whisper/build --target whisper-server -j 4
fi
mkdir -p models
download() {
  local url="$1" destination="$2" checksum="${3:-}"
  if [ ! -s "$destination" ]; then
    aria2c --continue=true --max-connection-per-server=4 --split=4 --min-split-size=16M --file-allocation=none --auto-file-renaming=false --max-tries=5 --retry-wait=5 --summary-interval=10 --console-log-level=warn ${checksum:+--checksum=sha-256=$checksum} --dir="$(dirname "$destination")" --out="$(basename "$destination").part" "$url" 2>&1 | tr '\r' '\n'
    mv "$destination.part" "$destination"
  fi
}
echo 'VOICE_STAGE: Downloading multilingual Whisper base'
bash whisper/models/download-ggml-model.sh base /voice/models 2>&1 | tr '\r' '\n'
if [ ! -s models/pocket-tts-spanish-q8_0.gguf ]; then
  echo 'VOICE_STAGE: Downloading Pocket TTS (Spanish, Q8_0, pre-quantized)'
  download "https://huggingface.co/audio-cpp/audio.cpp-gguf/resolve/6d5436fc85f7a20c2e9f4e472b7f3a532f686444/PocketTTS-GGUF/spanish/pocket-tts-spanish-q8_0.gguf" models/pocket-tts-spanish-q8_0.gguf
fi
if [ ! -s models/kokoro-82m-q8_0.gguf ]; then
  echo 'VOICE_STAGE: Downloading Kokoro 82M (multilingual, Q8_0, pre-quantized)'
  download "https://huggingface.co/audio-cpp/audio.cpp-gguf/resolve/77af7ee6a8223df27baa2a952aebe142a8a4a929/Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf" models/kokoro-82m-q8_0.gguf
fi
cat > /voice/server.json <<'JSON'
{"host":"0.0.0.0","port":7861,"backend":"cpu","threads":4,"lazy_load":true,"idle_unload_ms":90000,"ui_management":true,"max_loaded_models":2,"models":[{"id":"breeze","family":"pocket_tts","path":"/voice/models/pocket-tts-spanish-q8_0.gguf","task":"tts","mode":"streaming"},{"id":"kokoro","family":"kokoro_tts","path":"/voice/models/kokoro-82m-q8_0.gguf","task":"tts","mode":"offline"}]}
JSON
echo 'VOICE_STAGE: Starting speech services'
whisper/build/bin/whisper-server --host 0.0.0.0 --port 8178 --model /voice/models/ggml-base.bin --language auto --threads 4 &
whisper_pid=$!
audio/build/portal/bin/audiocpp_server --config /voice/server.json &
speech_pid=$!
trap 'kill "$whisper_pid" "$speech_pid" 2>/dev/null || true; wait; exit 0' TERM INT
set +e
wait -n "$whisper_pid" "$speech_pid"
code=$?
kill "$whisper_pid" "$speech_pid" 2>/dev/null
wait
exit "$code"
