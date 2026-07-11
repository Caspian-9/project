"""LLM-Wiki 知识库索引构建脚本。

从 raw/ 目录扫描研究报告文件，生成/更新 index.json。

用法:
    python llm_wiki/scripts/build_index.py          # 扫描 raw/ 并生成索引
    python llm_wiki/scripts/build_index.py --check  # 检查哪些报告文件缺失
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# --- 报告元数据预定义 ---
# 即使原始文件暂未放入 raw/，索引条目仍保留，方便用户知道应放入哪些文件。
# 每个条目: (相对路径, 标题, 作者/来源, 日期, 关键词, 摘要, 类别)

KNOWN_REPORTS: list[dict[str, Any]] = [
    # ======================== 海通证券_他山之石系列 ========================
    {
        "id": "ht_tszs_001",
        "path": "海通证券_他山之石系列/海通证券_20120830_他山之石.pdf",
        "title": "他山之石",
        "source": "海通证券",
        "date": "2012-08-30",
        "keywords": ["量化选股", "海外经验", "他山之石"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列开篇，介绍海外量化选股的先进方法和经验。",
    },
    {
        "id": "ht_tszs_002",
        "path": "海通证券_他山之石系列/海通证券_20121207_他山之石.pdf",
        "title": "他山之石（二）",
        "source": "海通证券",
        "date": "2012-12-07",
        "keywords": ["量化选股", "海外经验", "他山之石"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第二篇。",
    },
    {
        "id": "ht_tszs_003",
        "path": "海通证券_他山之石系列/海通证券_20130121_他山之石系列五.pdf",
        "title": "他山之石系列五",
        "source": "海通证券",
        "date": "2013-01-21",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第五篇。",
    },
    {
        "id": "ht_tszs_004",
        "path": "海通证券_他山之石系列/海通证券_20130226_他山之石.pdf",
        "title": "他山之石（四）",
        "source": "海通证券",
        "date": "2013-02-26",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第四篇。",
    },
    {
        "id": "ht_tszs_005",
        "path": "海通证券_他山之石系列/海通证券_20130326_他山之石.pdf",
        "title": "他山之石（五）",
        "source": "海通证券",
        "date": "2013-03-26",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第五篇。",
    },
    {
        "id": "ht_tszs_006",
        "path": "海通证券_他山之石系列/海通证券_20130425_他山之石.pdf",
        "title": "他山之石（六）",
        "source": "海通证券",
        "date": "2013-04-25",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第六篇。",
    },
    {
        "id": "ht_tszs_007",
        "path": "海通证券_他山之石系列/海通证券_20130702_他山之石.pdf",
        "title": "他山之石（七）",
        "source": "海通证券",
        "date": "2013-07-02",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第七篇。",
    },
    {
        "id": "ht_tszs_008",
        "path": "海通证券_他山之石系列/海通证券_20130726_他山之石.pdf",
        "title": "他山之石（八）",
        "source": "海通证券",
        "date": "2013-07-26",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第八篇。",
    },
    {
        "id": "ht_tszs_009",
        "path": "海通证券_他山之石系列/海通证券_20130828_他山之石.pdf",
        "title": "他山之石（九）",
        "source": "海通证券",
        "date": "2013-08-28",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第九篇。",
    },
    {
        "id": "ht_tszs_010",
        "path": "海通证券_他山之石系列/海通证券_20131111_他山之石实证系列之一：从持股变动挖掘股票情绪信息.pdf",
        "title": "他山之石实证系列之一：从持股变动挖掘股票情绪信息",
        "source": "海通证券",
        "date": "2013-11-11",
        "keywords": ["持股变动", "情绪指标", "实证研究", "选股因子"],
        "category": "他山之石系列",
        "subcategory": "实证系列",
        "abstract": "基于持股变动数据构建股票情绪指标，实证检验其对未来收益的预测能力。",
    },
    {
        "id": "ht_tszs_011",
        "path": "海通证券_他山之石系列/海通证券_20131209_他山之石系列之十五.pdf",
        "title": "他山之石系列之十五",
        "source": "海通证券",
        "date": "2013-12-09",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第十五篇。",
    },
    {
        "id": "ht_tszs_012",
        "path": "海通证券_他山之石系列/海通证券_20131224_他山之石实证系列之二：基金持有人具有选基能力吗？.pdf",
        "title": "他山之石实证系列之二：基金持有人具有选基能力吗？",
        "source": "海通证券",
        "date": "2013-12-24",
        "keywords": ["基金选择", "持有人行为", "实证研究"],
        "category": "他山之石系列",
        "subcategory": "实证系列",
        "abstract": "实证检验基金持有人是否具备选择优质基金的能力。",
    },
    {
        "id": "ht_tszs_013",
        "path": "海通证券_他山之石系列/海通证券_20140110_他山之石系列十六.pdf",
        "title": "他山之石系列十六",
        "source": "海通证券",
        "date": "2014-01-10",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第十六篇。",
    },
    {
        "id": "ht_tszs_014",
        "path": "海通证券_他山之石系列/海通证券_20140129_他山之石本土实证之三：聚焦被忽视的超预期.pdf",
        "title": '他山之石本土实证之三：聚焦被"忽视"的超预期',
        "source": "海通证券",
        "date": "2014-01-29",
        "keywords": ["超预期", "分析师预期", "选股因子", "本土实证"],
        "category": "他山之石系列",
        "subcategory": "实证系列",
        "abstract": "基于A股数据实证检验超预期因子（earnings surprise）的选股效果，聚焦被市场忽视的超预期信号。",
    },
    {
        "id": "ht_tszs_015",
        "path": "海通证券_他山之石系列/海通证券_20140214_他山之石系列十七.pdf",
        "title": "他山之石系列十七",
        "source": "海通证券",
        "date": "2014-02-14",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第十七篇。",
    },
    {
        "id": "ht_tszs_016",
        "path": "海通证券_他山之石系列/海通证券_20140224_他山之石本土实证系列之四：ATR是一个更好的趋势确认指标吗.pdf",
        "title": "他山之石本土实证系列之四：ATR是一个更好的趋势确认指标吗",
        "source": "海通证券",
        "date": "2014-02-24",
        "keywords": ["ATR", "趋势确认", "技术指标", "本土实证"],
        "category": "他山之石系列",
        "subcategory": "实证系列",
        "abstract": "实证检验ATR（平均真实波幅）指标在A股市场的趋势确认效果，与传统趋势指标对比。",
    },
    {
        "id": "ht_tszs_017",
        "path": "海通证券_他山之石系列/海通证券_20140324_他山之石系列十八.pdf",
        "title": "他山之石系列十八",
        "source": "海通证券",
        "date": "2014-03-24",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第十八篇。",
    },
    {
        "id": "ht_tszs_018",
        "path": "海通证券_他山之石系列/海通证券_20140409_他山之石系列十九.pdf",
        "title": "他山之石系列十九",
        "source": "海通证券",
        "date": "2014-04-09",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第十九篇。",
    },
    {
        "id": "ht_tszs_019",
        "path": "海通证券_他山之石系列/海通证券_20140516_他山之石系列二十.pdf",
        "title": "他山之石系列二十",
        "source": "海通证券",
        "date": "2014-05-16",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第二十篇。",
    },
    {
        "id": "ht_tszs_020",
        "path": "海通证券_他山之石系列/海通证券_20140624_他山之石系列二十一.pdf",
        "title": "他山之石系列二十一",
        "source": "海通证券",
        "date": "2014-06-24",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第二十一篇。",
    },
    {
        "id": "ht_tszs_021",
        "path": "海通证券_他山之石系列/海通证券_20140723_他山之石——Bridgewater经济运行准则.pdf",
        "title": "他山之石——Bridgewater经济运行准则",
        "source": "海通证券",
        "date": "2014-07-23",
        "keywords": ["Bridgewater", "宏观经济", "运行准则", "全天候策略"],
        "category": "他山之石系列",
        "subcategory": "专题",
        "abstract": "介绍Bridgewater（桥水基金）的经济运行分析框架和全天候投资策略。",
    },
    {
        "id": "ht_tszs_022",
        "path": "海通证券_他山之石系列/海通证券_20141008他山之石本土实证系列之五：过去26周最高价及其出现时间的动量效应.pdf",
        "title": "他山之石本土实证系列之五：过去26周最高价及其出现时间的动量效应",
        "source": "海通证券",
        "date": "2014-10-08",
        "keywords": ["动量效应", "52周最高价", "时间因子", "本土实证"],
        "category": "他山之石系列",
        "subcategory": "实证系列",
        "abstract": "实证检验过去26周（半年）最高价及其出现时间距离对A股未来收益的预测作用，验证锚定效应在A股的存在性。",
    },
    {
        "id": "ht_tszs_023",
        "path": "海通证券_他山之石系列/海通证券_20141014_他山之石系列之二十四.pdf",
        "title": "他山之石系列之二十四",
        "source": "海通证券",
        "date": "2014-10-14",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第二十四篇。",
    },
    {
        "id": "ht_tszs_024",
        "path": "海通证券_他山之石系列/海通证券_20141111_他山之石本土实证系列之六：券商分析师覆盖变化对个股的影响.pdf",
        "title": "他山之石本土实证系列之六：券商分析师覆盖变化对个股的影响",
        "source": "海通证券",
        "date": "2014-11-11",
        "keywords": ["分析师覆盖", "信息不对称", "选股因子", "本土实证"],
        "category": "他山之石系列",
        "subcategory": "实证系列",
        "abstract": "实证检验分析师覆盖数量的变化对A股个股收益的影响，探讨信息不对称因子的选股价值。",
    },
    {
        "id": "ht_tszs_025",
        "path": "海通证券_他山之石系列/海通证券_20141114_他山之石系列之二十五.pdf",
        "title": "他山之石系列之二十五",
        "source": "海通证券",
        "date": "2014-11-14",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第二十五篇。",
    },
    {
        "id": "ht_tszs_026",
        "path": "海通证券_他山之石系列/海通证券_20141219_他山之石系列二十六.pdf",
        "title": "他山之石系列二十六",
        "source": "海通证券",
        "date": "2014-12-19",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第二十六篇。",
    },
    {
        "id": "ht_tszs_027",
        "path": "海通证券_他山之石系列/海通证券_20150127_他山之石系列二十七.pdf",
        "title": "他山之石系列二十七",
        "source": "海通证券",
        "date": "2015-01-27",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第二十七篇。",
    },
    {
        "id": "ht_tszs_028",
        "path": "海通证券_他山之石系列/海通证券_20150213_他山之石系列二十八.pdf",
        "title": "他山之石系列二十八",
        "source": "海通证券",
        "date": "2015-02-13",
        "keywords": ["量化选股", "海外经验"],
        "category": "他山之石系列",
        "subcategory": "综述",
        "abstract": "海通证券他山之石系列第二十八篇。",
    },
    # ======================== 华泰联合_行业量化选股 ========================
    {
        "id": "htlhyh_001",
        "path": "华泰联合_行业量化选股/华泰联合_2010-02-05_银行业最优量化选股指标.pdf",
        "title": "银行业最优量化选股指标——行业量化选股指标解析系列之一",
        "source": "华泰联合证券",
        "date": "2010-02-05",
        "keywords": ["银行业", "行业轮动", "量化选股", "最优指标"],
        "category": "行业量化选股",
        "subcategory": "银行业",
        "abstract": "系统解析银行业的最优量化选股指标体系，构建行业专属的多因子选股框架。",
    },
    {
        "id": "htlhyh_002",
        "path": "华泰联合_行业量化选股/华泰联合_2010-03-10_交通运输业最优量化选股指标.pdf",
        "title": "交通运输业最优量化选股指标——行业量化选股指标解析系列之二",
        "source": "华泰联合证券",
        "date": "2010-03-10",
        "keywords": ["交通运输", "行业轮动", "量化选股", "最优指标"],
        "category": "行业量化选股",
        "subcategory": "交通运输",
        "abstract": "系统解析交通运输业的最优量化选股指标体系。",
    },
    {
        "id": "htlhyh_003",
        "path": "华泰联合_行业量化选股/华泰联合_2010-03-11_餐饮旅游业最优量化选股指标.pdf",
        "title": "餐饮旅游业最优量化选股指标——行业量化选股指标解析系列之三",
        "source": "华泰联合证券",
        "date": "2010-03-11",
        "keywords": ["餐饮旅游", "行业轮动", "量化选股", "最优指标"],
        "category": "行业量化选股",
        "subcategory": "餐饮旅游",
        "abstract": "系统解析餐饮旅游业的最优量化选股指标体系。",
    },
    {
        "id": "htlhyh_004",
        "path": "华泰联合_行业量化选股/华泰联合_2010-04-07_信息服务业最优量化选股指标.pdf",
        "title": "信息服务业最优量化选股指标——行业量化选股指标解析系列之五",
        "source": "华泰联合证券",
        "date": "2010-04-07",
        "keywords": ["信息服务", "行业轮动", "量化选股", "最优指标"],
        "category": "行业量化选股",
        "subcategory": "信息服务",
        "abstract": "系统解析信息服务业的最优量化选股指标体系。",
    },
    {
        "id": "htlhyh_005",
        "path": "华泰联合_行业量化选股/华泰联合_2010-08-11_有色金属业最优量化选股指标.pdf",
        "title": "有色金属业最优量化选股指标",
        "source": "华泰联合证券",
        "date": "2010-08-11",
        "keywords": ["有色金属", "行业轮动", "量化选股", "最优指标"],
        "category": "行业量化选股",
        "subcategory": "有色金属",
        "abstract": "系统解析有色金属业的最优量化选股指标体系。",
    },
    {
        "id": "htlhyh_006",
        "path": "华泰联合_行业量化选股/华泰联合_2010-08-11_有色金属业最优量化选股指标——行业量化选股指标解析系列之十九.pdf",
        "title": "有色金属业最优量化选股指标——行业量化选股指标解析系列之十九",
        "source": "华泰联合证券",
        "date": "2010-08-11",
        "keywords": ["有色金属", "行业轮动", "量化选股"],
        "category": "行业量化选股",
        "subcategory": "有色金属",
        "abstract": "行业量化选股指标解析系列第十九篇，有色金属业专题。",
    },
    {
        "id": "htlhyh_007",
        "path": "华泰联合_行业量化选股/华泰联合_2010-09-10_黑色金属业最优量化选股指标.pdf",
        "title": "黑色金属业最优量化选股指标——行业量化选股指标解析系列之二十",
        "source": "华泰联合证券",
        "date": "2010-09-10",
        "keywords": ["黑色金属", "钢铁", "行业轮动", "量化选股"],
        "category": "行业量化选股",
        "subcategory": "黑色金属",
        "abstract": "系统解析黑色金属（钢铁）业的最优量化选股指标体系。",
    },
    {
        "id": "htlhyh_008",
        "path": "华泰联合_行业量化选股/华泰联合_2010-09-15_交运设备业最优量化选股指标.pdf",
        "title": "交运设备业最优量化选股指标",
        "source": "华泰联合证券",
        "date": "2010-09-15",
        "keywords": ["交运设备", "行业轮动", "量化选股", "最优指标"],
        "category": "行业量化选股",
        "subcategory": "交运设备",
        "abstract": "系统解析交运设备业的最优量化选股指标体系。",
    },
    {
        "id": "htlhyh_009",
        "path": "华泰联合_行业量化选股/华泰联合_2010-09-27_市场预期收益率选股策略.pdf",
        "title": "市场预期收益率选股策略",
        "source": "华泰联合证券",
        "date": "2010-09-27",
        "keywords": ["预期收益率", "选股策略", "市场预期"],
        "category": "行业量化选股",
        "subcategory": "选股策略",
        "abstract": "基于市场预期收益率构建量化选股策略的研究。",
    },
    {
        "id": "htlhyh_010",
        "path": "华泰联合_行业量化选股/华泰联合_2010-11-24_化工业最优量化选股指标.pdf",
        "title": "化工业最优量化选股指标",
        "source": "华泰联合证券",
        "date": "2010-11-24",
        "keywords": ["化工", "行业轮动", "量化选股", "最优指标"],
        "category": "行业量化选股",
        "subcategory": "化工",
        "abstract": "系统解析化工业的最优量化选股指标体系。",
    },
    {
        "id": "htlhyh_011",
        "path": "华泰联合_行业量化选股/华泰联合_2010-11-24_化工业最优量化选股指标——行业量化选股指标解析系列之二十二.pdf",
        "title": "化工业最优量化选股指标——行业量化选股指标解析系列之二十二",
        "source": "华泰联合证券",
        "date": "2010-11-24",
        "keywords": ["化工", "行业轮动", "量化选股"],
        "category": "行业量化选股",
        "subcategory": "化工",
        "abstract": "行业量化选股指标解析系列第二十二篇，化工业专题。",
    },
    {
        "id": "htlhyh_012",
        "path": "华泰联合_行业量化选股/华泰联合_2011-05-20_数量化选股策略之三：PB-ROE策略.pdf",
        "title": "数量化选股策略之三：PB-ROE策略",
        "source": "华泰联合证券",
        "date": "2011-05-20",
        "keywords": ["PB-ROE", "估值因子", "选股策略", "价值投资"],
        "category": "行业量化选股",
        "subcategory": "选股策略",
        "abstract": "构建PB-ROE框架下的量化选股策略，结合估值与盈利能力的二维选股模型。",
    },
    {
        "id": "htlhyh_013",
        "path": "华泰联合_行业量化选股/华泰联合_2011-06-20_规模因子分析——数量化选股策略之四.pdf",
        "title": "规模因子分析——数量化选股策略之四",
        "source": "华泰联合证券",
        "date": "2011-06-20",
        "keywords": ["规模因子", "市值效应", "小盘股", "多因子模型"],
        "category": "行业量化选股",
        "subcategory": "选股策略",
        "abstract": "系统分析A股市场规模因子（市值效应）的选股效果和稳定性。",
    },
    {
        "id": "htlhyh_014",
        "path": "华泰联合_行业量化选股/华泰联合_2011-07-06_估值因子分析——数量化选股策略之五.pdf",
        "title": "估值因子分析——数量化选股策略之五",
        "source": "华泰联合证券",
        "date": "2011-07-06",
        "keywords": ["估值因子", "PE", "PB", "价值投资", "多因子模型"],
        "category": "行业量化选股",
        "subcategory": "选股策略",
        "abstract": "系统分析各类估值因子（PE、PB、PS等）在A股的选股效果。",
    },
    {
        "id": "htlhyh_015",
        "path": "华泰联合_行业量化选股/华泰联合_2011-07-08_数量化选股策略效果评价研究.pdf",
        "title": "数量化选股策略效果评价研究",
        "source": "华泰联合证券",
        "date": "2011-07-08",
        "keywords": ["策略评价", "绩效归因", "稳健性检验"],
        "category": "行业量化选股",
        "subcategory": "方法论",
        "abstract": "建立量化选股策略的效果评价体系，涵盖收益归因、风险调整、稳健性检验等维度。",
    },
    {
        "id": "htlhyh_016",
        "path": "华泰联合_行业量化选股/华泰联合_2011-07-12_成长因子分析——数量化选股策略之六.pdf",
        "title": "成长因子分析——数量化选股策略之六",
        "source": "华泰联合证券",
        "date": "2011-07-12",
        "keywords": ["成长因子", "盈利增长", "多因子模型"],
        "category": "行业量化选股",
        "subcategory": "选股策略",
        "abstract": "系统分析成长类因子（盈利增长、收入增长等）在A股的选股效果。",
    },
    {
        "id": "htlhyh_017",
        "path": "华泰联合_行业量化选股/华泰联合_2011-07-26_盈利因子分析——数量化选股策略之七.pdf",
        "title": "盈利因子分析——数量化选股策略之七",
        "source": "华泰联合证券",
        "date": "2011-07-26",
        "keywords": ["盈利因子", "ROE", "ROA", "多因子模型"],
        "category": "行业量化选股",
        "subcategory": "选股策略",
        "abstract": "系统分析盈利类因子（ROE、ROA、毛利率等）在A股的选股效果。",
    },
    {
        "id": "htlhyh_018",
        "path": "华泰联合_行业量化选股/华泰联合_2011-08-09_基于经营现金流量净额的量化选股策略.pdf",
        "title": "基于经营现金流量净额的量化选股策略——成长量化投资研究之三",
        "source": "华泰联合证券",
        "date": "2011-08-09",
        "keywords": ["现金流", "经营现金流", "质量因子", "选股策略"],
        "category": "行业量化选股",
        "subcategory": "选股策略",
        "abstract": "基于经营现金流量净额构建选股策略，检验现金流质量因子的选股效果。",
    },
    {
        "id": "htlhyh_019",
        "path": "华泰联合_行业量化选股/华泰联合_2011-08-22_交投波动因子分析.pdf",
        "title": "交投波动因子分析——数量化选股策略之十",
        "source": "华泰联合证券",
        "date": "2011-08-22",
        "keywords": ["交投因子", "波动率", "换手率", "多因子模型"],
        "category": "行业量化选股",
        "subcategory": "选股策略",
        "abstract": "系统分析交易类因子（换手率、波动率等）在A股的选股效果。",
    },
    {
        "id": "htlhyh_020",
        "path": "华泰联合_行业量化选股/华泰联合_2011-08-31_分析师预测因子分析——数量化选股策略之十一.pdf",
        "title": "分析师预测因子分析——数量化选股策略之十一",
        "source": "华泰联合证券",
        "date": "2011-08-31",
        "keywords": ["分析师预测", "一致预期", "超预期", "选股因子"],
        "category": "行业量化选股",
        "subcategory": "选股策略",
        "abstract": "系统分析分析师预测类因子（一致预期、预测修正等）在A股的选股效果。",
    },
    {
        "id": "htlhyh_021",
        "path": "华泰联合_行业量化选股/华泰联合-金融工程：跳出庐山看庐山.pdf",
        "title": "金融工程：跳出庐山看庐山",
        "source": "华泰联合证券",
        "date": "2011-01-01",
        "keywords": ["金融工程", "方法论", "量化投资", "综述"],
        "category": "行业量化选股",
        "subcategory": "方法论",
        "abstract": "华泰联合金融工程团队的量化投资方法论综述，从海外视角审视A股量化投资。",
    },
    # ======================== 国信证券_多因子研究 ========================
    {
        "id": "gx_mf_001",
        "path": "国信证券_多因子研究/国信证券_20110914_数量化研究系列之十五_基于全市场的GARP选股研究.pdf",
        "title": "数量化研究系列之十五：基于全市场的GARP选股研究",
        "source": "国信证券",
        "date": "2011-09-14",
        "keywords": ["GARP", "价值成长", "全市场选股", "多因子"],
        "category": "多因子研究",
        "subcategory": "GARP策略",
        "abstract": "构建全市场GARP（Growth at a Reasonable Price）选股策略，融合价值与成长因子。",
    },
    {
        "id": "gx_mf_002",
        "path": "国信证券_多因子研究/国信证券_20111115_数量化研究系列之十九_多因子选股模型之组合构建Ⅲ.pdf",
        "title": "数量化研究系列之十九：多因子选股模型之组合构建Ⅲ",
        "source": "国信证券",
        "date": "2011-11-15",
        "keywords": ["多因子模型", "组合构建", "权重优化"],
        "category": "多因子研究",
        "subcategory": "组合优化",
        "abstract": "多因子选股模型的组合构建方法研究（第三篇），涵盖因子加权和组合优化技术。",
    },
    {
        "id": "gx_mf_003",
        "path": "国信证券_多因子研究/国信证券_20111221_关注度选股因子历史回测.pdf",
        "title": "金融工程：关注度选股因子历史回测",
        "source": "国信证券",
        "date": "2011-12-21",
        "keywords": ["关注度因子", "行为金融", "选股因子", "历史回测"],
        "category": "多因子研究",
        "subcategory": "行为金融因子",
        "abstract": "构建关注度选股因子（基于媒体关注/搜索热度等），进行A股历史回测验证。",
    },
    {
        "id": "gx_mf_004",
        "path": "国信证券_多因子研究/国信证券_20120822_多因子研究系列(一)_因子回溯测试的总体框架.pdf",
        "title": "多因子研究系列(一)：因子回溯测试的总体框架",
        "source": "国信证券",
        "date": "2012-08-22",
        "keywords": ["因子回测", "IC分析", "分层回测", "方法论", "框架"],
        "category": "多因子研究",
        "subcategory": "方法论",
        "abstract": "建立系统化的因子回溯测试总体框架，涵盖数据处理、IC分析、分层回测、稳健性检验等完整流程。",
    },
    {
        "id": "gx_mf_005",
        "path": "国信证券_多因子研究/国信证券_20120911_多因子研究系列(三)_成长类因子测试.pdf",
        "title": "多因子研究系列(三)：成长类因子测试",
        "source": "国信证券",
        "date": "2012-09-11",
        "keywords": ["成长因子", "盈利增长", "因子测试", "IC分析"],
        "category": "多因子研究",
        "subcategory": "因子测试",
        "abstract": "系统测试A股市场成长类因子（营收增长、盈利增长、预期增长等）的选股有效性。",
    },
    {
        "id": "gx_mf_006",
        "path": "国信证券_多因子研究/国信证券_20120911_多因子研究系列(四)_规模类因子测试.pdf",
        "title": "多因子研究系列(四)：规模类因子测试",
        "source": "国信证券",
        "date": "2012-09-11",
        "keywords": ["规模因子", "市值", "小盘效应", "因子测试"],
        "category": "多因子研究",
        "subcategory": "因子测试",
        "abstract": "系统测试A股市场规模类因子（总市值、流通市值等）的选股有效性。",
    },
    {
        "id": "gx_mf_007",
        "path": "国信证券_多因子研究/国信证券_20120911_多因子研究系列(六)_质量类因子测试.pdf",
        "title": "多因子研究系列(六)：质量类因子测试",
        "source": "国信证券",
        "date": "2012-09-11",
        "keywords": ["质量因子", "ROE", "ROA", "因子测试"],
        "category": "多因子研究",
        "subcategory": "因子测试",
        "abstract": "系统测试A股市场质量类因子（ROE、ROA、毛利率、资产负债率等）的选股有效性。",
    },
    # ======================== 长城证券_量化研究 ========================
    {
        "id": "cc_001",
        "path": "长城证券_量化研究/长城证券_基于价值和成长的静态选股模型——量化研究系列之1.pdf",
        "title": "基于价值和成长的静态选股模型——量化研究系列之1",
        "source": "长城证券",
        "date": "2011-01-01",
        "keywords": ["价值因子", "成长因子", "静态选股", "GARP"],
        "category": "量化研究系列",
        "subcategory": "选股模型",
        "abstract": "长城证券量化研究系列开篇，构建基于价值和成长双维度的静态选股模型。",
    },
    {
        "id": "cc_002",
        "path": "长城证券_量化研究/长城证券_动态预期选股模型初探——量化研究系列之2.pdf",
        "title": "动态预期选股模型初探——量化研究系列之2",
        "source": "长城证券",
        "date": "2011-01-01",
        "keywords": ["动态预期", "一致预期", "预期修正", "选股模型"],
        "category": "量化研究系列",
        "subcategory": "选股模型",
        "abstract": "基于分析师动态预期数据构建选股模型，探讨预期变化对股价的影响。",
    },
    {
        "id": "cc_003",
        "path": "长城证券_量化研究/长城证券_动态预期+股价动量反转之选股策略——量化研究系列之3.pdf",
        "title": "动态预期+股价动量反转之选股策略——量化研究系列之3",
        "source": "长城证券",
        "date": "2011-01-01",
        "keywords": ["动态预期", "动量", "反转", "选股策略"],
        "category": "量化研究系列",
        "subcategory": "选股模型",
        "abstract": "将动态预期因子与股价动量/反转因子结合，构建复合选股策略。",
    },
    {
        "id": "cc_004",
        "path": "长城证券_量化研究/长城证券_GARP 选股策略研究.pdf",
        "title": "GARP 选股策略研究",
        "source": "长城证券",
        "date": "2011-01-01",
        "keywords": ["GARP", "价值成长", "选股策略"],
        "category": "量化研究系列",
        "subcategory": "GARP策略",
        "abstract": "GARP（合理价格下的成长）选股策略在A股的实证研究。",
    },
    # ======================== 光大证券 ========================
    {
        "id": "gd_001",
        "path": "光大证券/光大证券_2012-09-10_数量化投资：体系与策略.pdf",
        "title": "数量化投资：体系与策略",
        "source": "光大证券",
        "date": "2012-09-10",
        "keywords": ["数量化投资", "体系框架", "策略综述"],
        "category": "方法论",
        "subcategory": "综述",
        "abstract": "光大证券数量化投资体系与策略的全面介绍，涵盖多因子、事件驱动、CTA等策略类别。",
    },
    # ======================== 联合证券_数量化选股 ========================
    {
        "id": "lh_001",
        "path": "联合证券_数量化选股/联合证券_数量化选股系列研究.pdf",
        "title": "数量化选股系列研究（总论）",
        "source": "联合证券",
        "date": "2010-01-01",
        "keywords": ["数量化选股", "多因子", "策略综述"],
        "category": "数量化选股",
        "subcategory": "综述",
        "abstract": "联合证券数量化选股系列研究的总论，建立量化选股的系统框架。",
    },
    {
        "id": "lh_002",
        "path": "联合证券_数量化选股/联合证券_数量化选股系列研究之一.pdf",
        "title": "数量化选股系列研究之一",
        "source": "联合证券",
        "date": "2010-01-01",
        "keywords": ["数量化选股", "因子测试", "实证研究"],
        "category": "数量化选股",
        "subcategory": "实证",
        "abstract": "联合证券数量化选股系列第一篇实证研究。",
    },
    {
        "id": "lh_003",
        "path": "联合证券_数量化选股/联合证券_专题研究：滚动市盈率（TTM）选股策略分析.pdf",
        "title": "专题研究：滚动市盈率（TTM）选股策略分析",
        "source": "联合证券",
        "date": "2010-01-01",
        "keywords": ["市盈率", "TTM", "估值因子", "选股策略"],
        "category": "数量化选股",
        "subcategory": "估值因子",
        "abstract": "专题研究滚动市盈率（TTM PE）作为选股因子的有效性和策略构建。",
    },
    # ======================== 技术指标选股择时 ========================
    {
        "id": "gx_tech_001",
        "path": "技术指标选股择时/国信证券_20120507_技术指标系列(一)_KDJ优化指标.pdf",
        "title": "技术指标系列(一)：KDJ优化指标——6年累积收益17.5倍",
        "source": "国信证券",
        "date": "2012-05-07",
        "keywords": ["KDJ", "技术指标", "优化", "选股择时"],
        "category": "技术指标选股择时",
        "subcategory": "动量指标",
        "abstract": "对经典KDJ指标进行优化改进，在A股实现6年17.5倍的累积收益回测。",
    },
    {
        "id": "gx_tech_002",
        "path": "技术指标选股择时/国信证券_20120508_技术指标系列(二)_ADX平均趋向指标.pdf",
        "title": "技术指标系列(二)：ADX平均趋向指标——每年超过20%的绝对收益",
        "source": "国信证券",
        "date": "2012-05-08",
        "keywords": ["ADX", "趋向指标", "趋势跟踪", "选股择时"],
        "category": "技术指标选股择时",
        "subcategory": "趋势指标",
        "abstract": "利用ADX平均趋向指标构建趋势跟踪选股策略，年化收益超过20%。",
    },
    {
        "id": "gx_tech_003",
        "path": "技术指标选股择时/国信证券_20120509_技术指标系列(三)_AROON阿隆优化指标.pdf",
        "title": "技术指标系列(三)：加入二次确认的AROON阿隆优化指标",
        "source": "国信证券",
        "date": "2012-05-09",
        "keywords": ["AROON", "阿隆指标", "二次确认", "选股择时"],
        "category": "技术指标选股择时",
        "subcategory": "趋势指标",
        "abstract": "对AROON阿隆指标加入二次确认机制，提升趋势识别的准确率。",
    },
    {
        "id": "gx_tech_004",
        "path": "技术指标选股择时/国信证券_20120510_技术指标系列(五)_CCI的顺势而为.pdf",
        "title": "技术指标系列(五)：CCI的顺势而为",
        "source": "国信证券",
        "date": "2012-05-10",
        "keywords": ["CCI", "顺势指标", "选股择时"],
        "category": "技术指标选股择时",
        "subcategory": "动量指标",
        "abstract": "基于CCI（商品通道指数）顺势指标构建选股择时策略。",
    },
    {
        "id": "gx_tech_005",
        "path": "技术指标选股择时/国信证券_20120515_技术指标系列(六)_chaikinAD.pdf",
        "title": "技术指标系列(六)：ChaikinAD——六年年化收益71%",
        "source": "国信证券",
        "date": "2012-05-15",
        "keywords": ["Chaikin", "AD线", "资金流", "选股择时"],
        "category": "技术指标选股择时",
        "subcategory": "资金流指标",
        "abstract": "基于Chaikin A/D线（累积/派发线）构建选股策略，六年年化收益71%。",
    },
    {
        "id": "gx_tech_006",
        "path": "技术指标选股择时/国信证券_20120814_技术指标系列(七)_CMO动量波动指标的运用.pdf",
        "title": "技术指标系列(七)：CMO动量波动指标的运用",
        "source": "国信证券",
        "date": "2012-08-14",
        "keywords": ["CMO", "动量", "波动", "选股择时"],
        "category": "技术指标选股择时",
        "subcategory": "动量指标",
        "abstract": "基于CMO（Chande动量摆动指标）构建动量波动选股策略。",
    },
    {
        "id": "gx_tech_007",
        "path": "技术指标选股择时/国信证券_20120823_技术指标系列(九)_EMV指标改进用法.pdf",
        "title": "技术指标系列(九)：EMV指标改进用法——识别尖部能力强",
        "source": "国信证券",
        "date": "2012-08-23",
        "keywords": ["EMV", "简易波动指标", "顶部识别", "选股择时"],
        "category": "技术指标选股择时",
        "subcategory": "成交量指标",
        "abstract": "改进EMV（简易波动指标）的用法，提升对股价顶部的识别能力。",
    },
    {
        "id": "gx_tech_008",
        "path": "技术指标选股择时/国信证券_20120828_技术指标系列(十)_综合篇.pdf",
        "title": "技术指标系列(十)：综合篇",
        "source": "国信证券",
        "date": "2012-08-28",
        "keywords": ["技术指标", "综合", "多指标", "选股择时"],
        "category": "技术指标选股择时",
        "subcategory": "综合",
        "abstract": "技术指标系列的总结篇，综合运用多个技术指标构建复合选股择时策略。",
    },
    {
        "id": "gx_tech_009",
        "path": "技术指标选股择时/国信证券_20120903_技术指标高频系列(一)_基于KDJ优化指标的高频交易.pdf",
        "title": "技术指标高频系列(一)：基于KDJ优化指标的高频交易",
        "source": "国信证券",
        "date": "2012-09-03",
        "keywords": ["高频交易", "KDJ", "技术指标", "程序化交易"],
        "category": "技术指标选股择时",
        "subcategory": "高频交易",
        "abstract": "将优化后的KDJ指标应用于高频交易场景，探索程序化交易的可行性。",
    },
    # ======================== 学术论文 ========================
    {
        "id": "paper_001",
        "path": "学术论文/因子选股模型在中国市场的实证研究_刘毅.caj",
        "title": "因子选股模型在中国市场的实证研究",
        "source": "学术论文",
        "authors": ["刘毅"],
        "date": "2012-01-01",
        "keywords": ["因子选股", "多因子模型", "中国市场", "实证研究"],
        "category": "学术论文",
        "subcategory": "多因子",
        "abstract": "系统性实证研究多因子选股模型在中国A股市场的适用性和改进方向。",
    },
    {
        "id": "paper_002",
        "path": "学术论文/基于遗传算法的风格选股模型研究_邹运.caj",
        "title": "基于遗传算法的风格选股模型研究",
        "source": "学术论文",
        "authors": ["邹运"],
        "date": "2012-01-01",
        "keywords": ["遗传算法", "风格选股", "智能优化", "机器学习"],
        "category": "学术论文",
        "subcategory": "智能优化",
        "abstract": "运用遗传算法优化风格选股模型的参数和因子组合，探索智能优化在量化选股中的应用。",
    },
    {
        "id": "paper_003",
        "path": "学术论文/指标选股组合及股指期货套期保值策略_秦宇斌.caj",
        "title": "指标选股组合及股指期货套期保值策略",
        "source": "学术论文",
        "authors": ["秦宇斌"],
        "date": "2012-01-01",
        "keywords": ["技术指标", "选股组合", "股指期货", "套期保值"],
        "category": "学术论文",
        "subcategory": "对冲策略",
        "abstract": "构建技术指标选股组合并结合股指期货进行套期保值，研究多空对冲策略的绩效。",
    },
    {
        "id": "paper_004",
        "path": "学术论文/量化交易在中国股市的应用_王俊杰.caj",
        "title": "量化交易在中国股市的应用",
        "source": "学术论文",
        "authors": ["王俊杰"],
        "date": "2012-01-01",
        "keywords": ["量化交易", "中国股市", "策略回测", "综述"],
        "category": "学术论文",
        "subcategory": "综述",
        "abstract": "系统综述量化交易策略在中国股市的应用现状、挑战和前景。",
    },
    # ======================== 量化选股方法论 ========================
    {
        "id": "method_001",
        "path": "量化选股方法论/[量化选股] 动量反转模型.doc",
        "title": "[量化选股] 动量反转模型",
        "source": "方法论汇总",
        "date": "2011-01-01",
        "keywords": ["动量", "反转", "行为金融", "选股模型"],
        "category": "量化选股方法论",
        "subcategory": "动量策略",
        "abstract": "系统阐述动量效应与反转效应的理论基础、实证证据及在A股的选股模型构建方法。",
    },
    {
        "id": "method_002",
        "path": "量化选股方法论/[量化选股] 多因子选股模型.doc",
        "title": "[量化选股] 多因子选股模型",
        "source": "方法论汇总",
        "date": "2011-01-01",
        "keywords": ["多因子模型", "因子构建", "组合优化", "选股框架"],
        "category": "量化选股方法论",
        "subcategory": "多因子",
        "abstract": "全面介绍多因子选股模型的理论框架、因子构建方法、组合优化技术及A股实证。",
    },
    {
        "id": "method_003",
        "path": "量化选股方法论/[量化选股] 行业轮动模型.doc",
        "title": "[量化选股] 行业轮动模型",
        "source": "方法论汇总",
        "date": "2011-01-01",
        "keywords": ["行业轮动", "经济周期", "动量", "选股模型"],
        "category": "量化选股方法论",
        "subcategory": "行业轮动",
        "abstract": "系统阐述行业轮动策略的理论基础、经济周期与行业表现的映射关系及A股实证。",
    },
    {
        "id": "method_004",
        "path": "量化选股方法论/[量化选股] 资金流模型.doc",
        "title": "[量化选股] 资金流模型",
        "source": "方法论汇总",
        "date": "2011-01-01",
        "keywords": ["资金流", "大单", "主力", "选股模型"],
        "category": "量化选股方法论",
        "subcategory": "资金流",
        "abstract": "系统阐述基于资金流向的选股模型，涵盖大单追踪、主力资金识别等方法。",
    },
    {
        "id": "method_005",
        "path": "量化选股方法论/[量化选股] 风格轮动模型.doc",
        "title": "[量化选股] 风格轮动模型",
        "source": "方法论汇总",
        "date": "2011-01-01",
        "keywords": ["风格轮动", "价值", "成长", "大小盘", "选股模型"],
        "category": "量化选股方法论",
        "subcategory": "风格轮动",
        "abstract": "系统阐述市场风格（价值/成长、大盘/小盘）轮动的理论基础及相应的选股策略。",
    },
]


def _scan_actual_files(raw_dir: Path) -> dict[str, list[Path]]:
    """扫描 raw/ 下各分类目录的实际文件。

    Args:
        raw_dir: llm_wiki/raw/ 的绝对路径。

    Returns:
        {category_dir_name: [file_path, ...]} 的映射。
    """
    catalog: dict[str, list[Path]] = {}
    if not raw_dir.exists():
        return catalog
    for child in raw_dir.iterdir():
        if child.is_dir():
            files = [f for f in child.iterdir() if f.is_file() and not f.name.startswith(".")]
            if files:
                catalog[child.name] = files
    return catalog


def _extract_tokens(filename: str) -> set[str]:
    """从文件名中提取匹配用 token。"""
    tokens: set[str] = set()
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename

    # 将 stem 按下划线、空格、中文破折号拆分，每段作为独立 token
    segments = re.split(r"[_ \t——]+", stem)
    for seg in segments:
        seg = seg.strip()
        if len(seg) >= 2:
            tokens.add(seg)

    # 日期 token: 8位连续数字 (YYYYMMDD)
    date_matches = re.findall(r"\d{8}", stem)
    tokens.update(date_matches)
    # 6位数字 (YYYYMM)
    tokens.update(re.findall(r"\d{6}", stem))

    # 系列编号: (一), (1), 之一, 系列五
    series_matches = re.findall(r"系列[一二三四五六七八九十\d]+|之[一二三四五六七八九十\d]+|\([一二三四五六七八九十\d]+\)", stem)
    tokens.update(series_matches)

    # 关键英文缩写 (>=2 大写字母): KDJ, ADX, ATR, CCI, EMV, CMO, GARP, PB, ROE, TTM
    abbrev_matches = re.findall(r"[A-Z]{2,}", stem)
    tokens.update(abbrev_matches)

    # 中文关键词 (>=3 汉字连续段)
    chinese_matches = re.findall(r"[一-鿿]{3,}", stem)
    tokens.update(chinese_matches)
    # 有区分度的 2 字词
    important_bigrams = {"动量", "反转", "选股", "择时", "因子", "行业", "风格", "资金", "技术", "实证", "高频"}
    for cw in re.findall(r"[一-鿿]{2}", stem):
        if cw in important_bigrams:
            tokens.add(cw)

    return tokens


def _match_file(
    report: dict[str, Any],
    catalog: dict[str, list[Path]],
    raw_dir: Path,
) -> Optional[Path]:
    """为一条报告记录匹配实际文件。

    匹配策略:
      1. 精确路径匹配
      2. 在目标分类目录中按 token 重叠度匹配
      3. 全目录扫描作为兜底

    Args:
        report: KNOWN_REPORTS 中的一条记录。
        catalog: _scan_actual_files 返回的文件目录。
        raw_dir: llm_wiki/raw/ 的绝对路径。

    Returns:
        匹配到的文件 Path，未匹配返回 None。
    """
    # 策略 1: 精确匹配
    exact_path = raw_dir / report["path"]
    if exact_path.exists():
        return exact_path

    # 策略 2: 在目标分类目录中按 token 匹配
    expected_category = report["path"].split("/")[0]
    expected_filename = report["path"].split("/")[-1] if "/" in report["path"] else report["path"]
    expected_tokens = _extract_tokens(expected_filename)

    candidates = catalog.get(expected_category, [])

    # 如果分类目录无文件，尝试全目录扫描
    if not candidates:
        for files in catalog.values():
            candidates.extend(files)

    if not candidates:
        return None

    best_match: Optional[Path] = None
    best_score = 0

    for cand in candidates:
        cand_tokens = _extract_tokens(cand.name)
        if not expected_tokens or not cand_tokens:
            continue
        # Jaccard 相似度
        intersection = expected_tokens & cand_tokens
        union = expected_tokens | cand_tokens
        score = len(intersection) / len(union) if union else 0

        # 日期精确匹配加权
        date_expected = {t for t in expected_tokens if re.match(r"^\d{8}$", t)}
        date_actual = {t for t in cand_tokens if re.match(r"^\d{8}$", t)}
        if date_expected and date_expected == date_actual:
            score += 0.5

        if score > best_score:
            best_score = score
            best_match = cand

    # 阈值: 至少 20% token 重叠 (account for 下划线/空格差异)
    return best_match if best_score >= 0.2 else None


def build_index(raw_dir: Path) -> dict[str, Any]:
    """扫描 raw/ 目录，用模糊匹配生成索引。

    Args:
        raw_dir: llm_wiki/raw/ 的绝对路径。

    Returns:
        包含 metadata 和 reports 列表的索引 dict。
    """
    index: dict[str, Any] = {
        "metadata": {
            "name": "量化研究 LLM-Wiki 知识库",
            "version": "2.0",
            "description": "服务于 Quant Harness 的研究报告知识库，覆盖多因子选股、行业轮动、技术指标、动量反转、资金流等量化策略领域。",
            "generated_at": datetime.now().isoformat(),
            "total_reports": 0,
            "total_found": 0,
            "total_missing": 0,
        },
        "reports": [],
    }

    catalog = _scan_actual_files(raw_dir)
    found_count = 0
    missing_count = 0

    for report in KNOWN_REPORTS:
        entry = report.copy()
        matched = _match_file(report, catalog, raw_dir)
        if matched is not None:
            entry["path"] = str(matched.relative_to(raw_dir)).replace("\\", "/")
            entry["status"] = "available"
            entry["file_size_bytes"] = matched.stat().st_size
            entry["file_hash_sha256"] = _hash_file(matched)
            found_count += 1
        else:
            entry["status"] = "missing"
            entry["file_size_bytes"] = None
            entry["file_hash_sha256"] = None
            missing_count += 1
        index["reports"].append(entry)

    # 检查 raw/ 中是否有未被索引覆盖的额外文件
    all_matched_paths: set[str] = set()
    for report in index["reports"]:
        if report["status"] == "available":
            all_matched_paths.add(report["path"])
    extra_count = 0
    for category_files in catalog.values():
        for f in category_files:
            rel = str(f.relative_to(raw_dir)).replace("\\", "/")
            if rel not in all_matched_paths:
                index["reports"].append({
                    "id": f"extra_{f.stem[:20]}",
                    "path": rel,
                    "title": f.stem,
                    "source": "未知",
                    "date": "",
                    "keywords": [],
                    "category": f.parent.name,
                    "subcategory": "未分类",
                    "abstract": "",
                    "status": "available",
                    "file_size_bytes": f.stat().st_size,
                    "file_hash_sha256": _hash_file(f),
                    "note": "自动发现的新文件，待手动补充元数据",
                })
                extra_count += 1

    index["metadata"]["total_reports"] = len(index["reports"])
    index["metadata"]["total_found"] = found_count + extra_count
    index["metadata"]["total_missing"] = missing_count

    return index


def check_missing(raw_dir: Path) -> list[dict[str, str]]:
    """检查哪些报告文件缺失。

    Args:
        raw_dir: llm_wiki/raw/ 的绝对路径。

    Returns:
        缺失报告列表。
    """
    catalog = _scan_actual_files(raw_dir)
    missing: list[dict[str, str]] = []
    for report in KNOWN_REPORTS:
        matched = _match_file(report, catalog, raw_dir)
        if matched is None:
            missing.append({
                "path": report["path"],
                "expected_location": str(raw_dir / report["path"]),
                "title": report["title"],
            })
    return missing


def _hash_file(file_path: Path) -> str:
    """计算文件的 SHA-256 哈希值。"""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def search_index(
    index: dict[str, Any],
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    source: Optional[str] = None,
) -> list[dict[str, Any]]:
    """在索引中搜索报告。

    Args:
        index: build_index 返回的索引 dict。
        keyword: 匹配 title、abstract、keywords 中的关键词。
        category: 按 category 过滤。
        source: 按 source 过滤。

    Returns:
        匹配的报告条目列表。
    """
    results: list[dict[str, Any]] = []
    for report in index["reports"]:
        if category and report.get("category") != category:
            continue
        if source and report.get("source") != source:
            continue
        if keyword:
            kw_lower = keyword.lower()
            searchable = " ".join([
                report.get("title", ""),
                report.get("abstract", ""),
                " ".join(report.get("keywords", [])),
            ]).lower()
            if kw_lower not in searchable:
                continue
        results.append(report)
    return results


def main() -> None:
    """CLI 入口：扫描 raw/ 并生成 index.json。"""
    import argparse

    parser = argparse.ArgumentParser(description="LLM-Wiki 索引构建工具")
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检查缺失文件，不生成索引",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="index.json 输出路径 (默认: llm_wiki/index.json)",
    )
    args = parser.parse_args()

    # 确定路径
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    wiki_dir = script_dir.parent
    raw_dir = wiki_dir / "raw"
    output_path = Path(args.output) if args.output else wiki_dir / "index.json"

    if args.check:
        missing = check_missing(raw_dir)
        if missing:
            print(f"缺失 {len(missing)} 个文件:")
            for m in missing:
                print(f"  [{m['title']}] → {m['expected_location']}")
        else:
            print("所有报告文件均已就位。")
        return

    # 生成索引
    index = build_index(raw_dir)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"索引已生成: {output_path}")
    print(f"  报告总数: {index['metadata']['total_reports']}")
    print(f"  已就位:   {index['metadata']['total_found']}")
    print(f"  缺失:     {index['metadata']['total_missing']}")


if __name__ == "__main__":
    main()
