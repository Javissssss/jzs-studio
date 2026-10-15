# -*- coding: utf-8 -*-
"""Offline tests for the pure parts of the pipeline (no network, no browser).
Run: python -m unittest discover -s tests -v
"""

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import brief, config, enrich, render  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
