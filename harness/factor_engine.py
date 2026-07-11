"""因子引擎 — 从原始因子出发，自动生成变体。

变体策略:
  1. param_tweak: 参数微调（窗口±50%、变换方式变化）
  2. window_change: 多时间尺度（短期/中期/长期）
  3. new_variable: 引入新变量（如加入成交量、高低价）
  4. composite: 组合因子（与相关因子加权组合）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from backtest.factor_builder import FactorDef, TransformMethod
from harness.workflow import FactorVariant


# ======================== 变体生成策略 ========================


@dataclass
class VariantGenerator:
    """因子变体生成器 — 根据原始因子定义自动生成变体列表。"""

    # 参数微调: 窗口缩放倍数
    param_tweak_scales: list[float] = field(
        default_factory=lambda: [0.25, 0.5, 0.75, 1.5, 2.0, 3.0]
    )

    # 多时间尺度: 短期/中期/长期窗口
    multi_scale_windows: dict[str, list[int]] = field(
        default_factory=lambda: {
            "short": [5, 10, 15],
            "medium": [20, 40, 60],
            "long": [120, 250],
        }
    )

    # 变换方式
    transforms: list[str] = field(
        default_factory=lambda: ["zscore", "rank", "winsorize"]
    )

    # 备选基元（用于引入新变量）
    alternative_bases: list[str] = field(
        default_factory=lambda: ["returns", "volume", "high", "low"]
    )

    def generate(
        self,
        original: dict[str, Any],
        factor_name: str = "factor",
        max_variants: int = 20,
    ) -> list[FactorVariant]:
        """从原始因子定义生成变体列表。

        Args:
            original: 原始因子参数字典 (base, window, agg_func, transform)。
            factor_name: 因子名称前缀。
            max_variants: 最大变体数量。

        Returns:
            FactorVariant 列表。
        """
        base = original.get("base", "returns")
        window = original.get("window", 20)
        agg_func = original.get("agg_func", "sum")
        transform = original.get("transform", "zscore")

        variants: list[FactorVariant] = []

        # 1. 参数微调 (param_tweak)
        for scale in self.param_tweak_scales:
            new_window = max(2, int(window * scale))
            if new_window == window:
                continue
            variants.append(
                FactorVariant(
                    name=f"{factor_name}_w{new_window}_{agg_func}",
                    description=f"窗口从{window}调整为{new_window}（×{scale}）",
                    base=base,
                    window=new_window,
                    agg_func=agg_func,
                    transform=transform,
                    parent_factor=factor_name,
                    variant_type="param_tweak",
                )
            )

        # 2. 变换方式变化
        for t in self.transforms:
            if t == transform:
                continue
            variants.append(
                FactorVariant(
                    name=f"{factor_name}_w{window}_{agg_func}_{t}",
                    description=f"变换方式从{transform}改为{t}",
                    base=base,
                    window=window,
                    agg_func=agg_func,
                    transform=t,
                    parent_factor=factor_name,
                    variant_type="param_tweak",
                )
            )

        # 3. 引入新变量 (change base)
        for alt_base in self.alternative_bases:
            if alt_base == base:
                continue
            for w in [window, max(2, window // 2)]:
                variants.append(
                    FactorVariant(
                        name=f"{factor_name}_{alt_base}_w{w}_{agg_func}",
                        description=f"改用{alt_base}数据，窗口{w}",
                        base=alt_base,
                        window=w,
                        agg_func=agg_func,
                        transform=transform,
                        parent_factor=factor_name,
                        variant_type="new_variable",
                    )
                )

        # 4. 多时间尺度
        for scale_name, windows in self.multi_scale_windows.items():
            for w in windows:
                if w == window:
                    continue
                variants.append(
                    FactorVariant(
                        name=f"{factor_name}_{scale_name}_w{w}_{agg_func}",
                        description=f"{scale_name}期尺度，窗口{w}",
                        base=base,
                        window=w,
                        agg_func=agg_func,
                        transform=transform,
                        parent_factor=factor_name,
                        variant_type="window_change",
                    )
                )

        # 去重 + 限制数量
        seen: set[str] = set()
        unique: list[FactorVariant] = []
        for v in variants:
            if v.name not in seen:
                seen.add(v.name)
                unique.append(v)
                if len(unique) >= max_variants:
                    break

        return unique

    def to_factor_defs(self, variants: list[FactorVariant]) -> list[FactorDef]:
        """将 FactorVariant 列表转为 FactorDef 列表。

        Args:
            variants: 变体列表。

        Returns:
            FactorDef 列表。
        """
        transform_map: dict[str, TransformMethod] = {
            "raw": TransformMethod.RAW,
            "zscore": TransformMethod.ZSCORE,
            "rank": TransformMethod.RANK,
            "winsorize": TransformMethod.WINSORIZE,
        }

        defs: list[FactorDef] = []
        for v in variants:
            defs.append(
                FactorDef(
                    name=v.name,
                    base=v.base,
                    window=v.window,
                    agg_func=v.agg_func,
                    transform=transform_map.get(v.transform, TransformMethod.ZSCORE),
                )
            )
        return defs


def generate_variant_ideas(
    original: dict[str, Any],
    economic_rationale: str = "",
    limitations: Optional[list[str]] = None,
) -> list[dict[str, str]]:
    """生成变体思路——供 LLM 参考的结构化建议。

    不直接生成 FactorVariant，而是输出自然语言描述，
    让 LLM 理解后再决定采用哪些变体。

    Args:
        original: 原始因子参数。
        economic_rationale: 因子的经济逻辑。
        limitations: 已知局限。

    Returns:
        变体思路列表，每项含 name, description, variant_type。
    """
    base = original.get("base", "returns")
    window = original.get("window", 20)
    agg = original.get("agg_func", "sum")

    ideas: list[dict[str, str]] = [
        {
            "name": "缩短窗口",
            "description": f"将{window}期窗口缩短至{max(2, window//2)}或{max(2, window//4)}期，捕捉更短期的信号",
            "variant_type": "window_change",
        },
        {
            "name": "延长窗口",
            "description": f"将{window}期窗口延长至{window*2}或{window*3}期，过滤噪音捕捉中长期趋势",
            "variant_type": "window_change",
        },
        {
            "name": "改用 Rank 变换",
            "description": "将截面标准化改为截面排序，降低极端值影响，提高因子稳定性",
            "variant_type": "param_tweak",
        },
        {
            "name": "去极值处理",
            "description": "在标准化之前对因子值进行 Winsorize（截尾1%/99%），减少异常值干扰",
            "variant_type": "param_tweak",
        },
        {
            "name": "引入成交量信息",
            "description": f"在{base}基础上乘以或除以成交量，构造价量复合因子",
            "variant_type": "new_variable",
        },
        {
            "name": "改用波动率",
            "description": f"将聚合函数从 {agg} 改为 std，捕捉{base}的波动特征而非方向",
            "variant_type": "param_tweak",
        },
    ]

    # 根据经济逻辑添加针对性建议
    if "动量" in economic_rationale or "趋势" in economic_rationale:
        ideas.append({
            "name": "分离上行/下行动量",
            "description": "将正收益和负收益分别聚合后相减，捕捉非对称动量效应",
            "variant_type": "new_variable",
        })
    if "反转" in economic_rationale:
        ideas.append({
            "name": "加入波动率过滤器",
            "description": "仅在高波动环境下做反转交易，低波动时不做",
            "variant_type": "new_variable",
        })
    if limitations:
        for lim in limitations:
            if "行业" in lim or "风格" in lim:
                ideas.append({
                    "name": "行业中性化",
                    "description": "对因子值做行业中性化处理，消除行业暴露偏差",
                    "variant_type": "new_variable",
                })
                break

    return ideas
