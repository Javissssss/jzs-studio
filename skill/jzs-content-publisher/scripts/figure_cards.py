#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render knowledge figure cards (flow/compare/checklist/timeline) to PNG.
Templates: ../templates/figure/<kind>.html with placeholder /*__DATA__*/.
Data JSON schemas:
  flow:     {"title":str,"subtitle":str,"steps":[{"label":str,"desc":str}]}
  compare:  {"title":str,"subtitle":str,"left":{"name":str,"items":[str]},"right":{...}}
  checklist:{"title":str,"subtitle":str,"items":[{"text":str,"note":str}]}
  timeline: {"title":str,"subtitle":str,"events":[{"date":str,"text":str}]}
Usage: python figure_cards.py --kind flow --data data.json --out fig.png [--width 1080]
"""

import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(HERE, "..", "templates", "figure")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--kind", required=True, choices=["flow", "compare", "checklist", "timeline"]
    )
    ap.add_argument(
        "--data", required=True, help="JSON file path or inline JSON string"
    )
    ap.add_argument("--out", required=True, help="output PNG path")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--scale", type=int, default=2)
    args = ap.parse_args()

    tpl_path = os.path.join(TPL_DIR, f"{args.kind}.html")
    if not os.path.exists(tpl_path):
        print(f"[error] template missing: {tpl_path}", file=sys.stderr)
        return 1
    with open(tpl_path, "r", encoding="utf-8") as f:
        tpl = f.read()

    if os.path.exists(args.data):
        with open(args.data, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(args.data)

    html = tpl.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False))

    tmp = os.path.join(tempfile.gettempdir(), f"jzs_fig_{args.kind}.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[error] playwright not installed; or open the html manually: " + tmp,
            file=sys.stderr,
        )
        return 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    url = "file:///" + os.path.abspath(tmp).replace("\\", "/")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(
            viewport={"width": args.width, "height": 800},
            device_scale_factor=args.scale,
        )
        pg.goto(url)
        pg.wait_for_load_state("networkidle")
        el = pg.query_selector("#figure")
        if not el:
            print("[error] #figure element not found in template", file=sys.stderr)
            b.close()
            return 1
        el.screenshot(path=args.out)
        b.close()
    print(f"[ok] {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
