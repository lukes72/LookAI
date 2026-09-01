#!/usr/bin/env python3
"""飞书论文日报发送脚本（机器人模式）。

从 papers_record.xlsx 读取指定日期抓取的论文，生成飞书 Markdown 日报，
并通过 lark-cli 以 user 身份发送到指定用户。

用法:
  python send_feishu.py                 # 发送今天的论文日报
  python send_feishu.py --dry-run       # 只预览消息，不真正发送
  python send_feishu.py --date 2026-08-31
  python send_feishu.py --all           # 发送全部论文（不限于当天）

配置（二选一，优先级从高到低）:
  1. 环境变量 FEISHU_USER_ID
  2. 仓库根目录 feishu_config.json: {"user_id": "ou_xxx"}
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
EXCEL_FILE = BASE_DIR / "papers_record.xlsx"
CONFIG_FILE = BASE_DIR / "feishu_config.json"

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


def resolve_user_id(cfg: dict) -> str:
    user_id = os.environ.get("FEISHU_USER_ID") or cfg.get("user_id", "")
    return str(user_id).strip()


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


def build_markdown(papers: list[dict], target_date: str) -> str:
    n = len(papers)
    lines = [f"📚 **论文日报** | {target_date}", f"共发现 **{n}** 篇新论文", ""]
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
        lines.append("")
    lines.append(
        "PDF 已下载至 papers/，记录已更新至 papers_record.xlsx，网站数据已更新至 viewer/papers_data.json。"
    )
    return "\n".join(lines).strip()


def send_via_lark_cli(markdown: str, user_id: str, dry_run: bool = False) -> bool:
    if dry_run:
        print("[DRY-RUN] 将执行 lark-cli im +messages-send ...")
        print(f"[DRY-RUN] user_id={user_id}, markdown 长度={len(markdown)}")
        print("----- 消息内容预览 -----")
        print(markdown)
        print("------------------------")
        return True

    print(f"[INFO] 正在通过 lark-cli 发送 {len(markdown)} 字符的日报...")
    if sys.platform == "win32":
        # Windows 下 lark-cli 是 npm 全局脚本(.ps1/.cmd)，直接 subprocess 找不到可执行文件，
        # 且 .ps1 受 ExecutionPolicy 限制；用 cmd /c 走 npm 的 .cmd shim 最稳。
        cmd = [
            "cmd", "/c", "lark-cli",
            "im", "+messages-send",
            "--as", "user",
            "--user-id", user_id,
            "--markdown", markdown,
        ]
    else:
        cmd = [
            "lark-cli",
            "im",
            "+messages-send",
            "--as",
            "user",
            "--user-id",
            user_id,
            "--markdown",
            markdown,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"[ERROR] lark-cli 发送失败: {result.stderr or result.stdout}")
        return False
    print("[OK] 已发送到飞书")
    if result.stdout:
        print(result.stdout.strip()[:2000])
    return True

def main() -> None:
    parser = argparse.ArgumentParser(description="发送飞书论文日报")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不发送")
    parser.add_argument("--date", default=date.today().isoformat(), help="指定日期 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="发送全部论文而不是仅当天")
    args = parser.parse_args()

    cfg = load_config()
    user_id = resolve_user_id(cfg)
    if not user_id:
        print("[ERROR] 未配置 FEISHU_USER_ID 或 feishu_config.json 中的 user_id")
        sys.exit(1)

    papers = load_papers()
    if args.all:
        selected = papers
    else:
        selected = [p for p in papers if p.get("crawled_date") == args.date]

    if not selected:
        markdown = f"✅ 今日（{args.date}）未发现新的 LLM 量化论文。"
    else:
        markdown = build_markdown(selected, args.date)

    ok = send_via_lark_cli(markdown, user_id, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
