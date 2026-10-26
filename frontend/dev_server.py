#!/usr/bin/env python3
"""Development server: serves frontend/ and proxies /api/, /admin/ and /static/ to Django.

Everything shares one origin (http://localhost:5173), so session cookies and CSRF work
without CORS. The proxy forwards the original Host header so Django's CSRF origin check
matches. Binds to 127.0.0.1 only. For development, not production.

    python frontend/dev_server.py [--port 5173] [--backend http://127.0.0.1:8000]
"""
import argparse
import http.client
import http.server
import json
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROXIED_PREFIXES = ("/api/", "/admin/", "/static/")
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}


class Handler(http.server.SimpleHTTPRequestHandler):
    backend_host = "127.0.0.1"
    backend_port = 8000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404, "Directory listing disabled")

    def _proxied(self):
        return self.path.startswith(PROXIED_PREFIXES)

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        try:
            conn = http.client.HTTPConnection(self.backend_host, self.backend_port, timeout=30)
            conn.request(self.command, self.path, body, headers)
            resp = conn.getresponse()
            data = resp.read()
        except OSError:
            payload = json.dumps(
                {"error": {"code": "backend_unreachable",
                           "message": f"Cannot reach the backend at {self.backend_host}:{self.backend_port}. Is Django running?"}}
            ).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(resp.status, resp.reason)
        for key, value in resp.getheaders():  # keeps repeated Set-Cookie headers
            if key.lower() not in HOP_BY_HOP and key.lower() != "content-length":
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)
        conn.close()

    def do_GET(self):
        self._proxy() if self._proxied() else super().do_GET()

    def do_HEAD(self):
        self._proxy() if self._proxied() else super().do_HEAD()

    def _write(self):
        if self._proxied():
            self._proxy()
        else:
            self.send_error(405, "Method not allowed")

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _write


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    target = urllib.parse.urlsplit(args.backend)
    Handler.backend_host = target.hostname or "127.0.0.1"
    Handler.backend_port = target.port or 80
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Frontend: http://localhost:{args.port}/  ->  proxying /api/ to {args.backend}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
