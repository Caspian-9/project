"""根据已 ingest 的 source 页面，生成有实际内容的实体 stub 页面。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def main() -> None:
    wiki_dir = Path(__file__).parent.parent / "wiki"
    idx_path = Path(__file__).parent.parent / "index.json"

    with open(idx_path, encoding="utf-8") as f:
        idx = json.load(f)

    reports = idx["reports"]
    today = datetime.now().strftime("%Y-%m-%d")

    # 收集每个实体的相关来源
    def find_sources(*keywords: str) -> list[dict]:
        """找到包含任意关键词的报告。"""
        matched: list[dict] = []
        for r in reports:
            ab = r.get("abstract", "") + " " + r.get("title", "")
            kw_text = " ".join(r.get("keywords", []))
            combined = (ab + " " + kw_text).lower()
            if any(kw.lower() in combined for kw in keywords):
                matched.append(r)
        return matched

    # ======================== 策略实体 ========================
    strategies = {
        "momentum-strategy": {
            "title": "动量策略",
            "aliases": ["Momentum", "动量效应", "趋势跟踪"],
            "keywords": ["动量", "momentum", "趋势", "GH", "RR", "52周最高价", "26周"],
            "definition": "买入过去N期表现最好的资产，卖出表现最差的资产。在A股市场，传统close-to-close动量效应弱于反转效应，但从最高价出发的GH/RR指标能捕捉到稳定的动量信号。",
        },
        "reversal-strategy": {
            "title": "反转策略",
            "aliases": ["Reversal", "反转效应", "均值回归"],
            "keywords": ["反转", "reversal", "均值回归", "超跌"],
            "definition": "买入过去短期表现最差的资产。A股市场1个月反转效应显著，买入前1个月收益率最低的十分之一个股年化超额收益>10%。",
        },
        "multi-factor-strategy": {
            "title": "多因子选股策略",
            "aliases": ["Multi-Factor", "打分法", "IC加权"],
            "keywords": ["多因子", "IC", "打分", "因子加权", "综合打分"],
            "definition": "综合多个Alpha因子对股票打分排序，选取最高分股票构建组合。核心环节：因子测试(IC/分层回测) → 因子筛选 → 权重分配 → 组合构建。",
        },
        "sector-rotation": {
            "title": "行业轮动策略",
            "aliases": ["Sector Rotation", "行业配置"],
            "keywords": ["行业轮动", "行业", "sector", "最优指标"],
            "definition": "在不同经济周期阶段超配/低配不同行业。华泰联合系列覆盖银行→化工15+行业，构建各行业专属最优量化选股指标体系。",
        },
        "trend-following": {
            "title": "趋势跟踪策略",
            "aliases": ["Trend Following", "CTA"],
            "keywords": ["趋势", "trend", "ADX", "ATR", "CCI", "顺势"],
            "definition": "技术分析核心范式——定义趋势并跟随。基本面与技术面本质都在定义各自框架内的趋势。长趋势持有期长、成功率高但回撤大，短趋势相反。ATR是更好的趋势确认指标。",
        },
        "garp-strategy": {
            "title": "GARP策略",
            "aliases": ["Growth at a Reasonable Price", "价值成长"],
            "keywords": ["GARP", "价值", "成长", "PE", "PB", "PEG"],
            "definition": "同时考量价值与成长的混合型投资策略。选股时兼顾价值(PE/PB/PCF/PS)和成长(净利润增长率等)，风险适中，震荡市表现最出色。国信证券GARP模型6年超额收益>300%。",
        },
        "pb-roe-strategy": {
            "title": "PB-ROE策略",
            "aliases": ["市净率-净资产收益率"],
            "keywords": ["PB", "ROE", "市净率", "净资产收益率", "估值"],
            "definition": "在沪深300成分股中使用PB和ROE两个维度构建选股策略。低PB+高ROE组合在A股表现优异，是价值投资在量化选股中的经典应用。",
        },
        "money-flow-strategy": {
            "title": "资金流选股策略",
            "aliases": ["Money Flow", "主力资金"],
            "keywords": ["资金流", "Chaikin", "AD", "EMV", "大单", "主力"],
            "definition": "基于成交量和价格关系追踪资金流向。ChaikinAD(SMA14,16)交叉策略6年累计收益2801%(年化71.63%)，EMV改进策略识别V字反转能力强。",
        },
        "style-rotation": {
            "title": "风格轮动策略",
            "aliases": ["Style Rotation", "大小盘轮动"],
            "keywords": ["风格轮动", "价值", "成长", "大小盘", "style"],
            "definition": "识别市场风格(价值/成长、大盘/小盘)切换规律并动态调整组合。风格因子在不同市场阶段表现差异显著。",
        },
        "hft-strategy": {
            "title": "高频交易策略",
            "aliases": ["HFT", "日内交易"],
            "keywords": ["高频", "HFT", "日内", "1分钟", "程序化"],
            "definition": "计算机驱动的日内高频交易，特征为交易次数多、每笔盈利小。KDJ优化指标高频策略在沪深300股指期货1分钟线年化47.99%、夏普2.12。优势：避免隔夜风险、分散投资、避免人为情绪。",
        },
    }

    for slug, info in strategies.items():
        sources = find_sources(*info["keywords"])
        src_links = "\n".join(
            f"| [[sources/{s['id']}]] | {s.get('title','')[:40]} | {s.get('date','')} |"
            for s in sources[:8]
        )
        page = f"""---
