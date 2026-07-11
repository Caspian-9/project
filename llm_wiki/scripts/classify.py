"""自动分类脚本：将 raw/ 下的研究报告按文件名规则归类到对应子目录。

用法:
    python llm_wiki/scripts/classify.py          # 扫描并分类
    python llm_wiki/scripts/classify.py --dry-run # 仅预览，不实际移动
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional


# 分类规则：按文件名模式匹配
# (目标子目录, 匹配模式列表)
CLASSIFICATION_RULES: list[tuple[str, list[str]]] = [
    # 海通证券_他山之石系列
    (
        "海通证券_他山之石系列",
        [
            "海通证券_2012", "海通证券_2013", "海通证券_2014", "海通证券_2015",
            "他山之石",
        ],
    ),
    # 华泰联合_行业量化选股
    (
        "华泰联合_行业量化选股",
        [
            "华泰联合", "数量化选股策略", "规模因子", "估值因子", "成长因子",
            "盈利因子", "交投波动", "分析师预测", "经营现金流", "跳出庐山",
            "PB-ROE",
        ],
    ),
    # 国信证券_多因子研究
    (
        "国信证券_多因子研究",
        [
            "多因子研究系列", "数量化研究系列", "关注度选股", "金融工程",
            "因子回溯测试",
        ],
    ),
    # 技术指标选股择时
    (
        "技术指标选股择时",
        [
            "技术指标系列", "技术指标高频", "KDJ优化", "ADX平均", "AROON",
            "CCI的顺势", "chaikinAD", "CMO动量", "EMV指标",
        ],
    ),
    # 长城证券_量化研究
    (
        "长城证券_量化研究",
        [
            "长城证券", "动态预期", "价值和成长的静态",
        ],
    ),
    # 光大证券
    (
        "光大证券",
        [
            "光大证券", "数量化投资：体系与策略",
        ],
    ),
    # 联合证券_数量化选股
    (
        "联合证券_数量化选股",
        [
            "联合证券", "滚动市盈率",
        ],
    ),
    # 学术论文 (CAJ 文件)
    (
        "学术论文",
        [
            ".caj",
        ],
    ),
    # 量化选股方法论 (DOC 文件 + [量化选股] 标签)
    (
        "量化选股方法论",
        [
            "[量化选股]", ".doc",
        ],
    ),
]


def classify_file(filepath: Path) -> Optional[str]:
    """根据文件名返回目标子目录名，无法分类返回 None。

    Args:
        filepath: 文件路径。

    Returns:
        目标子目录名，或 None。
    """
    fname = filepath.name

    # 跳过隐藏文件和占位文件
    if fname.startswith(".") or fname == ".gitkeep":
        return None

    for target_dir, patterns in CLASSIFICATION_RULES:
        for pattern in patterns:
            if pattern.lower() in fname.lower():
                return target_dir

    return None


def scan_files(raw_dir: Path) -> list[Path]:
    """递归扫描 raw/ 下的所有实际文件。

    Args:
        raw_dir: llm_wiki/raw/ 的绝对路径。

    Returns:
        文件 Path 列表（排除目录和 .gitkeep）。
    """
    files: list[Path] = []
    for root, dirs, filenames in os.walk(raw_dir):
        # 跳过分类目标子目录本身
        dirs_to_skip = [d for d in dirs if d in {r[0] for r in CLASSIFICATION_RULES}]
        for d in dirs_to_skip:
            dirs.remove(d)
        for fname in filenames:
            fpath = Path(root) / fname
            if fname.startswith(".") or fname == ".gitkeep":
                continue
            files.append(fpath)
    return files


def run_classify(raw_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    """执行分类。

    Args:
        raw_dir: llm_wiki/raw/ 的绝对路径。
        dry_run: True 时仅打印不移动。

    Returns:
        (已分类数, 未匹配数)
    """
    files = scan_files(raw_dir)
    classified = 0
    unmatched: list[Path] = []

    for fpath in files:
        target = classify_file(fpath)
        if target is None:
            unmatched.append(fpath)
            continue

        dest_dir = raw_dir / target
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / fpath.name

        # 处理重名
        if dest_path.exists() and not dry_run:
            base = dest_path.stem
            ext = dest_path.suffix
            counter = 1
            while dest_path.exists():
                dest_path = dest_dir / f"{base}_{counter}{ext}"
                counter += 1

        if dry_run:
            print(f"  [DRY-RUN] {fpath.relative_to(raw_dir)} → {target}/")
        else:
            shutil.move(str(fpath), str(dest_path))
            print(f"  ✓ {fpath.name} → {target}/")

        classified += 1

    if unmatched:
        print(f"\n⚠ 无法分类 ({len(unmatched)} 个):")
        for f in unmatched:
            print(f"  ? {f.relative_to(raw_dir)}")

    return classified, len(unmatched)


def cleanup_empty_dirs(raw_dir: Path) -> int:
    """清理 raw/ 下的空目录。

    Args:
        raw_dir: llm_wiki/raw/ 的绝对路径。

    Returns:
        删除的空目录数。
    """
    removed = 0
    for root, dirs, files in os.walk(raw_dir, topdown=False):
        # 不删除分类目标目录
        if root == str(raw_dir):
            continue
        if not os.listdir(root):
            os.rmdir(root)
            removed += 1
            print(f"  ✗ 删除空目录: {Path(root).relative_to(raw_dir)}")
    return removed


def main() -> None:
    """CLI 入口。"""
    dry_run = "--dry-run" in sys.argv

    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    wiki_dir = script_dir.parent
    raw_dir = wiki_dir / "raw"

    if not raw_dir.exists():
        print(f"错误: raw/ 目录不存在: {raw_dir}")
        sys.exit(1)

    mode = "预览 (--dry-run)" if dry_run else "执行"
    print(f"=== 报告自动分类 {mode} ===\n")

    classified, unmatched = run_classify(raw_dir, dry_run=dry_run)

    if not dry_run:
        print(f"\n=== 清理空目录 ===")
        removed = cleanup_empty_dirs(raw_dir)
        print(f"\n=== 完成 ===")
        print(f"  已分类: {classified}")
        print(f"  未匹配: {unmatched}")
        print(f"  清理空目录: {removed}")
        print(f"\n下一步: python llm_wiki/scripts/build_index.py")


if __name__ == "__main__":
    main()
