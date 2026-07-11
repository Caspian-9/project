"""从 index.json 批量生成 wiki Markdown 页面。

为每个有摘要的报告创建 sources/{id}.md，并更新 _index.md 和 _log.md。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def slugify(text: str) -> str:
    """中文标题 → 英文 slug（取拼音首字母或直接用 id）"""
    return text.replace("/", "-").replace(" ", "-")[:60]


def gen_source_page(report: dict[str, Any]) -> str:
    """生成单个源文件摘要 Markdown 页面。"""
    title = report.get("title", report.get("path", "Unknown"))
    source = report.get("source", "未知")
    date = report.get("date", "")
    path = report.get("path", "")
    abstract = report.get("abstract", "")
    keywords = report.get("keywords", [])
    category = report.get("category", "")
    subcategory = report.get("subcategory", "")
    status = report.get("status", "unknown")
    has_real_abstract = bool(report.get("abstract_source"))

    tags = ", ".join(keywords[:6]) if keywords else ""
    ingest_note = ""
    if has_real_abstract:
        ingest_note = f"ingested_at: {datetime.now().strftime('%Y-%m-%d')}"
    else:
        ingest_note = "ingested_at: pending"

    # 相关实体猜测（基于关键词）
    related_entities = _guess_entities(keywords, abstract)

    page = f"""---
id: {report['id']}
source: {source}
date: {date}
type: source
category: {category}
subcategory: {subcategory}
status: {'ingested' if has_real_abstract else 'pending'}
{ingest_note}
tags: [{tags}]
---

# {title}

- **来源**: {source}
- **日期**: {date}
- **原始文件**: `raw/{path}`
- **分类**: {category} / {subcategory}
- **关键词**: {tags}

## 摘要

{abstract if abstract else '_待提取 — 原始文件为 DOC/CAJ 格式，PyPDF2 无法读取。请手动阅读后补充。_'}

## 涉及的主题
"""
    for entity_type, entity_name in related_entities:
        page += f"- {entity_type}: [[{entity_name}]]\n"

    if not related_entities:
        page += "\n_待补充 — ingest 完整报告后自动关联_\n"

    page += f"""
## 相关来源

