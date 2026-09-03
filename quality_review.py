#!/usr/bin/env python3
"""Local quality checks for papers and news before a Feishu send.

The checks are deliberately conservative: missing source material or an
incomplete LLM result blocks a real send. This module does not call any
network API and never handles credentials.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PLACEHOLDER_MARKERS = (
    "todo",
    "tbd",
    "待补",
    "待处理",
    "未生成",
    "未完成",
    "生成失败",
    "调用失败",
    "error",
    "exception",
)

HIGH_RISK_PATTERNS = (
    re.compile(r"全球首个", re.IGNORECASE),
    re.compile(r"彻底解决", re.IGNORECASE),
    re.compile(r"性能提升\s*\d+(?:\.\d+)?\s*倍", re.IGNORECASE),
    re.compile(r"(?:行业|全球)(?:最大|最强|领先)", re.IGNORECASE),
    re.compile(r"超越(?:了)?\s*[^，。；;]+模型", re.IGNORECASE),
    re.compile(r"登顶", re.IGNORECASE),
    re.compile(r"显著提升", re.IGNORECASE),
)


def _text(value: Any) -> str:
    return str(value or "").replace("\x00", " ").strip()


def _is_http_url(value: Any) -> bool:
    parsed = urlparse(_text(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_placeholder(value: Any) -> bool:
    text = _text(value).lower()
    return not text or any(marker in text for marker in PLACEHOLDER_MARKERS)


def _risk_warnings(text: str, item_id: str) -> list[str]:
    warnings: list[str] = []
    for pattern in HIGH_RISK_PATTERNS:
        if pattern.search(text):
            warnings.append(
                f"{item_id}: 总结包含高风险断言“{pattern.pattern}”，需要人工核对原文。"
            )
    return warnings


def review_papers(papers: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    items_needing_review: list[str] = []

    for index, paper in enumerate(papers, start=1):
        item_id = _text(paper.get("arxiv_id")) or f"paper-{index}"
        title = _text(paper.get("title"))
        abstract = _text(paper.get("abstract") or paper.get("summary"))
        summary = _text(paper.get("summary_cn"))
        pdf_url = paper.get("pdf_url") or f"https://arxiv.org/pdf/{item_id}"

        if not _text(paper.get("arxiv_id")):
            errors.append(f"{item_id}: 缺少 arxiv_id。")
        if not title:
            errors.append(f"{item_id}: 缺少论文标题。")
        if not abstract:
            errors.append(f"{item_id}: 缺少原始摘要，无法核对中文总结。")
        if not _is_http_url(pdf_url):
            errors.append(f"{item_id}: PDF URL 无效：{_text(pdf_url)}")
        if _is_placeholder(summary):
            errors.append(f"{item_id}: 中文总结为空或仍是占位/错误文本。")
        else:
            warnings.extend(_risk_warnings(summary, item_id))
            if warnings and warnings[-1].startswith(item_id + ":"):
                items_needing_review.append(item_id)

        if not _text(paper.get("affiliations")):
            warnings.append(f"{item_id}: 作者单位为空，建议人工确认。")

    return {
        "ok": not errors,
        "kind": "papers",
        "checked": len(papers),
        "errors": errors,
        "warnings": warnings,
        "items_needing_review": sorted(set(items_needing_review)),
    }


def review_news(items: list[dict[str, Any]], source_errors: list[str] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    items_needing_review: list[str] = []

    source_errors = [str(error) for error in (source_errors or []) if str(error).strip()]
    if source_errors:
        errors.append(f"新闻源抓取失败 {len(source_errors)} 个：" + " | ".join(source_errors))

    for index, item in enumerate(items, start=1):
        item_id = _text(item.get("id")) or f"news-{index}"
        title = _text(item.get("title"))
        source = _text(item.get("source"))
        url = _text(item.get("url"))
        source_text = _text(item.get("summary_short") or item.get("summary"))
        summary = _text(item.get("summary_cn"))

        if not title:
            errors.append(f"{item_id}: 缺少新闻标题。")
        if not source:
            errors.append(f"{item_id}: 缺少新闻来源。")
        if not _is_http_url(url):
            errors.append(f"{item_id}: 原文 URL 无效：{url}")
        if not source_text:
            errors.append(f"{item_id}: 缺少新闻原始摘要或描述。")
        if _is_placeholder(summary):
            errors.append(f"{item_id}: 中文总结为空或仍是占位/错误文本。")
        else:
            item_warnings = _risk_warnings(summary, item_id)
            warnings.extend(item_warnings)
            if item_warnings:
                items_needing_review.append(item_id)

    return {
        "ok": not errors,
        "kind": "news",
        "checked": len(items),
        "errors": errors,
        "warnings": warnings,
        "items_needing_review": sorted(set(items_needing_review)),
        "source_errors": source_errors,
    }


def merge_reports(*reports: dict[str, Any]) -> dict[str, Any]:
    errors = [error for report in reports for error in report.get("errors", [])]
    warnings = [warning for report in reports for warning in report.get("warnings", [])]
    needs_review = sorted(
        {
            item_id
            for report in reports
            for item_id in report.get("items_needing_review", [])
        }
    )
    return {
        "ok": not errors,
        "kind": "daily",
        "checked": sum(int(report.get("checked", 0)) for report in reports),
        "errors": errors,
        "warnings": warnings,
        "items_needing_review": needs_review,
        "reports": list(reports),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_review_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
