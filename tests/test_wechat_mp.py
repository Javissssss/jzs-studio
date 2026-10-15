# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import perspective, wechat_mp  # noqa: E402

MD = """开篇一段。

[MOOD:fed] 图说A

## 01 第一节

**重点**内容
- 列表一
- 列表二

[FIGURE:f1] 框架图

[CLOSE] 金句结尾？评论区聊聊。

行情为已发生的客观描述，不构成任何买卖推荐。
"""


class WechatBodyTest(unittest.TestCase):
    def setUp(self):
        self.man = [
            {"raw": "[MOOD:fed] 图说A", "type": "MOOD", "ok": True, "file": "a.jpg"},
            {"raw": "[FIGURE:f1] 框架图", "type": "FIGURE", "ok": True, "file": "f.png"},
        ]

    def test_inline_styles_images_and_close(self):
        html = wechat_mp.build_body(MD, self.man, lambda m: "https://mmbiz.qpic.cn/" + m["file"])
        self.assertEqual(html.count("<img"), 2)
        self.assertIn("mmbiz.qpic.cn/f.png", html)
        self.assertNotIn("<style", html)
        self.assertNotIn("class=", html)
        self.assertIn("PART 01", html)
        self.assertNotIn("01 第一节", html)  # numbering stripped
        self.assertNotIn("[CLOSE]", html)
        self.assertIn("金句结尾", html)
        self.assertIn("<li", html)
        self.assertIn("font-size:12px", html)  # disclaimer small

    def test_failed_image_skipped(self):
        self.man[0]["ok"] = False
        html = wechat_mp.build_body(MD, self.man, lambda m: "u")
        self.assertEqual(html.count("<img"), 1)

    def test_not_configured(self):
        with mock.patch.dict(os.environ, {"JZS_WX_APPID": "", "JZS_WX_SECRET": ""}):
            self.assertFalse(wechat_mp.is_configured())
            wechat_mp._token.update(v="", exp=0)
            with self.assertRaises(RuntimeError):
                wechat_mp.access_token()

    def test_errcode_hint(self):
        with self.assertRaises(RuntimeError) as cm:
            wechat_mp._check({"errcode": 40164, "errmsg": "invalid ip"}, "x")
        self.assertIn("白名单", str(cm.exception))

    def test_cover_size(self):
        from PIL import Image

        d = tempfile.mkdtemp()
        out = wechat_mp.make_cover(None, "一个很长很长的标题用来测试换行和截断效果到底好不好", os.path.join(d, "c.jpg"), "一稿")
        self.assertEqual(Image.open(out).size, (1800, 766))


class PerspectiveTest(unittest.TestCase):
    def test_missing_skill_is_empty(self):
        with mock.patch.object(perspective, "find_skill", return_value=None):
            self.assertEqual(perspective.brief_block("shifenxiyin", "美联储"), "")

    def test_block_from_local_skill(self):
        d = tempfile.mkdtemp()
        sk = os.path.join(d, "shifenxiyin-perspective")
        os.makedirs(sk)
        with open(os.path.join(sk, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nversion: 999.0\n---\n## 核心心智模型\n钱货双流量\n## 无关\nxx\n")
        with mock.patch.dict(os.environ, {"JZS_PERSPECTIVE_DIR": d}):
            self.assertTrue(perspective.find_skill("shifenxiyin"))
            b = perspective.brief_block("shifenxiyin", "无宏观")
        self.assertIn("钱货双流量", b)
        self.assertNotIn("xx", b)
        self.assertNotIn("宏观数据核查", b)


if __name__ == "__main__":
    unittest.main()
