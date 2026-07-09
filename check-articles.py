#!/usr/bin/env python3
"""Validate article HTML: canonical URLs, local assets, and live npayen.com links."""

import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parent


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for attr in ("href", "src"):
            if attr in attrs:
                self.links.append((tag, attr, attrs[attr]))


def article_number(folder_name: str) -> int:
    return int(folder_name.split("_")[0])


def expected_canonical(num: int) -> str:
    slug = f"{num:02d}" if num < 10 else str(num)
    return f"https://npayen.com/articles/{slug}.html"


def check_live_url(url: str):
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url, method=method, headers={"User-Agent": "Mozilla/5.0 (article-checker)"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, None
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in (403, 405, 501):
                continue
            return exc.code, str(exc)
        except Exception as exc:
            return None, str(exc)
    return None, "unreachable"


def main() -> int:
    articles = sorted(BASE.glob("*/*rticle*.html"))
    issues = 0

    print(f"Checking {len(articles)} articles in {BASE}\n")

    # Canonical + RSS alignment
    print("=== Canonical URLs ===")
    canon_urls = []
    for path in articles:
        num = article_number(path.parent.name)
        expected = expected_canonical(num)
        content = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', content, re.I)
        if not match:
            print(f"  MISSING  {path.relative_to(BASE)}")
            issues += 1
        elif match.group(1) != expected:
            print(f"  WRONG    {path.relative_to(BASE)} -> {match.group(1)} (expected {expected})")
            issues += 1
        else:
            canon_urls.append(match.group(1))
    if issues == 0:
        print("  OK - all canonical URLs match npayen.com feed pattern")

    feed_urls = [expected_canonical(i) for i in range(1, 40)]
    if sorted(canon_urls) != sorted(feed_urls):
        print("  WARN - canonical set does not match articles 01-39")
        issues += 1

    # Local assets
    print("\n=== Local assets ===")
    missing = []
    checked = 0
    for path in articles:
        parser = LinkExtractor()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        for tag, attr, href in parser.links:
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            if href.startswith(("http://", "https://", "//")):
                continue
            checked += 1
            clean = href.replace("\\", "/").split("?")[0].split("#")[0]
            target = (path.parent / clean).resolve()
            if not target.exists():
                missing.append((path.relative_to(BASE), f"{tag}[{attr}]", href))

    if missing:
        issues += len(missing)
        print(f"  FAIL - {len(missing)} missing local references")
        for item in missing:
            print(f"    {item[0]} {item[1]} -> {item[2]}")
    else:
        print(f"  OK - all {checked} local references resolve")

    # Live npayen.com article pages
    print("\n=== Live npayen.com pages ===")
    live_issues = []
    for i in range(1, 40):
        url = expected_canonical(i)
        status, err = check_live_url(url)
        if not status or status >= 400:
            live_issues.append((url, status, err))
    if live_issues:
        issues += len(live_issues)
        for url, status, err in live_issues:
            print(f"  FAIL [{status}] {url} ({err})")
    else:
        print("  OK - articles 01-39 return HTTP 200 on npayen.com")

    # og:url alignment (informational)
    print("\n=== og:url vs canonical (informational) ===")
    mismatches = []
    for path in articles:
        content = path.read_text(encoding="utf-8", errors="replace")
        canon = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', content, re.I)
        og = re.search(r'<meta\s+property="og:url"\s+content="([^"]+)"', content, re.I)
        if canon and og and canon.group(1) != og.group(1):
            mismatches.append(path.relative_to(BASE))
    if mismatches:
        print(f"  INFO - {len(mismatches)} articles still use github.io in og:url")
    else:
        print("  OK - og:url matches canonical")

    print("\n=== Summary ===")
    if issues == 0:
        print("All critical checks passed.")
        return 0
    print(f"{issues} issue(s) found.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
