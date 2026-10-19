# 第一阶段文件替换记录

基于仓库提交 `8aea063ddf8320273392f16837951a6d80f8c935` 整理，日期2026-10-19。用户指定使用本仓库并替换无效旧内容；此次按内容与版本关系处理，Git历史保留。

| 原文件 | 处理 | 原因和后续入口 |
| --- | --- | --- |
| 根README与项目README | 更新 | 改为两个方向的当前入口，区分启动成果与待恢复数据 |
| planning/four-scenarios.md | 旧稿归档，当前文件重写 | 通用四情境不足以落实新方案的12组合与CFE/服务边界 |
| planning/day-1-2-kickoff.md | 旧稿归档，当前文件重写 | 将已完成准备与团队待办分开，并给出可执行交付条件 |
| planning/task-tracker.csv | 移出当前入口并归档 | 旧表状态及依赖过时，当前使用[任务跟踪表](task-tracker.md) |
| planning/data-dictionary-template.csv | 移出当前入口并归档 | 旧表字段覆盖不足，当前使用[详细字典](data/data_dictionary.md)和[空输入模板](data/initial_input.template.json) |
| sources/download-manifest.txt | 改名归档 | 内容是旧忽略规则，并非下载清单；见[原始规则](../sources/archive/original-ignore-rules.txt) |
| 两项论文action-checklist.md | 更新 | 分别列材料、Day 1/2行动与结果边界，保留独立工作流 |

旧启动稿位于 `archive/2026-10-19-before-step1/`，只用于追溯。`sources/local-documents/` 八份研究原稿、原数据源报告、原文献资料及既有数据归档元数据均保留，未把较早版本等同于无用材料。原文中的本机路径和旧相对链接作为历史内容保留，现用入口使用仓库相对链接。

新增 `planning/direction1/`、`planning/direction3/`、`planning/data/`、`data/metadata/public-seed/`、决策日志和协作说明。公开仓库未新增原始CSV、PDF、网盘文件、凭据或本机连接配置。
