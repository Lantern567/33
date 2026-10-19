# 数据中心电力柔性研究工作区

研究数据中心的供能侧与计算需求侧柔性、24×7 无碳电力匹配，以及储能配置和分期转型。

- [项目说明](dc-flexibility-project/README.md)：研究目标、目录分工和启动安排。
- [本地研究材料索引](dc-flexibility-project/sources/local-documents/README.md)：2026 年 10 月 15–18 日形成的八份调研、研究方案和计算说明。
- [既有计算与数据入口](dc-flexibility-project/data/metadata/existing-computations.md)：核实历史气候、未来情景、全年小时输入及三年需求模拟，连接本机已有数据。
- [四类运营情境](dc-flexibility-project/planning/four-scenarios.md)：现有启动框架，使用时结合材料索引中的方案和计算说明。
- [工作区协作规范](AGENTS.md)：输入版本、研究证据、数据存放及提交约定。

本次初始化日期为 2026 年 10 月 19 日，新增材料范围为数据中心研究。研究原文保留原始文件名及内容，文件来源、大小和 SHA-256 记录在[导入清单](dc-flexibility-project/sources/local-documents/import-manifest.json)中。

数据目录分为 `data/raw/`、`data/interim/`、`data/processed/` 和 `data/metadata/`。前三类数据默认保留在本地；脚本、核验输出和会议记录分别放在 `analysis/`、`results/` 和 `meeting-notes/`。五个本地数据入口已连接前期计算资料，文件与时间覆盖见[数据清单](dc-flexibility-project/data/metadata/existing-data-inventory.json)。后续参数确认和模型计算按具体研究要求开展。
