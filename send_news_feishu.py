#!/usr/bin/env python3
"""飞书 AI 新闻日报发送脚本。

从 news_items.json 读取已生成中文总结的新闻条目，以应用机器人身份
发送「新模型 / 新技术 / 大公司动态」日报到飞书。

用法:
  python send_news_feishu.py              # 发送 news_items.json 中已总结的新闻
  python send_news_feishu.py --dry-run    # 只预览消息，不真正发送
  python send_news_feishu.py --json 路径  # 指定输入 JSON（默认 news_items.json）

配置（优先级从高到低）:
  环境变量 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_USER_ID
  或仓库根目录 feishu_config.json:
    {"app_id": "cli_xxx", "app_secret": "xxx", "user_id": "ou_xxx"}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "feishu_config.json"
DEFAULT_JSON = BASE_DIR / "news_items.json"

FEISHU_BASE = "https://open.feishu.cn/open-apis"

SOURCE_NAMES = {
    "openai.com": "OpenAI",
    "huggingface.co": "Hugging Face",
    "blog.google": "Google",
    "deepmind.google": "DeepMind",
    "techcrunch.com": "TechCrunch",
    "theverge.com": "The Verge",
    "venturebeat.com": "VentureBeat",
    "technologyreview.com": "MIT Tech Review",
    "hub.baai.ac.cn": "智源社区",
    "aiera.com.cn": "新智元",
}


def load_config() -> dict:
    cfg: dict = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] 读取 feishu_config.json 失败: {e}")
    return cfg


def resolve_setting(env_name: str, cfg_key: str, cfg: dict) -> str:
    return str(os.environ.get(env_name) or cfg.get(cfg_key, "")).strip()


def source_name(url: str) -> str:
    host = url.replace("https://", "").replace("http://", "").split("/")[0]
    for key, name in SOURCE_NAMES.items():
        if key in host:
            return name
    return host


def fmt_date(published: str) -> str:
    """把 ISO 时间转成日期字符串（本地时区）。"""
    if not published:
        return ""
    try:
        dt = datetime.fromisoformat(published)
        return dt.astimezone().date().isoformat()
    except Exception:
        return published[:10]


def load_news(json_path: Path) -> list[dict]:
    if not json_path.exists():
        return []
    data = json.loads(json_path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    # 只发送已经生成中文总结的条目
    items = [it for it in items if (it.get("summary_cn") or "").strip()]
    items.sort(key=lambda x: x.get("published", ""), reverse=True)
    return items


def build_markdown(items: list[dict], target_date: str) -> str:
    lines = [
        f"📰 AI 新闻日报 | {target_date}",
        f"共 {len(items)} 条 · 新模型 / 新技术 / 大公司动态",
        "",
    ]
    for i, it in enumerate(items, 1):
        title = it.get("title", "").strip()
        src = source_name(it.get("source", ""))
        date = fmt_date(it.get("published", ""))
        summary = it.get("summary_cn", "").strip()
        url = it.get("url", "").strip()
        lines.append(f"【{i}】{title}")
        lines.append(f"来源：{src} | {date}")
        if summary:
            lines.append(f"💡 {summary}")
        if url:
            lines.append(f"🔗 原文：{url}")
        lines.append("")
    return "\n".join(lines).strip()


def line_to_elements(line: str) -> list[dict]:
    if line.startswith("🔗 原文："):
        url = line[len("🔗 原文："):].strip()
        return [
            {"tag": "text", "text": "🔗 原文："},
            {"tag": "a", "text": url, "href": url},
        ]
    return [{"tag": "text", "text": line}]


def build_post_content(items: list[dict], target_date: str) -> dict:
    content: list[list[dict]] = []

    def add_line(line: str) -> None:
        elements = line_to_elements(line)
        if elements:
            content.append(elements)

    add_line(f"📰 AI 新闻日报 | {target_date}")
    add_line(f"共 {len(items)} 条 · 新模型 / 新技术 / 大公司动态")
    add_line("")

    for i, it in enumerate(items, 1):
        title = it.get("title", "").strip()
        src = source_name(it.get("source", ""))
        date = fmt_date(it.get("published", ""))
        summary = it.get("summary_cn", "").strip()
        url = it.get("url", "").strip()
        add_line(f"【{i}】{title}")
        add_line(f"来源：{src} | {date}")
        if summary:
            add_line(f"💡 {summary}")
        if url:
            add_line(f"🔗 原文：{url}")
        add_line("")

    return {
        "zh_cn": {
            "title": f"📰 AI 新闻日报 | {target_date}",
            "content": content,
        }
    }


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    url = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": app_id, "app_secret": app_secret}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
    return data["tenant_access_token"]


def send_post_message(token: str, user_id: str, post_content: dict) -> dict:
    url = f"{FEISHU_BASE}/im/v1/messages?receive_id_type=open_id"
    payload = {
        "receive_id": user_id,
        "msg_type": "post",
        "content": json.dumps(post_content, ensure_ascii=False),
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"发送消息失败: {data}")
    return data.get("data", {})


def main() -> None:
    parser = argparse.ArgumentParser(description="发送飞书 AI 新闻日报")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不发送")
    parser.add_argument("--json", default=str(DEFAULT_JSON), help="输入 JSON 路径")
    args = parser.parse_args()

    cfg = load_config()
    app_id = resolve_setting("FEISHU_APP_ID", "app_id", cfg)
    app_secret = resolve_setting("FEISHU_APP_SECRET", "app_secret", cfg)
    user_id = resolve_setting("FEISHU_USER_ID", "user_id", cfg)

    if not app_id or not app_secret:
        print("[ERROR] 未配置 FEISHU_APP_ID / FEISHU_APP_SECRET（或 feishu_config.json 中的 app_id/app_secret）")
        sys.exit(1)
    if not user_id:
        print("[ERROR] 未配置 FEISHU_USER_ID 或 feishu_config.json 中的 user_id")
        sys.exit(1)

    items = load_news(Path(args.json))
    target_date = datetime.now().astimezone().date().isoformat()

    if not items:
        markdown = "✅ 今日没有新的 AI 新闻。"
        post_content = {
            "zh_cn": {
                "title": f"📰 AI 新闻日报 | {target_date}",
                "content": [[{"tag": "text", "text": markdown}]],
            }
        }
    else:
        markdown = build_markdown(items, target_date)
        post_content = build_post_content(items, target_date)

    if args.dry_run:
        print("[DRY-RUN] 将调用飞书开放平台 API 发送 post 消息")
        print(f"[DRY-RUN] user_id={user_id}, 内容长度={len(markdown)}")
        print("----- 消息内容预览 -----")
        print(markdown)
        print("------------------------")
        return

    print("[INFO] 正在获取 tenant_access_token ...")
    token = get_tenant_access_token(app_id, app_secret)
    print(f"[INFO] 正在发送 {len(markdown)} 字符的新闻日报 ...")
    result = send_post_message(token, user_id, post_content)
    print(f"[OK] 已发送到飞书: message_id={result.get('message_id', '')}")


if __name__ == "__main__":
    main()
