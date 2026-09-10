"""Wrapper de auth/CORS delante de whisper-server (que no tiene forma propia
de autenticar: sin flags de auth, ACAO:* hardcodeado en su código fuente).
Stdlib puro, mismo estilo que services/tts-piper/server.py: valida
Authorization/Origin y reenvía solo POST /inference al whisper-server
interno (127.0.0.1, puerto no publicado al host).

Uso: python proxy.py --host 0.0.0.0 --port 8090
     --upstream-host 127.0.0.1 --upstream-port 9091
Requiere AUTH_TOKEN en el entorno — sin él, el proceso no arranca (falla
ruidoso en vez de quedar como proxy abierto sin auth).
"""

import argparse
import hmac
import http.client
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_FORWARD_HEADERS = ("Content-Type", "Content-Length")


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


def make_handler(*, upstream_host: str, upstream_port: int, auth_token: str, allowed_origin: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            print(f"[whisper-proxy] {self.address_string()} {fmt % args}")

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
            if self.path != "/":
                self.send_response(404)
                self._cors_headers()
                self.end_headers()
                return
            # Health check propio, sin auth ni forward — whisper-server no
            # necesariamente implementa GET / con el mismo contrato.
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"whisper-stt ok")

        def do_POST(self) -> None:
            if self.path != "/inference":
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
            body = self.rfile.read(length) if length else b""

            conn = http.client.HTTPConnection(upstream_host, upstream_port, timeout=120)
            try:
                forward_headers = {
                    k: v for k, v in self.headers.items() if k in _FORWARD_HEADERS
                }
                conn.request("POST", "/inference", body=body, headers=forward_headers)
                upstream_resp = conn.getresponse()
                upstream_body = upstream_resp.read()
            except OSError as e:
                self.send_response(502)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(f"whisper-stt upstream error: {e}".encode())
                return
            finally:
                conn.close()

            self.send_response(upstream_resp.status)
            self._cors_headers()
            for header, value in upstream_resp.getheaders():
                if header.lower() not in ("access-control-allow-origin", "transfer-encoding", "connection"):
                    self.send_header(header, value)
            self.end_headers()
            self.wfile.write(upstream_body)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, required=True)
    args = parser.parse_args()

    auth_token = os.environ.get("AUTH_TOKEN", "")
    if not auth_token:
        print("[whisper-proxy] fatal: falta AUTH_TOKEN en el entorno — no arranco sin auth", file=sys.stderr)
        sys.exit(1)
    allowed_origin = os.environ.get("ALLOWED_ORIGIN", "")

    handler = make_handler(
        upstream_host=args.upstream_host,
        upstream_port=args.upstream_port,
        auth_token=auth_token,
        allowed_origin=allowed_origin,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"[whisper-proxy] escuchando en http://{args.host}:{args.port} -> upstream {args.upstream_host}:{args.upstream_port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
