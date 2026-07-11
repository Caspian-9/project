# Wiki 操作日志

> 追加模式。记录每次 ingest、query、lint 操作。
> 格式: `## [YYYY-MM-DD] {operation} | {brief description}`

---

## [2026-07-11] setup | Wiki 初始化

- 创建 wiki/ 目录结构和 _schema.md
- 初始化 _index.md 导航页
- raw/ 中有 84 篇研究报告待 ingest
- 已生成 index.json (JSON 检索索引)

## [2026-07-11] batch-ingest | 批量生成源文件摘要页

- 从 index.json 批量生成 75 篇 sources/ 页面
- 每页包含 PDF 第一页提取的摘要 + 关键词推测的实体关联
- 更新 _index.md 全量导航目录
- 9 篇 DOC/CAJ 待手动处理后 ingest

## [2026-07-11] generate-entities | 生成实体页面

- 10 个策略实体 (3 growing, 7 stub) — 含定义 + 相关来源链接
- 6 个因子实体 (4 growing, 2 stub) — 含A股实证来源表
- 8 个技术指标 (6 growing, 2 stub) — 含关键绩效数据
- 5 个概念 (4 growing, 1 stub) — 含定义 + 引用来源
- 2 个综合分析 (evolving) — 动量vs反转 + 技术指标横向对比
- 所有实体均从 75 篇源文件摘要中自动提取相关内容
