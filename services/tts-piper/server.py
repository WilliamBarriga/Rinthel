"""Wrapper HTTP mínimo sobre el binario `piper` (que solo tiene CLI, sin
server nativo — a diferencia de whisper.cpp). Stdlib puro, sin deps nuevas:
texto+idioma entra por POST /speak, sale un WAV.

Uso: python server.py --host 127.0.0.1 --port 8091 --piper-bin PATH
     --voice-es PATH --voice-en PATH
AUTH_TOKEN/ALLOWED_ORIGIN/MAX_TEXT_LENGTH se leen del entorno (los pasa
docker-compose) — AUTH_TOKEN es requerido, sin él el proceso no arranca en
vez de quedar sirviendo /speak sin auth.
"""

import argparse
import hmac
import json
import os
import subprocess
import sys
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


def _check_auth(headers, auth_token: str) -> bool:
    expected = f"Bearer {auth_token}"
    return hmac.compare_digest(headers.get("Authorization", ""), expected)


def _check_origin(headers, allowed_origin: str) -> bool:
    origin = headers.get("Origin")
    # Sin header Origin (caller que no es un browser) se deja pasar — el
    # bearer token es el gate real; exigir Origin rompería a cualquier
    # caller server-to-server legítimo que no manda ese header.
    if not origin or not allowed_origin:
        return True
    return origin == allowed_origin


def make_handler(
    voices: dict[str, str],
    piper_bin: str,
    *,
    auth_token: str = "",
    allowed_origin: str = "",
    max_text_length: int = 2000,
):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            print(f"[tts-piper] {self.address_string()} {fmt % args}")

        def _cors_headers(self) -> None:
            if allowed_origin:
                self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._cors_headers()
            self.end_headers()

        def do_GET(self) -> None:
            # Liveness sin auth a propósito — mismo criterio que el health
            # check de whisper-proxy.
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"tts-piper ok")

        def do_POST(self) -> None:
            if self.path != "/speak":
                self.send_response(404)
                self._cors_headers()
                self.end_headers()
                return

            if not _check_auth(self.headers, auth_token):
                self.send_response(401)
                self.send_header("WWW-Authenticate", "Bearer")
                self._cors_headers()
                self.end_headers()
                return

            if not _check_origin(self.headers, allowed_origin):
                self.send_response(403)
                self._cors_headers()
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
                self._cors_headers()
                self.end_headers()
                self.wfile.write(b"bad request: need {\"text\": ..., \"lang\"?: \"es\"|\"en\"}")
                return

            if len(text) > max_text_length:
                self.send_response(413)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(f"text too long (max {max_text_length} chars)".encode())
                return

            voice_path = voices.get(lang, voices["es"])
            try:
                wav_bytes = _synthesize(piper_bin, voice_path, text)
            except subprocess.CalledProcessError as e:
                self.send_response(500)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(f"piper failed: {e.stderr.decode(errors='replace')}".encode())
                return
            self.send_response(200)
            self._cors_headers()
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

    auth_token = os.environ.get("AUTH_TOKEN", "")
    if not auth_token:
        print("[tts-piper] fatal: falta AUTH_TOKEN en el entorno — no arranco sin auth", file=sys.stderr)
        sys.exit(1)
    allowed_origin = os.environ.get("ALLOWED_ORIGIN", "")
    max_text_length = int(os.environ.get("MAX_TEXT_LENGTH", "2000"))

    voices = {"es": args.voice_es, "en": args.voice_en}
    handler = make_handler(
        voices, args.piper_bin,
        auth_token=auth_token, allowed_origin=allowed_origin, max_text_length=max_text_length,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"[tts-piper] escuchando en http://{args.host}:{args.port} — voces: {voices}")
    server.serve_forever()


if __name__ == "__main__":
    main()
