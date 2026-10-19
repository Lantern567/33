# 数据中心电力柔性研究工作区

研究数据中心的供能侧与计算需求侧柔性、24×7 无碳电力匹配，以及储能配置和分期转型。

- [项目说明](dc-flexibility-project/README.md)：研究目标、目录分工和启动安排。
- [本地研究材料索引](dc-flexibility-project/sources/local-documents/README.md)：2026 年 10 月 15–18 日形成的八份调研、研究方案和计算说明。
- [既有计算与数据入口](dc-flexibility-project/data/metadata/existing-computations.md)：历史气候、未来情景、全年小时输入及三年需求模拟的核查与复用条件。
- [网盘归档清单](dc-flexibility-project/data/metadata/baidu-netdisk-archive-20261019-final-20261019T131312Z.json)：云端目录、逐文件校验记录与本地清理状态。
- [四类运营情境](dc-flexibility-project/planning/four-scenarios.md)：现有启动框架，使用时结合材料索引中的方案和计算说明。
- [工作区协作规范](AGENTS.md)：输入版本、研究证据、数据存放及提交约定。

本次初始化日期为 2026 年 10 月 19 日，新增材料范围为数据中心研究。研究原文保留原始文件名及内容，文件来源、大小和 SHA-256 记录在[导入清单](dc-flexibility-project/sources/local-documents/import-manifest.json)中。

数据目录分为 `data/raw/`、`data/interim/`、`data/processed/` 和 `data/metadata/`，数据内容不提交 Git；脚本、核验输出和会议记录分别放在 `analysis/`、`results/` 和 `meeting-notes/`。选定数据已归档到百度网盘 `/科研数据/数据中心研究/20261019`，初始 71 份文件约 22.4 GB，另有研究原文及归档清单。56 份普通数据已删除本地副本，9 份 OneDrive 数据已核实为仅联机文件，本地缓存报告值均为零，3 份来源说明保留。使用数据时按[归档清单](dc-flexibility-project/data/metadata/baidu-netdisk-archive-20261019-final-20261019T131312Z.json)下载到相应 `data/raw/` 路径；[数据清单](dc-flexibility-project/data/metadata/existing-data-inventory.json)保留迁移前核查快照。后续参数确认和模型计算按具体研究要求开展。
