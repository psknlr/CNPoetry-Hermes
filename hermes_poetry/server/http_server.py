"""纯标准库 Web 服务：ThreadingHTTPServer + 静态单页应用。

安全基线（承袭伤寒-赫尔墨斯）：
  * HERMES_SERVER_TOKEN 设置时启用 Bearer 鉴权并关闭开放 CORS；
  * 请求体上限 256KB；整数参数钳位（算力护栏）；
  * 静态文件路径穿越防护；异常只回 trace_id 不回内部细节；
  * /livez /readyz 免鉴权探针分离。
"""
from __future__ import annotations

import hmac
import json
import os
import re
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .. import health
from .service import ServiceContext

STATIC_DIR = Path(__file__).parent / "static"
MAX_BODY_BYTES = 256 * 1024
_INT_CAPS = {"top_k": (1, 50), "limit": (1, 200)}

ROUTES: List[Tuple[str, "re.Pattern", str]] = []  # (method, pattern, service_method)


def route(method: str, pattern: str, fn_name: str) -> None:
    ROUTES.append((method, re.compile(f"^{pattern}$"), fn_name))


route("GET", "/api/health", "health")
route("GET", "/api/stats", "stats")
route("GET", "/api/skills", "skills")
route("GET", "/api/tools", "tools")
route("POST", "/api/search", "search")
route("POST", "/api/poem", "poem")
route("POST", "/api/match", "match")
route("POST", "/api/differential", "differential")
route("POST", "/api/teach", "teach")
route("POST", "/api/imagery", "imagery")
route("POST", "/api/cipai", "cipai")
route("POST", "/api/author", "author")
route("POST", "/api/rhyme", "rhyme")
route("POST", "/api/intertext", "intertext")
route("POST", "/api/scene", "scene")
route("POST", "/api/gloss", "gloss")
route("POST", "/api/research", "research")
route("POST", "/api/ask", "ask")
route("POST", "/api/council", "run_council")
route("POST", "/api/compose", "compose")
route("POST", "/api/compose_gufeng", "compose_gufeng")
route("POST", "/api/check_draft", "check_draft")
route("POST", "/api/feihua", "feihua")
route("POST", "/api/tool", "tool")

_MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".svg": "image/svg+xml"}


def make_handler(service: ServiceContext):
    auth_token = os.environ.get("HERMES_SERVER_TOKEN", "")

    class Handler(BaseHTTPRequestHandler):
        server_version = "HermesCNPoetry"

        def log_message(self, fmt, *args):  # 安静日志
            pass

        def _send(self, code: int, payload: Dict, content_type="application/json; charset=utf-8"):
            blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(blob)))
            if not auth_token:
                self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(blob)

        def do_OPTIONS(self):
            self.send_response(204)
            if not auth_token:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def _dispatch(self, method: str):
            path = self.path.split("?", 1)[0]
            if path == "/livez":
                return self._send(200, health.livez())
            if path == "/readyz":
                r = health.readyz()
                return self._send(200 if r["ready"] else 503, r)
            if method == "GET" and not path.startswith("/api/"):
                return self._serve_static(path)
            # 鉴权
            if auth_token and path != "/api/health":
                supplied = ""
                auth = self.headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    supplied = auth[7:]
                supplied = supplied or self.headers.get("X-Auth-Token", "")
                if not hmac.compare_digest(supplied.encode(), auth_token.encode()):
                    return self._send(401, {"error": "unauthorized"})
            body = self._json_body(method)
            if body is None:
                return  # 已回错误
            for m, pat, fn_name in ROUTES:
                if m == method and pat.match(path):
                    try:
                        result = getattr(service, fn_name)(body) if m == "POST" \
                            else getattr(service, fn_name)()
                        return self._send(200, result)
                    except health.MissingAssetsError as exc:
                        return self._send(503, {"error": "not_ready", "detail": str(exc)})
                    except Exception:
                        trace_id = uuid.uuid4().hex[:12]
                        print(f"[error {trace_id}]", file=sys.stderr)
                        import traceback
                        traceback.print_exc()
                        return self._send(500, {"error": "internal_error", "trace_id": trace_id})
            self._send(404, {"error": "not_found"})

        def _json_body(self, method: str) -> Optional[Dict]:
            if method != "POST":
                return {}
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                length = 0
            if length > MAX_BODY_BYTES:
                self._send(413, {"error": "body_too_large"})
                return None
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid_json"})
                return None
            if not isinstance(body, dict):
                body = {}
            for k, (lo, hi) in _INT_CAPS.items():
                if k in body:
                    try:
                        body[k] = max(lo, min(hi, int(body[k])))
                    except (TypeError, ValueError):
                        body[k] = lo
            return body

        def _serve_static(self, path: str):
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (STATIC_DIR / rel).resolve()
            root = STATIC_DIR.resolve()
            # 以父目录关系判定（startswith 字符串前缀会放行 static_evil 类同级目录）
            if not (target == root or root in target.parents) or not target.is_file():
                return self._send(404, {"error": "not_found"})
            blob = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", _MIME.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, warm: bool = True) -> None:
    service = ServiceContext()
    if not service.ready():
        print("规则库未生成：请先运行 `python3 -m hermes_poetry pipeline`", file=sys.stderr)
        sys.exit(2)
    if warm:
        service.warm()
    httpd = ThreadingHTTPServer((host, port), make_handler(service))
    from ..llm import get_client
    token_note = "（Bearer 鉴权已开启）" if os.environ.get("HERMES_SERVER_TOKEN") else ""
    print(f"诗海赫尔墨斯控制台: http://{host}:{port}/  后端={get_client().backend}{token_note}",
          file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
