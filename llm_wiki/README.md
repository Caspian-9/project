# LLM-Wiki 量化研究知识库

> 服务于 Quant Harness 的研究报告知识库，为 LLM 提供可检索的量化策略先验知识。

## 目录结构

```
llm_wiki/
├── raw/                          # 原始研究报告（放入实际 PDF/DOC/CAJ 文件）
│   ├── 海通证券_他山之石系列/     # 28 篇：海外量化经验 + 本土实证
│   ├── 华泰联合_行业量化选股/     # 21 篇：行业轮动 + 多因子选股策略
│   ├── 国信证券_多因子研究/       # 7 篇：因子回测框架 + 因子测试
│   ├── 长城证券_量化研究/         # 4 篇：GARP + 动态预期选股
│   ├── 光大证券/                  # 1 篇：数量化投资体系与策略
│   ├── 联合证券_数量化选股/       # 3 篇：数量化选股系列
│   ├── 学术论文/                  # 4 篇：CAJ 格式学术论文
│   ├── 量化选股方法论/            # 5 篇：五大选股模型方法论（DOC）
│   └── 技术指标选股择时/          # 9 篇：技术指标系统测试
├── index.json                    # 知识库索引（自动生成，LLM 检索入口）
├── scripts/
│   └── build_index.py            # 索引构建/校验脚本
└── README.md                     # 本文件
```

## 知识库覆盖主题

| 主题 | 报告数 | 核心内容 |
|---|---|---|
| 多因子选股 | 20+ | 因子测试框架、成长/价值/质量/规模/动量/反转因子 |
| 行业轮动 | 15+ | 银行业到化工业的最优选股指标 |
| 技术指标选股 | 9 | KDJ、ADX、AROON、CCI、Chaikin、CMO、EMV |
| GARP 策略 | 3 | 价值+成长的二维选股 |
| 行为金融 | 5 | 动量/反转、情绪指标、关注度因子 |
| 方法论 | 10+ | 因子回测框架、策略评价、组合优化 |
| 学术论文 | 4 | 遗传算法优化、套期保值、量化交易综述 |

## 快速开始

### 1. 放入原始报告

将实际的研究报告文件（PDF/DOC/CAJ）放入 `raw/` 对应子目录。

### 2. 生成索引

```bash
python llm_wiki/scripts/build_index.py
```

### 3. 检查缺失文件

```bash
python llm_wiki/scripts/build_index.py --check
```

### 4. 检索知识库（Python）

```python
import json
from llm_wiki.scripts.build_index import search_index

with open("llm_wiki/index.json", encoding="utf-8") as f:
    index = json.load(f)

# 按关键词搜索
results = search_index(index, keyword="动量")

# 按类别过滤
results = search_index(index, category="多因子研究")

# 按来源过滤
results = search_index(index, source="海通证券")
```

## 与 Quant Harness 的集成

Harness 的 `ContextManager`（Phase 3）会读取 `index.json`，在 Layer 1/2 中将相关知识卡片注入 LLM 上下文：

```
用户提出研究问题
    → Harness 从 index.json 检索相关报告
    → 将匹配的报告摘要注入 LLM 上下文
    → LLM 基于先验知识生成假设
    → 必要时 LLM 请求读取完整报告（Layer 3）
```

## 报告来源概览

- **海通证券** (2012-2015)：他山之石系列，海外量化方法论 + A 股本土实证
- **华泰联合** (2010-2011)：行业量化选股指标解析 + 数量化选股策略系列
- **国信证券** (2011-2012)：多因子研究系列（因子回测框架）、技术指标系列
- **长城证券** (2011)：量化研究系列（GARP、动态预期）
- **光大证券** (2012)：数量化投资体系与策略
- **联合证券** (2010)：数量化选股系列
