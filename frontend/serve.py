"""Serve the Election Explorer frontend locally.

    uv run python frontend/serve.py [--port 8000]

A thin wrapper over http.server that pins the MIME types ES modules need
(Windows' registry can map .js to text/plain, which browsers refuse to load
as a module) and disables caching so edits show on reload.
"""

from __future__ import annotations

import argparse
import http.server
import mimetypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    with http.server.ThreadingHTTPServer((args.bind, args.port), Handler) as httpd:
        print(f"Election Explorer at http://{args.bind}:{args.port}/  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