id: strat_{slug[:4]}
type: strategy
name: {info['title']}
aliases: {info['aliases']}
status: {'growing' if len(sources) >= 3 else 'stub'}
created: {today}
---

# {info['title']}

## 定义

{info['definition']}

## 相关来源

| 来源 | 标题 | 日期 |
|------|------|------|
{src_links if src_links else '| — | 待补充 | — |'}

## 关键参数

_待补充——ingest 完整报告后填入具体参数和最优范围_

## 相关

"""
        # 找相关因子和指标
        related = []
        for kw in info["keywords"]:
            if any(fkw in kw.lower() for fkw in ["动量", "趋势"]):
                related.append("- [[factors/momentum-factor]] — 动量因子")
                break
        for kw in info["keywords"]:
            if "资金流" in kw.lower() or "chaikin" in kw.lower():
                related.append("- [[indicators/chaikin-ad]] — Chaikin A/D线")
                related.append("- [[indicators/emv]] — EMV简易波动指标")
                break
        if not related:
            related.append("- [[concepts/sharpe-ratio]] — 夏普比率")
        page += "\n".join(set(related)) + "\n"

        out = wiki_dir / "strategies" / f"{slug}.md"
        out.write_text(page, encoding="utf-8")

    print(f"策略实体: {len(strategies)} 个")

    # ======================== 因子实体 ========================
    factors = {
        "size-factor": {
            "title": "规模因子 (Size)",
            "aliases": ["SMB", "市值因子", "小盘效应"],
            "definition": "小市值股票长期跑赢大市值股票。国信证券测试22个规模因子(S_MarketValue等)，全部在小盘股和中证500中表现最好，行业集中在有色金属、采掘、食品饮料。",
        },
        "growth-factor": {
            "title": "成长因子 (Growth)",
            "aliases": ["盈利增长", "收入增长"],
            "definition": "高成长股票未来收益更高。国信证券测试26个成长因子(G_NetProfit, G_ROE, G_EPS, G_EPSCAGR5等)，中盘股+2008-2012阶段最适合。华泰联合测试成长因子在A股选股效果显著。",
        },
        "quality-factor": {
            "title": "质量因子 (Quality)",
            "aliases": ["QMJ", "盈利质量", "财务安全"],
            "definition": "高质量公司长期跑赢低质量公司。国信证券测试25个质量因子(Q_ROE/Q_ROA/Q_ROIC/Q_DebtAssetsRatio等)，从盈利质量、经营效率、财务安全性三维度分类。中盘股表现最优。",
        },
        "value-factor": {
            "title": "估值因子 (Value)",
            "aliases": ["HML", "价值因子", "PE", "PB"],
            "definition": "低估值的股票长期跑赢高估值。华泰联合系统测试PE/PB/PCF/PS等估值因子在A股的有效性。滚动市盈率(TTM)比静态PE更具时效性和成长性反映能力。",
        },
        "momentum-factor": {
            "title": "动量因子 (Momentum)",
            "aliases": ["MOM", "趋势因子"],
            "definition": "过去表现好的股票未来继续表现好。但A股1个月周期呈反转效应。海通证券发现从26周最高价出发(GH/RR指标)能捕捉动量效应，传统close-to-close不够充分。",
        },
        "profitability-factor": {
            "title": "盈利因子 (Profitability)",
            "aliases": ["RMW", "ROE", "盈利能力"],
            "definition": "高盈利能力的公司长期跑赢。华泰联合测试ROE/ROA/毛利率/净利率等盈利因子，在食品饮料、医药等行业选股效果显著。与PB结合的PB-ROE策略是经典价值选股框架。",
        },
    }

    for slug, info in factors.items():
        keywords = info["aliases"] + [slug.replace("-", " ")]
        sources = find_sources(*keywords)
        src_links = "\n".join(
            f"| [[sources/{s['id']}]] | {s.get('title','')[:40]} | {s.get('date','')} |"
            for s in sources[:8]
        )
        page = f"""---
