# -*- coding: utf-8 -*-
"""Offline tests for the pure parts of the pipeline (no network, no browser).
Run: python -m unittest discover -s tests -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import brief, config, enrich, media, render, state  # noqa: E402

SAMPLE_AI = """好的，下面是稿件。
===WECHAT_START===
# 降息之后，普通人的钱该放哪

导语第一段，
接着第二行。

## 一、发生了什么

第一段内容。

第二段内容。

## 二、怎么看

- 要点一
- 要点二

## 三、怎么做

结论段落。

[CLOSE]
你怎么看？评论区聊聊。
[/CLOSE]
===WECHAT_END===
===XHS_TITLE_START===
降息了，钱放哪？
===XHS_TITLE_END===
===XHS_START===
小红书正文
===XHS_END===
===XHS_TAGS_START===
#理财 #降息
===XHS_TAGS_END===
===FIGURES_START===
[{"id":"f1","caption":"三层决策框架","nodes":["a","b"]}]
===FIGURES_END===
"""


class TestParse(unittest.TestCase):
    def test_parse_blocks(self):
        p = brief.parse_ai_output(SAMPLE_AI)
        self.assertTrue(p["parsed_ok"])
        self.assertIn("## 一、发生了什么", p["wechat_md"])
        self.assertEqual(p["xhs_titles"], ["降息了，钱放哪？"])
        self.assertEqual(len(p["figures"]), 1)

    def test_parse_plain_text_fallback(self):
        p = brief.parse_ai_output("# 标题\n\n纯正文，没有任何标记")
        self.assertFalse(p["parsed_ok"])
        self.assertIn("纯正文", p["wechat_md"])


class TestEnrich(unittest.TestCase):
    def test_injects_cover_and_unused_figure(self):
        md = brief.parse_ai_output(SAMPLE_AI)["wechat_md"]
        figs = [{"id": "f1", "caption": "三层决策框架"}]
        out, rep = enrich.ensure_placeholders(md, "降息之后理财", figs, [])
        self.assertTrue(out.startswith("[MOOD:stock market"))
        self.assertEqual(out.count("[FIGURE:f1]"), 1)
        self.assertEqual(rep["figure"], 1)
        self.assertGreaterEqual(rep["mood"], 1)

    def test_idempotent_when_already_placed(self):
        md = "[MOOD:x] 封面\n\n## 一\n\n[FIGURE:f1] 图\n\n正文"
        out, rep = enrich.ensure_placeholders(md, "", [{"id": "f1"}], [])
        self.assertEqual(out, md)
        self.assertEqual(rep, {"mood": 0, "figure": 0, "chart": 0})

    def test_leftovers_go_before_close(self):
        md = "正文\n\n[CLOSE]\n结尾\n[/CLOSE]"
        out, _ = enrich.ensure_placeholders(md, "", [], [{"id": "c1", "caption": "走势"}])
        self.assertLess(out.index("[CHART:c1]"), out.index("[CLOSE]"))


class TestRender(unittest.TestCase):
    def setUp(self):
        self.md = brief.parse_ai_output(SAMPLE_AI)["wechat_md"]

    def test_no_duplicate_paragraphs(self):
        html_str, _ = render.render_article(self.md, [], {"title": "t"})
        for para in ("第一段内容。", "第二段内容。", "结论段落。"):
            self.assertEqual(html_str.count(para), 1, para)

    def test_cjk_soft_wrap_no_space(self):
        html_str, _ = render.render_article(self.md, [], {"title": "t"})
        self.assertIn("导语第一段，接着第二行。", html_str)

    def test_meta(self):
        _, meta = render.render_article(self.md, [], {"title": "降息之后"})
        self.assertEqual(meta["sections"], 3)
        self.assertTrue(meta["has_close"])
        self.assertTrue(meta["finance"])

    def test_lead_skips_cover_image(self):
        md, _ = enrich.ensure_placeholders(self.md, "降息", [], [])
        _, meta = render.render_article(md, [], {"title": "t"})
        self.assertTrue(meta["lead"].startswith("导语第一段"), meta["lead"])

    def test_disclaimer_only_for_finance(self):
        fin, _ = render.render_article(self.md, [], {"title": "降息之后"})
        non, m2 = render.render_article("## 一\n\n写作方法", [], {"title": "如何写作"})
        self.assertIn(config.FINANCE_DISCLAIMER, fin)
        self.assertNotIn(config.FINANCE_DISCLAIMER, non)
        self.assertFalse(m2["finance"])


class TestApi(unittest.TestCase):
    """Flask routes end-to-end, isolated workspace, no media generation."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls._orig = config.WORKSPACE_DIR
        config.WORKSPACE_DIR = cls.tmp
        import app as app_mod

        cls.client = app_mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        config.WORKSPACE_DIR = cls._orig
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_flow_and_export(self):
        c = self.client
        pid = c.post("/api/projects", json={"title": "t"}).get_json()["project"]["id"]
        r = c.post(f"/api/projects/{pid}/topics/fetch", json={"mode": "direct", "title": "降息之后"}).get_json()
        self.assertTrue(r["ok"])
        r = c.post(f"/api/projects/{pid}/topic/select", json={"topic": r["candidates"][0]}).get_json()
        self.assertTrue(r["ok"])
        self.assertTrue(c.post(f"/api/projects/{pid}/brief/generate", json={}).get_json()["ok"])
        r = c.post(f"/api/projects/{pid}/draft/fill", json={"ai_output": SAMPLE_AI}).get_json()
        self.assertTrue(r["ok"])
        self.assertEqual(r["enriched"]["figure"], 1)
        r = c.post(f"/api/projects/{pid}/render", json={}).get_json()
        self.assertTrue(r["ok"], r)
        self.assertIn("html_url", r["project"]["render"])
        z = c.get(f"/api/projects/{pid}/export.zip")
        self.assertEqual(z.status_code, 200)
        self.assertEqual(z.mimetype, "application/zip")

    def test_errors_are_json(self):
        r = self.client.get("/api/projects/does-not-exist")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.get_json()["ok"])
        r = self.client.post("/api/projects/nope/render", json={})
        self.assertEqual(r.status_code, 404)



