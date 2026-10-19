# 公开初始数据接收记录

接收日期：2026-10-19（Asia/Shanghai）。先前的本地启动工作已取得小规模真实公开文件、核对来源并做结构检查。本次入库前对 10 个本地文件重新计算 SHA-256 与大小，均与接收清单一致。Git 仓库只提交本报告和元数据；下列文件链接指向上游来源，数据及 PDF 并未上传。未重建逐时负荷、未求解调度模型、未优化储能方案。

## 已取得且保留在本地的文件

| 文件 | 记录数 | 字段数 | 缺失单元格 | 用途边界 |
|---|---:|---:|---:|---|
| [summary_power_a40.csv](https://raw.githubusercontent.com/ml-energy/zeus/master/examples/research_reproducibility/zeus_nsdi23/trace/summary_power_a40.csv) | 453 | 7 | 0 | 指定 GPU 实验配置功耗/耗时汇总；不是设施逐时负荷 |
| [summary_power_p100.csv](https://raw.githubusercontent.com/ml-energy/zeus/master/examples/research_reproducibility/zeus_nsdi23/trace/summary_power_p100.csv) | 270 | 7 | 0 | 指定 GPU 实验配置功耗/耗时汇总；不是设施逐时负荷 |
| [summary_power_rtx6000.csv](https://raw.githubusercontent.com/ml-energy/zeus/master/examples/research_reproducibility/zeus_nsdi23/trace/summary_power_rtx6000.csv) | 410 | 7 | 0 | 指定 GPU 实验配置功耗/耗时汇总；不是设施逐时负荷 |
| [summary_power_v100.csv](https://raw.githubusercontent.com/ml-energy/zeus/master/examples/research_reproducibility/zeus_nsdi23/trace/summary_power_v100.csv) | 476 | 7 | 0 | 指定 GPU 实验配置功耗/耗时汇总；不是设施逐时负荷 |
| [summary_train.csv](https://raw.githubusercontent.com/ml-energy/zeus/master/examples/research_reproducibility/zeus_nsdi23/trace/summary_train.csv) | 3759 | 8 | 849 | 训练配置与达标 epoch 汇总 |
| [pai_machine_spec.csv](https://aliopentrace.oss-cn-beijing.aliyuncs.com/v2020GPUTraces/pai_machine_spec.tar.gz) | 1897 | 5 | 0 | 机器静态规格；不是任务表、负荷或功耗 |

[Alibaba 原始压缩包](https://aliopentrace.oss-cn-beijing.aliyuncs.com/v2020GPUTraces/pai_machine_spec.tar.gz)与解压 CSV 的 SHA256 均与官方 README 一致。CSV 无表头；字段顺序按官方说明解释，原文件未添加标题或更改。

[PNNL 2022 成本与性能报告](https://www.pnnl.gov/sites/default/files/media/file/ESGC%20Cost%20Performance%20Report%202022%20PNNL-33283.pdf)和[2024 LCOS 工作簿说明](https://www.pnnl.gov/sites/default/files/media/file/ESGC_LCOS_Workbook_v2024_Documentation.pdf)已按原字节归档并验证 PDF 文件头；本次未完成全文/表格核验或参数提取。

## 结构核查与使用限制

- 全部 CSV 列数一致；缺失标记按空字符串、NA、NaN、null、None、n/a 计数。原始标记保留，未补零。各字段观测范围、重复检查和 GPU 类别见 [csv_checks.json](csv_checks.json)。
- Zeus 四种 GPU 文件独立保存；GPU 型号来自文件名，不在原 CSV 字段内。合并前必须显式增加 gpu_type 与 source_file 来源列。
- Zeus train 行按配置、run 与 target_metric 区分；同一训练配置可有多个目标指标，不能把每行等同于独立训练任务。连接 power 表前还需核对 dataset、network、batch_size、optimizer、目标口径与 GPU 型号，避免多对多放大。
- 功耗单位为 W，epoch 时长为 s；不能将 average_power 直接当成设施 kW/MW 或一个小时的 kWh。
- CPU-only 机器和零 GPU 容量均保留。零值、缺失值及未知含义分别处理。
- 这个公开小样本集合不含风光逐时序列、电价/碳强度、PUE、SLA/截止时间，也不含可用的全量任务到达轨迹；这些仍需后续准备。
- summary_train.csv 的 849 个缺失值全部位于 target_epoch；其含义需结合上游实验协议确认，不能当作 0 epoch 或已完成任务。target_metric 在不同数据集中使用不同指标/量纲，不可跨任务直接比较。

## 下一步待办

- [ ] 确定研究地区、年份、时区与数据中心规模，再取相匹配的电网/风光数据。
- [ ] 在存储与口径确认后单独获取 Alibaba 任务/实例等大文件，并检验脱敏时间映射；本次未下载。
- [ ] 为 Zeus 定义目标指标、允许 batch size/power limit 与任务映射，不把实验汇总误认作生产负荷。
- [ ] 从 PNNL 表格逐项记录技术、时长、规模、成本年份、地域、单位和页码；中国研究成本本地化仍待完成。
- [ ] 公开再分发前核验每项资料许可；本地小样本用于研究工作区来源归档；当前 Git 仓库仅含元数据。

## 来源与许可

- [Alibaba GPU v2020 官方数据说明](https://github.com/alibaba/clusterdata/blob/master/cluster-trace-gpu-v2020/README.md)；[研究/学习用途声明](https://github.com/alibaba/clusterdata#our-motivation)。未发现根目录 LICENSE，不推断商业使用许可。
- [Zeus 官方 trace 目录](https://github.com/ml-energy/zeus/tree/master/examples/research_reproducibility/zeus_nsdi23/trace)；[仓库许可证](https://github.com/ml-energy/zeus/blob/master/LICENSE)，[上游许可证](https://raw.githubusercontent.com/ml-energy/zeus/master/LICENSE)。
- [PNNL 储能成本与性能数据库](https://www.pnnl.gov/energy-storage-cost-and-performance-database)。报告作为待提取参数的资料；没有生成任何报价或已验证成本参数。

所有下载 URL、取回时间、字节数、SHA256 和检查结果见 [manifest.json](manifest.json)。下载内容均未作为脚本执行。


## 在其他电脑恢复

按[本地恢复说明](README.md)从既有本地成果包复制，或从 manifest 的官方来源下载并核验 SHA-256。清单里的 `path` 是本地公开资料根目录的相对路径，并非仓库已提交的文件路径。公开小样本与已有 NC/NCC 网盘资料是两条独立来源链；后者的恢复状态见[数据准备状态](../step1-data-readiness.md)。
