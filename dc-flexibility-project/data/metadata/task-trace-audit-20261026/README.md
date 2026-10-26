# 任务来源核验记录

核验日期：2026 年 10 月 26 日。说明与复现命令见[任务记录粒度与柔性约束](../../../docs/task-trace-flexibility.md)。

- `asi-acme-validation.json`：Acme Kalos 作业、ASI 相对日 109 的完整 24 小时，以及 CPU/GPU 四档规模功率接口的服务器计算记录。
- `independent-checks.json`：实际作业在 48 个时间段内的独立交集计算核对和 5 项异常输入检查。
- `lisa-summary.json`：Lisa 全部 1596963 条作业、官方文件 MD5、时间粒度、CPU/GPU 分区、核心小时和两种累计粒度的核对。

原始作业、ASI 分片与含任务标识的派生表保存在本地或服务器的 `data/raw/task-trace-audit-20261026/`、`data/processed/task-trace-audit-20261026/`。公开仓库保存汇总与校验值。

上述记录验证任务读取、资源累计和功率接口；业务截止时间及暂停权限缺失时保留未知。Lisa 时间未携带时区，输出保留源时间及相对小时，不直接赋予 UTC 时区。30 秒监测的粒度由来源说明和整合代码确认，本轮未运行完整监测标定。