id: factor_{slug[:4]}
type: factor
name: {info['title']}
aliases: {info['aliases']}
status: {'growing' if len(sources) >= 3 else 'stub'}
created: {today}
---

# {info['title']}

## 定义

{info['definition']}

## A 股实证来源

| 来源 | 标题 | 日期 |
|------|------|------|
{src_links if src_links else '| — | 待补充 | — |'}

## 相关

- [[concepts/ic-analysis]] — IC分析
- [[concepts/factor-testing]] — 因子测试方法
"""
        out = wiki_dir / "factors" / f"{slug}.md"
        out.write_text(page, encoding="utf-8")

    print(f"因子实体: {len(factors)} 个")

    # ======================== 技术指标 ========================
    indicators = {
        "kdj": {
            "title": "KDJ 随机指标",
            "definition": "经典动量摆动指标。国信证券优化版：沪深300 6年17.5倍、高频版年化47.99%/夏普2.12。综合策略核心组件。",
        },
        "adx": {
            "title": "ADX 平均趋向指标",
            "definition": "趋势强度指标(非方向)。ADX(14)在沪深300双边交易年化54.90%/夏普1.61，每年>20%绝对收益。",
        },
        "aroon": {
            "title": "AROON 阿隆指标",
            "definition": "趋势识别指标。加入二次确认后年化51.22%/夏普1.49。牛市年化141%(胜率100%)，适合长期趋势。",
        },
        "cci": {
            "title": "CCI 商品通道指数",
            "definition": "顺势指标。CCI(27)年化42.9%/夏普1.23。优化版(20,7)年化55.5%/夏普1.62，信号更灵敏。",
        },
        "chaikin-ad": {
            "title": "Chaikin A/D 累积/派发线",
            "definition": "量价关系指标。SMA(14,16)交叉策略6年28倍/年化71.63%/夏普2.12，技指系列最佳单策略。",
        },
        "emv": {
            "title": "EMV 简易波动指标",
            "definition": "量价关系指标。参数14年化44%/夏普1.29。改进版引入MA替代0轴，识别V字反转(尖部)能力强。",
        },
        "cmo": {
            "title": "CMO 动量摆动指标",
            "definition": "Chande动量摆动指标，衡量价格动量和波动。沪深300双边交易表现良好，牛/熊/震荡市均有正收益。",
        },
        "atr": {
            "title": "ATR 平均真实波幅",
            "definition": "波动率指标。海通证券证明ATR是更好的趋势确认指标：比SD盈利幅度高36%/最大盈利高28%，趋势反转时不会出现伪突破。2013.12案例：抓住82%跌幅(SD仅24%)。",
        },
    }

    for slug, info in indicators.items():
        kw_map = {"kdj": "KDJ", "adx": "ADX", "aroon": "AROON", "cci": "CCI",
                  "chaikin-ad": "Chaikin", "emv": "EMV", "cmo": "CMO", "atr": "ATR"}
        sources = find_sources(kw_map.get(slug, slug))
        src_links = "\n".join(
            f"| [[sources/{s['id']}]] | {s.get('title','')[:40]} | {s.get('date','')} |"
            for s in sources[:6]
        )
        page = f"""---
