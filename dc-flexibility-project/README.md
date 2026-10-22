# 数据中心无碳供能研究项目

方向一当前采用[全球网格需求侧柔性收益研究方案](planning/direction1/全球网格需求侧柔性收益研究方案_20261023.md)：逐网格设置相同计算服务，结合土地、本地绿电、制冷、算力和储能成本计算柔性净收益。方向三继续采用储能转型方案。既有站点方案与原始材料保留，各版本的空间单位和供电边界分别使用。

## 从这里开始

方向一从上述全球网格方案及[方向一入口](planning/direction1/INDEX.md)开始。以下首期计划、真实站点数据模板和四类运营情境保留其原研究范围，不能直接当作全球网格实验配置。

1. 阅读[首1–2日计划](planning/day-1-2-kickoff.md)，在[任务表](planning/task-tracker.md)认领工作。
2. 核对[方向一四类情境](planning/four-scenarios.md)、[方向一详细规格](planning/direction1/INDEX.md)和[方向三比较边界](planning/direction3/INDEX.md)。两条研究线共用来源治理，不混用需求侧控制权限。
3. 查看[数据就绪状态](data/metadata/step1-data-readiness.md)，按[字段字典](planning/data/data_dictionary.md)填写[空输入模板](planning/data/initial_input.template.json)。未知值保留为空并说明原因。
4. 在[决策日志](meeting-notes/2026-10-19-step1-decisions.md)确认网区、样本、阶段目标、服务边界和负责人。

## 当前成果与证据

| 内容 | 当前状态 | 使用边界 |
| --- | --- | --- |
| 八份研究原文与导入校验 | 仓库已归档，原文保留 | 最新采用版本见[材料索引](sources/local-documents/README.md) |
| 全球网格需求侧柔性方案 | 已明确逐网格比较、土地与供电边界、成本及验证要求 | 研究设计；尚未求解全球网格模型或形成收益结果 |
| 方向一计算细节 | 已在仓库找到并纳入规格 | 原文拟定扫描值仍须审阅，不视为实测参数 |
| NC、NCC、Azure及需求模拟 | 仓库有历史清单和网盘归档记录 | 本轮未恢复全套数据，不能据此声称已清洗或已复算 |
| Alibaba机器规格与Zeus功率/训练小样本 | 本地已有小样本及结构核验记录 | 可检查字段与测量边界，不能代替设施实际负荷或SLA |
| PNNL储能参考资料 | 本地已有两份官方PDF | 价格地域、年份、工程边界和参数提取尚待核验 |
| 研究输入与情境配置 | 模板和草案已建立，运行开关关闭 | 无虚构站点数据，无优化收益、最优容量或撞击风险结果 |

## 目录分工

- `sources/`：研究原稿、数据源核查报告和前期文献资料；原稿不作为已完成分析。
- `planning/`：计划、任务、四类情境、两个方向的独立规格和共用数据模板；`archive/` 保存被替换的旧启动稿。
- `data/metadata/`：历史数据清单、恢复入口、本轮可用性判断与公开小样本校验。
- `data/raw/`、`data/interim/`、`data/processed/`：本地数据目录，数据文件默认不提交Git。
- `analysis/`：后续处理与模型实现；`results/`：经过核验的输出，当前无研究结果。
- `papers/applied-energy/`、`papers/bird-risk/`：会议中的两条独立论文任务；行动清单已更新，原稿和正式要求待补齐。
- `meeting-notes/`：决定、待审问题与同步记录。

## 数据源报告的用法

[数据源核查报告](sources/research-report.md)支持分层构库的设计：全球候选层、区域核验层及AI大型项目补充层分别保留来源和位置类型。报告所称记录数量和核查日期属于原报告快照，本轮没有逐站重新验证。城市质心不能用于设施周边暴露分析，设施容量不能直接充当小时负荷；许可及跨源重复仍需按[来源审阅表](planning/data/source_review.md)处理。

前期数据包括 NC 全年供需输入、Azure 请求算例、NCC 多年气候计算资料、2023–2025 年需求模拟及周核验样例，已归档到百度网盘 `/科研数据/数据中心研究/20261019`。初始 71 份文件约 22.4 GB，另有研究原文及归档清单。56 份普通数据已删除本地副本，9 份 OneDrive 数据已核实为仅联机文件，本地缓存报告值均为零，3 份来源说明保留。使用前按[归档清单](data/metadata/baidu-netdisk-archive-20261019-final-20261019T131312Z.json)下载到相应 `data/raw/` 路径。年份、小时分辨率与复用条件见[既有计算说明](data/metadata/existing-computations.md)；[数据清单](data/metadata/existing-data-inventory.json)为迁移前核查快照，其中本地可访问字段记录核查时状态。本机历史来源映射保存在已忽略的 `data/raw/local-sources.json`。归档和缓存清理记录不表示研究输入已恢复或模型已复算。

## 近期需要团队确认

目标设施与电网边界、可获得的服务/SLA和表计数据、CFE阶段目标与小时约束、投资口径与价格基年、任务负责人及同步日期。会议中的“明天”“每2–3天”“两周内”保留为相对安排，不推定当前截止日。

## 文件检查

[本次检查记录](data/metadata/step1-validation.json)覆盖原稿哈希、当前文档链接、JSON与未运行状态；不验证科研模型。具备Python环境后，可在仓库根目录运行 `python dc-flexibility-project/analysis/check_step1.py` 复核工作包，追加 `--write-report` 可更新检查记录。