class TestWriter(unittest.TestCase):
    """Built-in writer against a fake OpenAI-compatible server."""

    @classmethod
    def setUpClass(cls):
        import http.server, threading

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                cls.seen = (self.path, self.headers.get("Authorization"), body)
                out = json.dumps({"choices": [{"message": {"content": SAMPLE_AI}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        cls.tmp = tempfile.mkdtemp(prefix="jzs_test_")
        cls._orig = config.WORKSPACE_DIR
        config.WORKSPACE_DIR = cls.tmp
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.env = {
            "JZS_LLM_BASE_URL": f"http://127.0.0.1:{cls.srv.server_port}/v1",
            "JZS_LLM_API_KEY": "test-key",
            "JZS_LLM_MODEL": "fake-model",
        }

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        config.WORKSPACE_DIR = cls._orig
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_write_full_draft(self):
        from unittest import mock
        import app as app_mod

        with mock.patch.dict(os.environ, self.env):
            c = app_mod.app.test_client()
            self.assertTrue(c.get("/api/health").get_json()["llm"]["configured"])
            pid = c.post("/api/projects", json={}).get_json()["project"]["id"]
            c.post(f"/api/projects/{pid}/topic/select", json={"topic": {"title": "降息之后", "summary": ""}})
            r = c.post(f"/api/projects/{pid}/draft/write?wait=1", json={"engine": "api"}).get_json()
            proj = c.get(f"/api/projects/{pid}").get_json()["project"]
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["result"]["parsed_ok"])
        self.assertEqual(r["result"]["model"], "fake-model")
        self.assertIn("## ", proj["draft"]["wechat_md"])
        path, auth, body = self.seen
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(auth, "Bearer test-key")
        self.assertIn("降息之后", body["messages"][1]["content"])

    def test_unconfigured_is_readable_error(self):
        from unittest import mock
        import app as app_mod

        with mock.patch.dict(os.environ, {"JZS_LLM_API_KEY": ""}):
            c = app_mod.app.test_client()
            pid = c.post("/api/projects", json={}).get_json()["project"]["id"]
            c.post(f"/api/projects/{pid}/topic/select", json={"topic": {"title": "x"}})
            res = c.post(f"/api/projects/{pid}/draft/write", json={"engine": "api"})
        self.assertEqual(res.status_code, 502)
        self.assertIn("未配置写作模型", res.get_json()["error"])


FAKE_CODEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_codex.py")


class TestEngines(unittest.TestCase):
    """Codex write, background jobs, manual slot upload, AI image API, settings."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="jzs_test_")
        cls._orig = config.WORKSPACE_DIR
        config.WORKSPACE_DIR = cls.tmp
        import app as app_mod

        cls.c = app_mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        config.WORKSPACE_DIR = cls._orig
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _project_with_draft(self):
        c = self.c
        pid = c.post("/api/projects", json={}).get_json()["project"]["id"]
        c.post(f"/api/projects/{pid}/topic/select", json={"topic": {"title": "降息之后"}})
        c.post(f"/api/projects/{pid}/draft/fill", json={"ai_output": SAMPLE_AI})
        return pid

    def test_codex_write_sync(self):
        from unittest import mock

        env = {"JZS_CODEX_CMD": FAKE_CODEX, "FAKE_CODEX_TEXT": SAMPLE_AI}
        with mock.patch.dict(os.environ, env):
            pid = self.c.post("/api/projects", json={}).get_json()["project"]["id"]
            self.c.post(f"/api/projects/{pid}/topic/select", json={"topic": {"title": "降息之后"}})
            r = self.c.post(f"/api/projects/{pid}/draft/write?wait=1", json={"engine": "codex"}).get_json()
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["model"], "Codex")
        self.assertTrue(r["result"]["parsed_ok"])
        self.assertTrue(any("fake codex" in l for l in r["log"]))

    def test_codex_failure_and_missing(self):
        from unittest import mock

        with mock.patch.dict(os.environ, {"JZS_CODEX_CMD": FAKE_CODEX, "FAKE_CODEX_RC": "3"}):
            pid = self.c.post("/api/projects", json={}).get_json()["project"]["id"]
            self.c.post(f"/api/projects/{pid}/topic/select", json={"topic": {"title": "x"}})
            res = self.c.post(f"/api/projects/{pid}/draft/write?wait=1", json={"engine": "codex"})
        self.assertEqual(res.status_code, 502)
        self.assertIn("退出码 3", res.get_json()["error"])
        with mock.patch.dict(os.environ, {"JZS_CODEX_CMD": ""}), mock.patch("shutil.which", return_value=None):
            res = self.c.post(f"/api/projects/{pid}/draft/write", json={"engine": "codex"})
        self.assertEqual(res.status_code, 502)
        self.assertIn("codex", res.get_json()["error"])

    def test_codex_cmd_resolution(self):
        from unittest import mock
        from core import codex

        with mock.patch.dict(os.environ, {"JZS_CODEX_CMD": "npx -y @openai/codex"}), \
                mock.patch("shutil.which", side_effect=lambda n: "C:/n/npx.cmd" if n == "npx" else None):
            self.assertEqual(codex.find_cmd(), ["C:/n/npx.cmd", "-y", "@openai/codex"])
        with mock.patch.dict(os.environ, {"JZS_CODEX_CMD": "nope-cmd"}), mock.patch("shutil.which", return_value=None):
            self.assertIsNone(codex.find_cmd())

    def test_background_job_polling(self):
        import time
        from unittest import mock

        env = {"JZS_CODEX_CMD": FAKE_CODEX, "FAKE_CODEX_TEXT": SAMPLE_AI}
        with mock.patch.dict(os.environ, env):
            pid = self.c.post("/api/projects", json={}).get_json()["project"]["id"]
            self.c.post(f"/api/projects/{pid}/topic/select", json={"topic": {"title": "降息之后"}})
            job = self.c.post(f"/api/projects/{pid}/draft/write", json={"engine": "codex"}).get_json()["job"]
            for _ in range(100):
                j = self.c.get(f"/api/jobs/{job['id']}").get_json()["job"]
                if j["status"] != "running":
                    break
                time.sleep(0.1)
        self.assertEqual(j["status"], "done", j)
        self.assertGreater(j["log_total"], 2)

    def test_manual_slot_upload_survives(self):
        import base64

        pid = self._project_with_draft()
        s = state.load(pid)
        s["media"] = {"cards": []}
        phs = media.parse_placeholders(s["draft"]["wechat_md"])
        s["media"]["manifest"] = [dict(p, ok=False, file=None, log="x", engine="stock") for p in phs]
        state.save(pid, s)
        png = base64.b64encode(PNG_1PX).decode()
        r = self.c.post(f"/api/projects/{pid}/media/slot/1", json={"data_url": "data:image/png;base64," + png}).get_json()
        self.assertTrue(r["ok"], r)
        m = r["project"]["media"]["manifest"][0]
        self.assertEqual(m["engine"], "manual")
        self.assertTrue(m["url"].endswith(".png"))
        import app as app_mod

        self.assertIn(phs[0]["raw"], app_mod._keep_manual(state.load(pid)))
        bad = self.c.post(f"/api/projects/{pid}/media/slot/1", json={"data_url": "data:text/html;base64,PGI+"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.c.post(f"/api/projects/{pid}/media/slot/99", json={}).status_code, 400)

    def test_imagegen_against_fake_server(self):
        import base64, http.server, threading
        from unittest import mock
        from core import imagegen

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                H.body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                out = json.dumps({"data": [{"b64_json": base64.b64encode(PNG_1PX).decode()}]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        env = {"JZS_IMG_BASE_URL": f"http://127.0.0.1:{srv.server_port}/v1", "JZS_IMG_API_KEY": "k", "JZS_IMG_MODEL": "m"}
        try:
            with mock.patch.dict(os.environ, env):
                path = imagegen.generate("一只猫", os.path.join(self.tmp, "img"))
        finally:
            srv.shutdown()
        self.assertTrue(path.endswith(".png") and os.path.getsize(path) == len(PNG_1PX))
        self.assertEqual(H.body["model"], "m")
        with mock.patch.dict(os.environ, {"JZS_IMG_API_KEY": ""}):
            with self.assertRaises(RuntimeError):
                imagegen.generate("x", os.path.join(self.tmp, "y"))

    def test_settings_never_leak_secrets(self):
        from unittest import mock
        from core import settings

        envf = os.path.join(self.tmp, ".env")
        with open(envf, "w", encoding="utf-8") as f:
            f.write("# keep me\nJZS_LLM_MODEL=old\n")
        with mock.patch.dict(os.environ, {}), mock.patch.object(settings, "ENV_PATH", envf):
            settings.update({"JZS_LLM_MODEL": "new", "JZS_LLM_API_KEY": "sk-secret", "EVIL": "x"})
            pub = {f["key"]: f for f in settings.public()}
            self.assertEqual(pub["JZS_LLM_MODEL"]["value"], "new")
            self.assertEqual(pub["JZS_LLM_API_KEY"]["value"], "")
            self.assertTrue(pub["JZS_LLM_API_KEY"]["set"])
            settings.update({"JZS_LLM_API_KEY": ""})  # empty = keep
            self.assertEqual(os.environ["JZS_LLM_API_KEY"], "sk-secret")
            with self.assertRaises(ValueError):
                settings.update({"JZS_BRAND": "a\nEVIL=1"})
            r = self.c.get("/api/settings").get_json()
            self.assertNotIn("sk-secret", json.dumps(r))
        with open(envf, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("# keep me", text)
        self.assertIn("JZS_LLM_MODEL=new", text)
        self.assertNotIn("EVIL", text)

    def test_brand_is_configurable(self):
        from unittest import mock

        with mock.patch.dict(os.environ, {"JZS_BRAND": "测试栏目"}):
            md = brief.generate_brief({"title": "t"})
            html_out, _ = render.render_article("# 标题\n\n正文", [], {"title": "t"})
        self.assertIn("测试栏目", md)
        self.assertNotIn("巨人之上", md)
        self.assertIn("测试栏目", html_out)


PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


if __name__ == "__main__":
    unittest.main()
