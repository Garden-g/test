#!/usr/bin/env python3
"""Build a compact fact pack for the Accio Agent narrative step.

This script does not call any LLM provider and does not require an API key. It
only extracts stable facts from report_data.json and analysis.json, so the
executing Accio Agent can write natural boss-facing copy from a clean, bounded
input instead of reading the full workbook schema.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]

SHEET_NAMES = [
    "老板结论",
    "投产看板",
    "询盘质量",
    "订单产出",
    "商品节奏",
    "关键词与广告机会",
    "业务员回复与跟进",
    "数据质量检查",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        Parsed arguments containing input and output file paths.

    Raises:
        SystemExit: argparse raises this when required arguments are missing.
    """

    parser = argparse.ArgumentParser(description="Build Agent narrative brief JSON.")
    parser.add_argument("--report-data", required=True, help="Path to report_data.json.")
    parser.add_argument("--analysis", required=True, help="Path to analysis.json.")
    parser.add_argument("--output", required=True, help="Path to narrative_brief.json.")
    return parser.parse_args(argv)


def load_json(path: Path) -> JsonDict:
    """Load a JSON object from disk.

    Args:
        path: UTF-8 JSON file path.

    Returns:
        Parsed dictionary, or an empty dictionary when the root is not an object.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is malformed.
    """

    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def clean_text(value: Any, limit: int = 180) -> str:
    """Convert a raw value into one safe, short line for Agent reading.

    Args:
        value: Raw value from normalized report data or analysis output.
        limit: Maximum number of characters to keep.

    Returns:
        One-line text. Missing values become "未返回".

    Raises:
        No exceptions are intentionally raised.
    """

    if value in (None, ""):
        return "未返回"
    if isinstance(value, dict):
        for key in ("def", "name", "title", "label", "value"):
            if value.get(key) not in (None, ""):
                return clean_text(value.get(key), limit)
        text = "；".join(f"{k}:{clean_text(v, 40)}" for k, v in list(value.items())[:6])
    elif isinstance(value, list):
        text = "；".join(clean_text(item, 40) for item in value[:8])
    else:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def compact_rows(rows: Any, keys: list[str], limit: int = 10) -> list[JsonDict]:
    """Project a list of dictionaries to only the fields useful for narrative.

    Args:
        rows: Candidate row list.
        keys: Field names to preserve.
        limit: Maximum rows to include.

    Returns:
        List of compact dictionaries with empty fields removed.

    Raises:
        No exceptions are intentionally raised.
    """

    if not isinstance(rows, list):
        return []
    compacted: list[JsonDict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = {key: clean_text(row.get(key)) for key in keys if row.get(key) not in (None, "", [])}
        if item:
            compacted.append(item)
        if len(compacted) >= limit:
            break
    return compacted


def metric_map(report_data: JsonDict, analysis: JsonDict) -> JsonDict:
    """Collect headline metrics that the Agent may mention.

    Args:
        report_data: Normalized report data.
        analysis: Diagnosis output.

    Returns:
        Dictionary of stable metrics and statuses.

    Raises:
        No exceptions are intentionally raised.
    """

    inquiry_summary = ((report_data.get("inquiry_quality") or {}).get("summary") or {})
    service = report_data.get("service") or {}
    quality = report_data.get("data_quality") or {}
    product_q = analysis.get("products_quadrant") or {}
    keyword_q = analysis.get("keywords_quadrant") or {}
    return {
        "executive_status": analysis.get("executive_status") or {},
        "one_liner": analysis.get("one_liner"),
        "inquiry_total": inquiry_summary.get("total_records"),
        "high_quality_inquiries": inquiry_summary.get("high_quality"),
        "low_quality_inquiries": inquiry_summary.get("low_quality"),
        "pending_info_inquiries": inquiry_summary.get("pending_info"),
        "p0_inquiry_risks": inquiry_summary.get("p0"),
        "p1_inquiry_risks": inquiry_summary.get("p1"),
        "first_5min_reply_rate_30d": service.get("first_5min_reply_rate_30d"),
        "avg_reply_time_30d": service.get("avg_reply_time_30d"),
        "reply_over_12h_count": service.get("reply_over_12h_count"),
        "not_follow_count": service.get("not_follow_count"),
        "product_quadrant_counts": {key: len(value or []) for key, value in product_q.items()},
        "keyword_quadrant_counts": {key: len(value or []) for key, value in keyword_q.items()},
        "data_quality_status": quality.get("status"),
        "data_coverage_rate": quality.get("coverage_rate"),
        "red_data_checks": quality.get("red_count"),
        "yellow_data_checks": quality.get("yellow_count"),
        "blocking_flags": quality.get("blocking_flags") or {},
        "degraded_conclusions": quality.get("degraded_conclusions") or [],
    }


def build_brief(report_data: JsonDict, analysis: JsonDict) -> JsonDict:
    """Build the complete Agent narrative brief.

    Args:
        report_data: Normalized report data generated by prepare_data.py.
        analysis: Diagnostic output generated by analyze.py.

    Returns:
        A compact JSON object for the Accio Agent to rewrite into narrative.json.

    Raises:
        No exceptions are intentionally raised.
    """

    products = analysis.get("products_quadrant") or {}
    keywords = analysis.get("keywords_quadrant") or {}
    inquiry = report_data.get("inquiry_quality") or {}
    quality = report_data.get("data_quality") or {}
    return {
        "version": 1,
        "purpose": "给正在执行 skill 的 Accio Agent 使用；请基于这些事实写 narrative.json，不调用第三方 LLM API。",
        "period": report_data.get("meta") or {},
        "required_sheets": SHEET_NAMES,
        "hard_rules": [
            "不能改数字，不能编造缺失字段，不能把未返回写成 0。",
            "订单金额或广告花费缺失时，只能写回报算不清，不能硬算 ROI。",
            "不要出现 Markdown、原始 JSON、内部错误、工具异常、外部 CRM 品牌名或不稳定增长工具包字样。",
            "同类商品、关键词、询盘动作要合并成自然话，不要逐行复制模板。",
        ],
        "headline_metrics": metric_map(report_data, analysis),
        "boss_actions": compact_rows(
            analysis.get("boss_top5_actions") or analysis.get("top3_actions") or [],
            ["priority", "object_type", "object_name", "why", "action", "owner", "due", "review_metric"],
            5,
        ),
        "inquiry_examples": compact_rows(
            inquiry.get("records") or [],
            ["customer", "country", "seller", "buyer_level", "product_or_need", "purchase_signals", "quality", "priority", "quality_reason", "suggested_action"],
            18,
        ),
        "product_examples": {
            key: compact_rows(rows, ["product_id", "title", "imps", "fb_num", "fb_rate_str", "why", "actions"], 8)
            for key, rows in products.items()
        },
        "keyword_examples": {
            key: compact_rows(rows, ["keyword", "clk", "cost", "inquiry", "rank_label", "source_tag", "why", "actions"], 8)
            for key, rows in keywords.items()
        },
        "seller_reply": report_data.get("service") or {},
        "data_quality": {
            "status": quality.get("status"),
            "coverage_rate": quality.get("coverage_rate"),
            "checks_detail": compact_rows(
                quality.get("checks_detail") or [],
                ["module", "check", "status", "usable", "period", "issue", "impact", "action"],
                30,
            ),
            "quarantined_modules": quality.get("quarantined_modules") or [],
        },
        "output_contract": {
            "boss_conclusion": {
                "weekly_battle": "老板结论页本周战况",
                "business_status": "经营状态",
                "data_confidence": "数据可信度",
                "biggest_risk": "最大风险",
                "biggest_opportunity": "最大机会",
                "boss_decision": "老板要拍板的事",
            },
            "sheet_summaries": {
                sheet: {"老板口径": "", "关键证据": "", "今天动作": "", "下周复查": ""}
                for sheet in SHEET_NAMES
                if sheet != "老板结论"
            },
            "top_actions": [{"action": "", "evidence": "", "decision": "", "review": ""}],
            "row_rewrites": {
                "product_actions": {},
                "keyword_actions": {},
                "inquiry_actions": {},
                "seller_actions": {},
            },
        },
    }


def main(argv: list[str]) -> int:
    """Run the narrative brief builder.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        Process exit code. Zero means success.

    Raises:
        No exceptions escape intentionally; errors are printed as JSON to stderr.
    """

    args = parse_args(argv)
    report_data = load_json(Path(args.report_data))
    analysis = load_json(Path(args.analysis))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_brief(report_data, analysis), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)
