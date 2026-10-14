#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Screenshot XHS cards from a single HTML file.
Each card element must have id=card1..cardN, sized 1080x1440.
Usage: python xhs_screenshot.py --html cards.html --out ./out --count 5 [--names a,b,c]
"""

import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True, help="path to cards html (file:// loaded)")
    ap.add_argument("--out", required=True, help="output dir for PNGs")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument(
        "--names", default="", help="comma-separated card names for filenames"
    )
    ap.add_argument("--scale", type=int, default=2, help="device_scale_factor")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[error] playwright not installed: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    html_path = os.path.abspath(args.html).replace("\\", "/")
    os.makedirs(args.out, exist_ok=True)
    names = (
        [n.strip() for n in args.names.split(",") if n.strip()] if args.names else []
    )

    ok = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(
            viewport={"width": 1080, "height": 1440}, device_scale_factor=args.scale
        )
        pg.goto(f"file:///{html_path}")
        pg.wait_for_load_state("networkidle")
        for i in range(1, args.count + 1):
            sel = f"#card{i}"
            el = pg.query_selector(sel)
            if not el:
                print(f"[warn] {sel} not found, skip")
                continue
            h = el.evaluate("e => e.scrollHeight")
            if h > 1440:
                print(
                    f"[warn] {sel} overflow: scrollHeight={h} > 1440, content will be clipped"
                )
            name = names[i - 1] if i - 1 < len(names) else f"card{i}"
            path = os.path.join(args.out, f"{i:02d}_{name}.png")
            el.screenshot(path=path)
            print(f"[ok] {path}")
            ok += 1
        b.close()

    print(f"done: {ok}/{args.count} cards")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