id: ind_{slug[:4]}
type: indicator
name: {info['title']}
category: 动量 | 趋势 | 波动 | 成交量
status: {'growing' if len(sources) >= 2 else 'stub'}
created: {today}
---

# {info['title']}

## 概要

{info['definition']}

## 相关来源

| 来源 | 标题 | 日期 |
|------|------|------|
{src_links if src_links else '| — | 待补充 | — |'}

## 相关

- [[strategies/trend-following]] — 趋势跟踪策略
- [[strategies/money-flow-strategy]] — 资金流策略
"""
        out = wiki_dir / "indicators" / f"{slug}.md"
        out.write_text(page, encoding="utf-8")

    print(f"技术指标: {len(indicators)} 个")

    # ======================== 概念 ========================
    concepts = {
        "ic-analysis": {
            "title": "IC 分析 (Information Coefficient)",
            "definition": "衡量因子预测能力的核心指标。IC = 因子值与下期收益的截面秩相关系数。需观察IC均值/标准差/分布/T检验。国信证券多因子系列统一采用IC评价体系。关注度因子平均IC超3%。",
        },
        "factor-testing": {
            "title": "因子测试方法",
            "definition": "标准化因子回溯测试流程：数据清洗 → 风格过滤(标准化/分位数/组合权重/残余收益率四层) → IC分析 → 分层回测 → 情境分析(行业/风格/市场阶段)。国信证券框架测试2007.1-2012.5。",
        },
        "overfitting": {
            "title": "过拟合",
            "definition": "策略在样本内表现优异但样本外失效。警示信号：参数高原型(vs尖峰型)更稳健、Sharpe>3需警惕。海通证券提出技术指标实证结果情境分析方法来检测过拟合。",
        },
        "sharpe-ratio": {
            "title": "夏普比率",
            "definition": "风险调整后收益指标 = (年化收益-无风险利率)/年化波动率。技术指标系列：ChaikinAD夏普2.12(最佳)，综合策略夏普2.15。通常>1为良好，>2为优秀。",
        },
        "information-ratio": {
            "title": "信息比率 (IR)",
            "definition": "超额收益/跟踪误差。衡量策略相对基准的主动管理能力。分析师覆盖策略IR=2.01，年化超额28.04%。IR>1通常认为优秀。",
        },
    }

    for slug, info in concepts.items():
        kw_map = {"ic-analysis": "IC", "factor-testing": "因子测试", "overfitting": "过拟合",
                  "sharpe-ratio": "夏普", "information-ratio": "信息比"}
        sources = find_sources(kw_map.get(slug, slug))
        src_links = "\n".join(
            f"| [[sources/{s['id']}]] | {s.get('title','')[:40]} | {s.get('date','')} |"
            for s in sources[:6]
        )
        page = f"""---
id: concept_{slug[:4]}
type: concept
name: {info['title']}
status: {'growing' if len(sources) >= 2 else 'stub'}
created: {today}
---

# {info['title']}

## 定义

{info['definition']}

## 引用来源

| 来源 | 标题 | 日期 |
|------|------|------|
{src_links if src_links else '| — | 待补充 | — |'}

## 相关

