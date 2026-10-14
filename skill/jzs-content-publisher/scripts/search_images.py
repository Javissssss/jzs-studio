#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Image search & download: Unsplash (env UNSPLASH_ACCESS_KEY),
Pexels (env PEXELS_API_KEY), Openverse (keyless, CC0/CC-BY). Pure stdlib.
Engine fallback chain: unsplash -> pexels -> openverse."""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "jzs-content-publisher/1.0"}


def http_get_json(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def search_openverse(query, count, license_="cc0,by"):
    q = urllib.parse.quote(query)
    url = (
        f"https://api.openverse.org/v1/images/?q={q}&page_size={count}"
        f"&license={license_}&mature=false"
    )
    data = http_get_json(url)
    out = []
    for r in data.get("results", []):
        out.append(
            {
                "source": "openverse",
                "title": r.get("title") or "",
                "creator": r.get("creator") or "",
                "license": r.get("license", ""),
                "license_version": r.get("license_version", ""),
                "url": r.get("url") or "",
                "detail": r.get("detail_url") or "",
                "width": r.get("width"),
                "height": r.get("height"),
            }
        )
    return out


def search_unsplash(query, count, orientation="landscape"):
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        return []
    q = urllib.parse.quote(query)
    url = (
        f"https://api.unsplash.com/search/photos?query={q}&per_page={count}"
        f"&orientation={orientation}&order_by=relevant"
    )
    data = http_get_json(url, {"Authorization": f"Client-ID {key}"})
    out = []
    for r in data.get("results", []):
        out.append(
            {
                "source": "unsplash",
                "title": r.get("alt_description") or "",
                "creator": (r.get("user") or {}).get("name", ""),
                "license": "unsplash",
                "url": (r.get("urls") or {}).get("regular", ""),
                "detail": (r.get("links") or {}).get("html", ""),
            }
        )
    return out


def search_pexels(query, count, orientation="landscape"):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    q = urllib.parse.quote(query)
    url = f"https://api.pexels.com/v1/search?query={q}&per_page={count}&orientation={orientation}"
    data = http_get_json(url, {"Authorization": key})
    out = []
    for r in data.get("photos", []):
        src = r.get("src") or {}
        out.append(
            {
                "source": "pexels",
                "title": r.get("alt") or "",
                "creator": r.get("photographer") or "",
                "license": "pexels",
                "url": src.get("large") or src.get("original") or "",
                "detail": r.get("url") or "",
                "width": r.get("width"),
                "height": r.get("height"),
            }
        )
    return out


def download(url, path, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(path, "wb") as f:
        f.write(r.read())
    return os.path.getsize(path)


def main():
    ap = argparse.ArgumentParser(description="Search and download free-license images")
    ap.add_argument(
        "--query", required=True, help="search keywords (English recommended)"
    )
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--prefix", default="img", help="output filename prefix")
    ap.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "openverse", "unsplash", "pexels"],
    )
    ap.add_argument(
        "--no-download", action="store_true", help="only print JSON metadata"
    )
    args = ap.parse_args()

    results = []
    engine = args.engine
    if engine in ("auto", "unsplash"):
        try:
            results = search_unsplash(args.query, args.count)
            if results:
                engine = "unsplash"
        except Exception as e:
            print(f"[warn] unsplash failed: {e}", file=sys.stderr)
    if not results and engine in ("auto", "pexels"):
        try:
            results = search_pexels(args.query, args.count)
            if results:
                engine = "pexels"
        except Exception as e:
            print(f"[warn] pexels failed: {e}", file=sys.stderr)
    if not results and engine in ("auto", "openverse"):
        try:
            results = search_openverse(args.query, args.count)
            if results:
                engine = "openverse"
        except Exception as e:
            print(f"[warn] openverse failed: {e}", file=sys.stderr)

    if not results:
        print(
            "[error] no results; fallback: use figure_cards.py HTML visuals",
            file=sys.stderr,
        )
        return 1

    os.makedirs(args.out, exist_ok=True)
    saved = []
    for i, r in enumerate(results[: args.count], 1):
        item = dict(r)
        if not args.no_download and r.get("url"):
            ext = ".jpg"
            u = r["url"].split("?")[0].lower()
            for e in (".png", ".webp", ".jpeg", ".jpg"):
                if u.endswith(e):
                    ext = e
                    break
            path = os.path.join(args.out, f"{args.prefix}_{i:02d}{ext}")
            try:
                size = download(r["url"], path)
                item["file"] = path
                item["bytes"] = size
            except Exception as e:
                print(f"[warn] download failed {r['url']}: {e}", file=sys.stderr)
        saved.append(item)

    print(json.dumps({"engine": engine, "images": saved}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