_待补充 — ingest 更多报告后自动建立交叉引用_
"""
    return page


def _guess_entities(keywords: list[str], abstract: str) -> list[tuple[str, str]]:
    """从关键词和摘要中推测相关实体页面。"""
    entities: list[tuple[str, str]] = []
    kw_lower = " ".join(keywords).lower() + " " + abstract.lower()

    strategy_map = {
        "动量": "strategies/momentum-strategy",
        "反转": "strategies/reversal-strategy",
        "多因子": "strategies/multi-factor-strategy",
        "行业轮动": "strategies/sector-rotation",
        "资金流": "strategies/money-flow-strategy",
        "风格轮动": "strategies/style-rotation",
        "GARP": "strategies/garp-strategy",
        "趋势": "strategies/trend-following",
        "PB-ROE": "strategies/pb-roe-strategy",
        "高频": "strategies/hft-strategy",
        "套期保值": "strategies/hedging-strategy",
    }
    factor_map = {
        "规模因子": "factors/size-factor",
        "成长因子": "factors/growth-factor",
        "质量因子": "factors/quality-factor",
        "估值因子": "factors/value-factor",
        "动量因子": "factors/momentum-factor",
        "盈利因子": "factors/profitability-factor",
        "波动因子": "factors/volatility-factor",
        "市值": "factors/size-factor",
        "ROE": "factors/profitability-factor",
    }
    indicator_map = {
        "KDJ": "indicators/kdj",
        "ADX": "indicators/adx",
        "AROON": "indicators/aroon",
        "CCI": "indicators/cci",
        "EMV": "indicators/emv",
        "CMO": "indicators/cmo",
        "ATR": "indicators/atr",
        "chaikin": "indicators/chaikin-ad",
        "MACD": "indicators/macd",
    }
    concept_map = {
        "IC": "concepts/ic-analysis",
        "因子测试": "concepts/factor-testing",
        "分层回测": "concepts/stratified-backtest",
        "过拟合": "concepts/overfitting",
        "幸存者偏差": "concepts/survivorship-bias",
        "二次确认": "concepts/double-confirmation",
        "信息比": "concepts/information-ratio",
        "夏普": "concepts/sharpe-ratio",
    }

    for kw, link in strategy_map.items():
        if kw.lower() in kw_lower:
            entities.append(("策略", link))
    for kw, link in factor_map.items():
        if kw.lower() in kw_lower:
            entities.append(("因子", link))
    for kw, link in indicator_map.items():
        if kw.lower() in kw_lower:
            entities.append(("技术指标", link))
    for kw, link in concept_map.items():
        if kw.lower() in kw_lower:
            entities.append(("概念", link))

    # 去重
    seen = set()
    unique = []
    for etype, elink in entities:
        if elink not in seen:
            seen.add(elink)
            unique.append((etype, elink))
    return unique[:5]


def gen_index_md(reports: list[dict[str, Any]]) -> str:
    """生成 _index.md 全量导航目录。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 按分类分组
    by_category: dict[str, list[dict[str, Any]]] = {}
    for r in reports:
        cat = r.get("category", "未分类")
        by_category.setdefault(cat, []).append(r)

    ingested = sum(1 for r in reports if r.get("abstract_source"))
    total = len(reports)

    page = f"""# Wiki 导航目录

> 自动维护。每次 ingest 后更新。
> 最后更新: {now}

## 系统页面

| 页面 | 说明 |
|------|------|
| [[overview]] | 知识库全景概述 + 知识地图 |
| [[_schema]] | Wiki 维护规范（给 LLM 看） |
| [[_log]] | 操作日志 |

---
"""

    # 源文件摘要
    page += f"""
## 源文件摘要 (`sources/`)

已 ingest: {ingested} / {total}
"""
    for cat_name, cat_reports in sorted(by_category.items()):
        page += f"\n### {cat_name} ({len(cat_reports)} 篇)\n\n"
        page += "| 页面 | 标题 | 来源 | 日期 | 状态 |\n"
        page += "|------|------|------|------|------|\n"
        for r in sorted(cat_reports, key=lambda x: x.get("date", ""), reverse=True):
            rid = r["id"]
            title = r.get("title", "")[:40]
            source = r.get("source", "")
            date = r.get("date", "")
            status = "已 ingest" if r.get("abstract_source") else "待 ingest"
            page += f"| [[sources/{rid}]] | {title} | {source} | {date} | {status} |\n"

    # 实体页面（占位）
    page += f"""
---

## 策略实体 (`strategies/`)

| 页面 | 状态 |
|------|------|
| [[strategies/momentum-strategy]] | stub |
| [[strategies/reversal-strategy]] | stub |
| [[strategies/multi-factor-strategy]] | stub |
| [[strategies/sector-rotation]] | stub |
| [[strategies/money-flow-strategy]] | stub |
| [[strategies/style-rotation]] | stub |
| [[strategies/garp-strategy]] | stub |
| [[strategies/trend-following]] | stub |
| [[strategies/pb-roe-strategy]] | stub |
| [[strategies/hft-strategy]] | stub |

## 因子实体 (`factors/`)

| 页面 | 状态 |
|------|------|
| [[factors/size-factor]] | stub |
| [[factors/growth-factor]] | stub |
| [[factors/quality-factor]] | stub |
| [[factors/value-factor]] | stub |
| [[factors/momentum-factor]] | stub |
| [[factors/profitability-factor]] | stub |

## 技术指标 (`indicators/`)

| 页面 | 状态 |
|------|------|
| [[indicators/kdj]] | stub |
| [[indicators/adx]] | stub |
| [[indicators/aroon]] | stub |
| [[indicators/cci]] | stub |
| [[indicators/emv]] | stub |
| [[indicators/cmo]] | stub |
| [[indicators/chaikin-ad]] | stub |
| [[indicators/atr]] | stub |

## 概念 (`concepts/`)

| 页面 | 状态 |
|------|------|
| [[concepts/ic-analysis]] | stub |
| [[concepts/factor-testing]] | stub |
| [[concepts/overfitting]] | stub |
| [[concepts/sharpe-ratio]] | stub |
| [[concepts/information-ratio]] | stub |

## 综合分析 (`synthesis/`)

| 页面 | 主题 | 状态 |
|------|------|------|
| [[synthesis/momentum-vs-reversal]] | A股动量 vs 反转 | planned |
| [[synthesis/tech-indicators-comparison]] | 技术指标横向对比 | planned |

---

## 统计

- 源文件摘要: {ingested} / {total}
- 策略实体: 10 (all stub)
- 因子实体: 6 (all stub)
- 技术指标: 8 (all stub)
- 概念: 5 (all stub)
- 综合分析: 2 (planned)
"""
    return page


def gen_log_md(prev_log: str, ingested_count: int) -> str:
    """更新日志，追加批量 ingest 记录。"""
    today = datetime.now().strftime("%Y-%m-%d")
    new_entry = f"""
## [{today}] batch-ingest | 批量生成源文件摘要页

- 从 index.json 批量生成 {ingested_count} 篇 sources/ 页面
- 每页包含 PDF 第一页提取的摘要 + 关键词推测的实体关联
- 更新 _index.md 全量导航目录
- 9 篇 DOC/CAJ 待手动处理后 ingest
"""
    return prev_log.rstrip() + "\n" + new_entry


def main() -> None:
    wiki_dir = Path(__file__).parent.parent / "wiki"
    idx_path = Path(__file__).parent.parent / "index.json"

    with open(idx_path, encoding="utf-8") as f:
        idx = json.load(f)

    reports = idx["reports"]
    sources_dir = wiki_dir / "sources"

    # 1. 生成 source 页面
    created = 0
    for r in reports:
        page = gen_source_page(r)
        out_path = sources_dir / f"{r['id']}.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page)
        created += 1

    print(f"已生成 {created} 个 source 页面")

    # 2. 生成 _index.md
    index_md = gen_index_md(reports)
    with open(wiki_dir / "_index.md", "w", encoding="utf-8") as f:
        f.write(index_md)
    print("已更新 _index.md")

    # 3. 更新 _log.md
    log_path = wiki_dir / "_log.md"
    prev_log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    ingested = sum(1 for r in reports if r.get("abstract_source"))
    new_log = gen_log_md(prev_log, ingested)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(new_log)
    print("已更新 _log.md")

    print(f"\n完成: {ingested}/{len(reports)} 篇已生成 source 页面")


if __name__ == "__main__":
    main()
