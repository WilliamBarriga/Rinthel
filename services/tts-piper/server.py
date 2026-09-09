"""Wrapper HTTP mínimo sobre el binario `piper` (que solo tiene CLI, sin
server nativo — a diferencia de whisper.cpp). Stdlib puro, sin deps nuevas:
texto+idioma entra por POST /speak, sale un WAV.

Uso: python server.py --host 127.0.0.1 --port 8091 --piper-bin PATH
     --voice-es PATH --voice-en PATH
"""

import argparse
import json
import os
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _synthesize(piper_bin: str, voice_path: str, text: str) -> bytes:
    # --output_file - (stdout) no es seekable: piper no puede volver a
    # patchear el header WAV con el tamaño real una vez que termina de
    # escribir, y deja el "data size" del header con un valor provisorio
    # (mucho menor al real) — el browser corta la reproducción ahí.
    # Un archivo real sí es seekable, header correcto garantizado.
    fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            [piper_bin, "--model", voice_path, "--output_file", tmp_path],
            input=text.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def make_handler(voices: dict[str, str], piper_bin: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            print(f"[tts-piper] {self.address_string()} {fmt % args}")

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"tts-piper ok")

        def do_POST(self) -> None:
            if self.path != "/speak":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body)
                text = payload["text"]
                lang = payload.get("lang", "es")
            except (json.JSONDecodeError, KeyError):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"bad request: need {\"text\": ..., \"lang\"?: \"es\"|\"en\"}")
                return
            voice_path = voices.get(lang, voices["es"])
            try:
                wav_bytes = _synthesize(piper_bin, voice_path, text)
            except subprocess.CalledProcessError as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"piper failed: {e.stderr.decode(errors='replace')}".encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav_bytes)))
            self.end_headers()
            self.wfile.write(wav_bytes)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--piper-bin", required=True)
    parser.add_argument("--voice-es", required=True)
    parser.add_argument("--voice-en", required=True)
    args = parser.parse_args()

    voices = {"es": args.voice_es, "en": args.voice_en}
    server = ThreadingHTTPServer((args.host, args.port), make_handler(voices, args.piper_bin))
    print(f"[tts-piper] escuchando en http://{args.host}:{args.port} — voces: {voices}")
    server.serve_forever()


if __name__ == "__main__":
    main()
