"""批量提取 raw/ 中所有 PDF 的第一页文本，自动更新 index.json 的 abstract。

跳过已精读的(abstract_source已存在)、DOC、CAJ 文件。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from PyPDF2 import PdfReader


def extract_first_page(filepath: Path) -> str:
    """提取 PDF 第一页文本，清洗后返回。

    清洗规则:
      - 去除逐字间距（中文字符间多余空格）
      - 去除页眉/页脚/免责声明
      - 提取 3-8 句核心摘要
    """
    try:
        reader = PdfReader(str(filepath))
        if len(reader.pages) == 0:
            return ""
        raw = reader.pages[0].extract_text()
        if not raw:
            return ""
    except Exception:
        return ""

    # 1. 去除中文字符间的多余空格（逐字间距）
    text = re.sub(r"(?<=[一-鿿])\s+(?=[一-鿿])", "", raw)
    # 2. 合并多余空白行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 3. 按行拆分
    lines = [l.strip() for l in text.split("\n")]
    # 4. 过滤低信息行
    junk_patterns = [
        r"^请.*阅读.*免责",
        r"^敬请参阅",
        r"^证券研究报告$",
        r"^金融工程$",
        r"^金融工程深度$",
        r"^专题报告",
        r"^量化研究",
        r"^\d{4}年\d{1,2}月\d{1,2}日$",
        r"^[-\s]*\d+[-\s]*$",  # page numbers
        r"^分析师\s",
        r"^联系人\s",
        r"^SAC执业证书",
        r"^执业证书编号",
        r"^[0-9\-]+$",  # phone numbers
        r"^[a-zA-Z0-9_]+@[a-zA-Z0-9]+\.[a-zA-Z]+$",  # emails
        r"^Table_",
        r"^\[Table",
        r"^大盘走势图",
        r"^相关研报",
        r"^海通证券研究所",
        r"^国信证券",
        r"^光大证券",
        r"^华泰联合",
        r"^敬请参阅最后一页",
    ]
    useful = []
    for line in lines:
        if not line or len(line) < 6:
            continue
        skip = False
        for pat in junk_patterns:
            if re.match(pat, line):
                skip = True
                break
        if not skip:
            useful.append(line)

    if not useful:
        return ""

    # 5. 取前 800 字符作为摘要
    result = " ".join(useful)
    if len(result) > 800:
        # 尝试在句子边界截断
        cut = result[:800].rfind("。")
        if cut > 200:
            result = result[:cut + 1]
        else:
            result = result[:800] + "..."
    return result


def main() -> None:
    wiki_dir = Path(__file__).parent.parent
    raw_dir = wiki_dir / "raw"
    idx_path = wiki_dir / "index.json"

    with open(idx_path, encoding="utf-8") as f:
        idx = json.load(f)

    # 搜集待处理的 PDF
    updated = 0
    skipped_no_file = 0
    skipped_bad_format = 0
    skipped_already = 0
    skipped_empty = 0

    for report in idx["reports"]:
        # 跳过已精读的
        if report.get("abstract_source"):
            skipped_already += 1
            continue

        # 跳过非 PDF
        fname = report.get("path", "")
        if not fname.lower().endswith(".pdf"):
            skipped_bad_format += 1
            continue

        filepath = raw_dir / report["path"]
        if not filepath.exists():
            # 尝试用模糊匹配找实际文件
            category = report["path"].split("/")[0]
            cat_dir = raw_dir / category
            found = None
            if cat_dir.exists():
                expected_stem = Path(report["path"]).stem
                for f in cat_dir.iterdir():
                    if f.suffix.lower() == ".pdf" and expected_stem[:20] in f.stem:
                        found = f
                        break
            if found:
                filepath = found
            else:
                skipped_no_file += 1
                continue

        # 提取
        abstract = extract_first_page(filepath)
        if abstract:
            report["abstract"] = abstract
            report["abstract_source"] = "PDF第一页自动提取"
            updated += 1
        else:
            skipped_empty += 1

    # 保存
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)

    total = len(idx["reports"])
    print(f"总报告数: {total}")
    print(f"本次新增: {updated}")
    print(f"已有精读: {skipped_already}")
    print(f"跳过(无文件): {skipped_no_file}")
    print(f"跳过(非PDF): {skipped_bad_format}")
    print(f"跳过(空文本): {skipped_empty}")
    print(f"累计精读: {updated + skipped_already} / {total}")


if __name__ == "__main__":
    main()
