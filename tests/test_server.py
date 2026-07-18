"""服务端测试：真实 HTTP 往返、鉴权、护栏。"""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from hermes_poetry import config


def _ensure():
    if not (config.RULES_INITIAL_DIR / "initial_rules.jsonl").exists():
        from hermes_poetry.orchestrator import run_pipeline
        run_pipeline(verbose=False)


class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure()
        from hermes_poetry.server.http_server import make_handler
        from hermes_poetry.server.service import ServiceContext
        cls.service = ServiceContext()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.service))
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
            return r.status, json.loads(r.read() or b"{}")

    def _post(self, path, body):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())

    def test_health_and_readyz(self):
        code, d = self._get("/api/health")
        self.assertEqual(code, 200)
        self.assertTrue(d["ok"])
        code, d = self._get("/readyz")
        self.assertEqual(code, 200)
        self.assertTrue(d["ready"])

    def test_search_api(self):
        code, d = self._post("/api/search", {"query": "床前明月光", "top_k": 3})
        self.assertEqual(code, 200)
        self.assertTrue(d["hits"])

    def test_static_and_traversal(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as r:
            html = r.read().decode()
        self.assertIn("诗海", html)
        self.assertIn("/app.js", html)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/%2e%2e/config.py")
        self.assertEqual(ctx.exception.code, 404)
        ctx.exception.close()

    def test_body_too_large(self):
        big = "x" * (300 * 1024)
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/search",
            data=json.dumps({"query": big}).encode(),
            headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 413)
        ctx.exception.close()

    def test_top_k_clamped(self):
        code, d = self._post("/api/search", {"query": "明月", "top_k": 99999})
        self.assertEqual(code, 200)
        self.assertLessEqual(len(d["hits"]), 50)

    def test_council_over_http(self):
        code, d = self._post("/api/council", {"question": "明月的意象"})
        self.assertEqual(code, 200)
        self.assertIn("timeline", d)
        self.assertTrue(d["citation_report"]["ok"])


class TestAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure()
        import os
        os.environ["HERMES_SERVER_TOKEN"] = "sekrit"
        from hermes_poetry.server.http_server import make_handler
        from hermes_poetry.server.service import ServiceContext
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ServiceContext()))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        import os
        del os.environ["HERMES_SERVER_TOKEN"]
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_401_without_token_200_with(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/stats")
        self.assertEqual(ctx.exception.code, 401)
        ctx.exception.close()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/stats",
                                     headers={"Authorization": "Bearer sekrit"})
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.status, 200)
        # 探针免鉴权
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/livez") as r:
            self.assertEqual(r.status, 200)


if __name__ == "__main__":
    unittest.main()
