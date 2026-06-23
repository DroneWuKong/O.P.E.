#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


STATIC_DIR = Path(os.environ.get("GUPFLEET_STATIC_DIR", "/var/www/gupfleet"))
LISTEN_HOST = os.environ.get("GUPFLEET_LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("GUPFLEET_LISTEN_PORT", "8080"))
REPO = os.environ.get("GUPFLEET_REPO", "DroneWuKong/Ai-Project")
NODE_URLS = {
    "gupa": os.environ.get("GUPFLEET_NODE_GUPA", "http://10.0.0.252:9100"),
    "gupb": os.environ.get("GUPFLEET_NODE_GUPB", "http://10.0.0.130:9100"),
    "gupc": os.environ.get("GUPFLEET_NODE_GUPC", "http://10.0.0.85:9100"),
}

GITHUB_PROXY_FUNCTION = """async function ghGet(path) {
  const r = await fetch('/api/github?path=' + encodeURIComponent(path), {
    signal: AbortSignal.timeout(8000)
  });
  if(!r.ok) throw new Error(r.status);
  return r.json();
}
"""


def resolve_github_token() -> str:
    for env_name in ("GUPFLEET_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value

    for name in ("index.html", "me.html"):
        path = STATIC_DIR / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"const GH_TOKEN = '([^']+)';", text)
        if match:
            return match.group(1)
    return ""


GITHUB_TOKEN = resolve_github_token()


def rewrite_dashboard_html(text: str) -> str:
    text = re.sub(r"const GH_TOKEN = '([^']*)';", "const GH_TOKEN = '';", text)
    for node_id in NODE_URLS:
        text = re.sub(
            rf"\{{id:'{node_id}', url:'[^']+'\}}",
            f"{{id:'{node_id}', url:'/api/node/{node_id}'}}",
            text,
        )
    text = re.sub(
        r"async function ghGet\(path\) \{.*?\n\}",
        GITHUB_PROXY_FUNCTION.strip(),
        text,
        flags=re.S,
    )
    return text


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "GupFleetDashboard/1.0"

    def do_GET(self) -> None:
        self.handle_request(send_body=True)

    def do_HEAD(self) -> None:
        self.handle_request(send_body=False)

    def handle_request(self, send_body: bool) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/node/"):
            self.handle_node_api(parsed.path.rsplit("/", 1)[-1], send_body=send_body)
            return
        if parsed.path == "/api/github":
            self.handle_github_api(parsed.query, send_body=send_body)
            return
        self.handle_static(parsed.path, send_body=send_body)

    def handle_node_api(self, node_id: str, send_body: bool) -> None:
        url = NODE_URLS.get(node_id)
        if not url:
            self.send_error(HTTPStatus.NOT_FOUND, "node not found")
            return
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                body = response.read()
        except Exception as exc:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"error": "node_unreachable", "node": node_id, "detail": str(exc)})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def handle_github_api(self, query: str, send_body: bool) -> None:
        params = urllib.parse.parse_qs(query)
        path = (params.get("path") or [""])[0]
        if not path.startswith("/repos/"):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_path"})
            return
        url = "https://api.github.com" + path
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        if GITHUB_TOKEN:
            request.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                body = response.read()
                status = response.status
                content_type = response.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            body = exc.read() or json.dumps({"error": "github_http_error", "status": exc.code}).encode()
            status = exc.code
            content_type = exc.headers.get("Content-Type", "application/json")
        except Exception as exc:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"error": "github_unreachable", "detail": str(exc)})
            return

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def handle_static(self, raw_path: str, send_body: bool) -> None:
        path = raw_path or "/"
        if path == "/":
            file_path = STATIC_DIR / "index.html"
        else:
            cleaned = path.lstrip("/")
            file_path = (STATIC_DIR / cleaned).resolve()
            if not str(file_path).startswith(str(STATIC_DIR.resolve())):
                self.send_error(HTTPStatus.FORBIDDEN, "forbidden")
                return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
            return

        body = file_path.read_bytes()
        content_type = "application/octet-stream"
        if file_path.suffix == ".html":
            body = rewrite_dashboard_html(body.decode("utf-8", "replace")).encode("utf-8")
            content_type = "text/html; charset=utf-8"
        elif file_path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif file_path.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif file_path.suffix == ".json":
            content_type = "application/json"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), DashboardHandler)
    print(f"serving gupfleet dashboard on {LISTEN_HOST}:{LISTEN_PORT} from {STATIC_DIR}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