- [[sources/gx_mf_004]] — 多因子研究系列(一)：因子回溯测试的总体框架
"""
        out = wiki_dir / "concepts" / f"{slug}.md"
        out.write_text(page, encoding="utf-8")

    print(f"概念: {len(concepts)} 个")

    # ======================== 综合分析 ========================
    syntheses = {
        "momentum-vs-reversal": {
            "title": "A股动量 vs 反转",
            "question": "A股市场究竟存在动量效应还是反转效应？",
            "content": """## 核心问题

A股市场究竟存在动量效应还是反转效应？不同来源的研究给出了不同的答案。

## 证据汇总

### 支持反转效应

| 来源 | 核心证据 |
|------|----------|
| [[sources/ht_tszs_022]] | 传统close-to-close收益率在中信一/二级行业上未产生显著动量效应。A股1个月反转：买入前1个月收益率最低的十分之一年化超额>10%。 |

### 支持动量效应

| 来源 | 核心证据 |
|------|----------|
| [[sources/ht_tszs_022]] | 从26周最高价出发的GH/RR指标在A股表现出稳定的动量预测能力，打破了传统方法看不到动量的局限。 |
| [[sources/gx_tech_001]] | 技术分析中趋势策略远好于反转策略。基本面与技术面本质都在定义趋势。 |

## 当前判断

A股短期(1个月)呈现反转效应，但通过更精细的指标设计(GH/RR、技术指标趋势跟踪)可以捕捉到中期动量。关键不在于动量是否存在，而在于用什么工具去度量。""",
        },
        "tech-indicators-comparison": {
            "title": "技术指标横向对比",
            "question": "9个技术指标中哪个综合表现最好？",
            "content": """## 核心问题

国信证券技术指标系列的9个指标中，哪个综合表现最好？如何组合最优？

## 单指标排名 (按年化夏普比率)

| 指标 | 年化收益 | 年化夏普 | 最大回撤 |
|------|----------|----------|----------|
| ChaikinAD(SMA14,16) | 71.63% | 2.12 | 25.89% |
| KDJ优化指标 | — | — | — |
| ADX(14) | 54.90% | 1.61 | 26% |
| CCI优化(20,7) | 55.5% | 1.62 | — |
| AROON优化 | 51.22% | 1.49 | 27.3% |
| EMV(14) | 44.02% | 1.29 | — |

## 多指标综合

| 策略 | 年化收益 | 年化夏普 | 最大回撤 |
|------|----------|----------|----------|
| 综合策略三 (ChaikinAD+KDJ+EMV) | 70.94% | 2.15 | 27.21% |

综合策略夏普超越所有单策略！核心思想是「多者胜」——但顶底判断更适合「少数决」(因此加入EMV改进指标)。

## 策略稳定性

ChaikinAD 2006-2011年各年收益：106.8% / 167.5% / 28.74% / 43.88% / 58.6% / 49.07%（每年均>28%）。

综合策略三同期：79.34% / 141% / 134% / 105% / 31.25% / 14.08%。""",
        },
    }

    for slug, info in syntheses.items():
        page = f"""---
id: synth_{slug[:4]}
type: synthesis
topic: {info['title']}
status: evolving
created: {today}
---

# {info['title']}

{info['content']}

## 待解决

- [ ] 不同市场阶段(牛/熊/震荡)的最优指标组合是否不同？
- [ ] 样本外(2012年后)表现如何？
- [ ] 交易成本(滑点/手续费)对高频策略的影响有多大？
"""
        out = wiki_dir / "synthesis" / f"{slug}.md"
        out.write_text(page, encoding="utf-8")

    print(f"综合分析: {len(syntheses)} 个")

    # 清理 .gitkeep（已有实际文件）
    for d in ["strategies", "factors", "indicators", "concepts", "synthesis"]:
        gk = wiki_dir / d / ".gitkeep"
        if gk.exists():
            gk.unlink()

    print("\n全部实体页面生成完毕！")


if __name__ == "__main__":
    main()
