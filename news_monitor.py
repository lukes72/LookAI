#!/usr/bin/env python3
"""AI 科技新闻采集脚本（RSS 聚合）。

从 news_sources.txt 中的多个 RSS 源抓取最近发布的新模型 / 新技术 / 大公司动态，
去重后输出 news_items.json，供后续 LLM 生成中文总结并推送到飞书。

用法:
  python news_monitor.py                 # 抓取最近 24 小时新闻
  python news_monitor.py --hours 72      # 抓取最近 72 小时
  python news_monitor.py --dry-run       # 只打印，不写文件 / 不更新去重记录

环境变量:
  NEWS_HOURS  默认时间窗口（小时），默认 24
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
SOURCES_FILE = BASE_DIR / "news_sources.txt"
OUTPUT_JSON = BASE_DIR / "news_items.json"
SEEN_FILE = BASE_DIR / "news_seen.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}

REQUEST_TIMEOUT = 20
MAX_ITEMS_PER_SOURCE = 10


def load_sources() -> list[str]:
    if not SOURCES_FILE.exists():
        return []
    out: list[str] = []
    for line in SOURCES_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def load_seen() -> set:
    if not SEEN_FILE.exists():
        return set()
    return set(ln.strip() for ln in SEEN_FILE.read_text(encoding="utf-8").splitlines() if ln.strip())


def item_id(title: str) -> str:
    norm = re.sub(r"\s+", " ", (title or "")).strip().lower()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&#8217;", "'")
        .replace("&#8211;", "-")
        .replace("&nbsp;", " ")
    )
    return re.sub(r"\s+", " ", s).strip()


def parse_pubdate(node: ET.Element, ns: str = "") -> datetime | None:
    for tag in ("pubDate", "published", "updated", "dc:date", "date"):
        el = node.find(f"{{{ns}}}{tag}") if ns else node.find(tag)
        if el is None and ns:
            el = node.find(tag)
        if el is not None and el.text:
            raw = el.text.strip()
            if tag == "pubDate":
                try:
                    dt = parsedate_to_datetime(raw)
                    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
            else:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
    return None


def parse_feed(xml_text: str, source: str, hours: int, seen: set) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    ns = ""
    if root.tag.endswith("feed"):
        ns_match = re.match(r"\{([^}]+)\}", root.tag)
        ns = ns_match.group(1) if ns_match else ""

    def findall_local(node: ET.Element, tag: str) -> list[ET.Element]:
        if ns:
            found = node.findall(f"{{{ns}}}{tag}")
            return found if found else node.findall(tag)
        return node.findall(tag)

    entries: list[ET.Element] = []
    if root.tag.endswith("feed"):  # Atom
        entries = findall_local(root, "entry")
    else:  # RSS 2.0
        channel = root.find("channel")
        if channel is None:
            return []
        entries = channel.findall("item")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items: list[dict] = []
    for entry in entries:
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break

        def get_text(tag: str) -> str:
            el = entry.find(f"{{{ns}}}{tag}") if ns else entry.find(tag)
            if el is None and ns:
                el = entry.find(tag)
            return clean_text(el.text) if el is not None and el.text else ""

        title = get_text("title")
        link = get_text("link")
        summary = get_text("description") or get_text("summary") or get_text("content")
        if not title:
            continue

        # Atom 的 link 可能是属性
        if not link:
            lk = entry.find(f"{{{ns}}}link") if ns else entry.find("link")
            if lk is not None:
                link = (lk.get("href", "") or "").strip()

        pub = parse_pubdate(entry, ns)
        if pub is not None and pub < cutoff:
            continue

        iid = item_id(title)
        if iid in seen:
            continue

        items.append({
            "id": iid,
            "title": title,
            "source": source,
            "url": link,
            "published": pub.isoformat() if pub else "",
            "summary_short": summary[:500],
            "summary_cn": "",
        })

    return items


def parse_hub_time(created: str) -> datetime | None:
    """解析智源社区 "YYYY-MM-DD HH:MM 分享" 格式时间（北京时间）。"""
    m = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})", (created or "").strip())
    if not m:
        return None
    try:
        dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=timezone(timedelta(hours=8)))
    except ValueError:
        return None


def fetch_hub_baai(hours: int, seen: set) -> list[dict]:
    """从智源社区（hub.baai.ac.cn）JSON API 抓取最新 AI 科技动态。"""
    api_url = "https://hub-api.baai.ac.cn/api/v1/story/list"
    headers = dict(HEADERS)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"
    payload = {"sort": "new", "page": 1}
    resp = requests.post(api_url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0 or not isinstance(data.get("data"), list):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items: list[dict] = []
    source_url = "https://hub.baai.ac.cn/"
    for row in data["data"]:
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
        info = row.get("story_info") or {}
        title = clean_text(info.get("title") or "")
        if not title:
            continue
        link = (info.get("url") or "").strip() or source_url
        summary = clean_text(info.get("summary") or info.get("content") or "")
        pub = parse_hub_time(info.get("created_at") or "")
        if pub is not None and pub < cutoff:
            continue
        iid = item_id(title)
        if iid in seen:
            continue
        items.append({
            "id": iid,
            "title": title,
            "source": source_url,
            "url": link,
            "published": pub.isoformat() if pub else "",
            "summary_short": summary[:500],
            "summary_cn": "",
        })
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 科技新闻采集")
    parser.add_argument("--hours", type=int, default=int(os.environ.get("NEWS_HOURS", "24")))
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = parser.parse_args()

    sources = load_sources()
    if not sources:
        print("[ERROR] news_sources.txt 为空或不存在")
        sys.exit(1)

    seen = load_seen()
    all_items: list[dict] = []
    errors: list[str] = []
    for url in sources:
        try:
            if url.startswith("json:"):
                target = url[len("json:"):].strip()
                items = fetch_hub_baai(args.hours, seen)
                if items:
                    print(f"[OK] {target} -> {len(items)} 条")
                    all_items.extend(items)
                else:
                    print(f"[SKIP] {target} -> 0 条")
                continue
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            items = parse_feed(resp.text, url, args.hours, seen)
            if items:
                print(f"[OK] {url} -> {len(items)} 条")
                all_items.extend(items)
            else:
                print(f"[SKIP] {url} -> 0 条")
        except Exception as e:  # noqa: BLE001
            msg = f"{url} -> {type(e).__name__}: {e}"
            errors.append(msg)
            print(f"[FAIL] {msg}")

    # 合并去重 + 排序（新的在前）
    uniq: dict[str, dict] = {}
    for it in all_items:
        uniq.setdefault(it["id"], it)
    items = sorted(uniq.values(), key=lambda x: x.get("published", ""), reverse=True)

    output = {
        "date": datetime.now().astimezone().date().isoformat(),
        "count": len(items),
        "sources_ok": len(sources) - len(errors),
        "sources_failed": len(errors),
        "errors": errors,
        "items": items,
    }

    if args.dry_run:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    OUTPUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if items:
        with open(SEEN_FILE, "a", encoding="utf-8") as f:
            for it in items:
                f.write(it["id"] + "\n")
    print(f"[DONE] 共 {len(items)} 条新闻 -> {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
