#!/usr/bin/env python3
"""飞书论文日报发送脚本（机器人模式）。

从 papers_record.xlsx 读取指定日期抓取的论文，生成飞书日报，
并直接调用飞书开放平台 API 以应用机器人身份发送给指定用户。

用法:
  python send_feishu.py                 # 发送今天的论文日报
  python send_feishu.py --dry-run       # 只预览消息，不真正发送
  python send_feishu.py --date 2026-08-31
  python send_feishu.py --all           # 发送全部论文（不限于当天）

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
from datetime import date
from monitor import is_relevant as monitor_is_relevant
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
EXCEL_FILE = BASE_DIR / "papers_record.xlsx"
CONFIG_FILE = BASE_DIR / "feishu_config.json"

FEISHU_BASE = "https://open.feishu.cn/open-apis"

EXCEL_HEADERS = [
    "arxiv_id",
    "title",
    "authors",
    "affiliations",
    "published_date",
    "categories",
    "abstract",
    "summary_cn",
    "pdf_filename",
    "crawled_date",
    "notes",
]


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


def load_papers() -> list[dict]:
    """从 Excel 读取全部论文（含空值清洗）。"""
    if not EXCEL_FILE.exists():
        return []

    from openpyxl import load_workbook

    wb = load_workbook(EXCEL_FILE, read_only=True)
    if "Papers" not in wb.sheetnames:
        return []
    ws = wb["Papers"]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(h) if h is not None else "" for h in rows[0]]
    idx = {name: i for i, name in enumerate(headers)}

    def cell(row, name: str) -> str:
        i = idx.get(name)
        if i is None or i >= len(row):
            return ""
        v = row[i]
        return "" if v is None else str(v).replace("\n", " ").strip()

    papers: list[dict] = []
    for row in rows[1:]:
        papers.append({h: cell(row, h) for h in EXCEL_HEADERS})
    return papers


def paper_is_relevant(p: dict) -> bool:
    """复用 monitor.py 的领域黑名单，过滤临床/医疗/生物/农业/金融/审计等应用方向。"""
    return monitor_is_relevant({
        "title": p.get("title", ""),
        "summary": p.get("abstract", ""),
        "categories": p.get("categories", ""),
    })


def paper_lines(papers: list[dict]) -> list[str]:
    """生成日报正文各行（不含标题行）。"""
    lines = [f"共发现 **{len(papers)}** 篇新论文"]
    for p in papers:
        title = p.get("title") or "(无标题)"
        lines.append(f"**{title}**")
        lines.append(f"arXiv: {p.get('arxiv_id', '')} | {p.get('published_date', '')}")
        if p.get("authors"):
            lines.append(f"作者: {p['authors']}")
        if p.get("affiliations"):
            lines.append(f"单位: {p['affiliations']}")
        if p.get("arxiv_id"):
            lines.append(f"PDF: https://arxiv.org/pdf/{p['arxiv_id']}")
        if p.get("summary_cn"):
            lines.append(f"摘要: {p['summary_cn']}")
    return lines


def build_markdown(papers: list[dict], target_date: str) -> str:
    lines = [f"📚 **论文日报** | {target_date}"] + paper_lines(papers)
    lines.append("")
    lines.append(
        "PDF 已下载至 papers/，记录已更新至 papers_record.xlsx，网站数据已更新至 viewer/papers_data.json。"
    )
    return "\n".join(lines).strip()


def line_to_elements(line: str) -> list[dict]:
    """把一行文本转换为飞书 post 富文本元素。"""
    line = line.replace("**", "")
    if line.startswith("PDF: "):
        url = line[len("PDF: "):].strip()
        return [
            {"tag": "text", "text": "PDF: "},
            {"tag": "a", "text": url, "href": url},
        ]
    return [{"tag": "text", "text": line}]


def build_post_content(papers: list[dict], target_date: str) -> dict:
    content = []
    for line in paper_lines(papers):
        elements = line_to_elements(line)
        if elements:
            content.append(elements)
    return {
        "zh_cn": {
            "title": f"📚 论文日报 | {target_date}",
            "content": content,
        }
    }


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    url = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal"
    resp = requests.post(
        url, json={"app_id": app_id, "app_secret": app_secret}, timeout=30
    )
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


def send_feishu(
    markdown: str,
    post_content: dict,
    user_id: str,
    app_id: str,
    app_secret: str,
    dry_run: bool = False,
) -> bool:
    if dry_run:
        print("[DRY-RUN] 将调用飞书开放平台 API 发送 post 消息")
        print(f"[DRY-RUN] user_id={user_id}, 内容长度={len(markdown)}")
        print("----- 消息内容预览 -----")
        print(markdown)
        print("------------------------")
        return True

    print("[INFO] 正在获取 tenant_access_token ...")
    token = get_tenant_access_token(app_id, app_secret)
    print(f"[INFO] 正在发送 {len(markdown)} 字符的日报 ...")
    result = send_post_message(token, user_id, post_content)
    print(f"[OK] 已发送到飞书: message_id={result.get('message_id', '')}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="发送飞书论文日报")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不发送")
    parser.add_argument("--date", default=date.today().isoformat(), help="指定日期 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="发送全部论文而不是仅当天")
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

    papers = load_papers()
    if args.all:
        selected = papers
    else:
        selected = [p for p in papers if p.get("crawled_date") == args.date]

    before = len(selected)
    selected = [p for p in selected if paper_is_relevant(p)]
    if len(selected) != before:
        print(f"[FILTER] 已过滤 {before - len(selected)} 篇非目标方向论文（临床/医疗/生物/农业/金融/审计等）")

    if not selected:
        markdown = f"✅ 今日（{args.date}）未发现新的 AI 论文。"
        post_content = {
            "zh_cn": {
                "title": f"📚 论文日报 | {args.date}",
                "content": [[{"tag": "text", "text": markdown}]],
            }
        }
    else:
        markdown = build_markdown(selected, args.date)
        post_content = build_post_content(selected, args.date)

    ok = send_feishu(markdown, post_content, user_id, app_id, app_secret, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()