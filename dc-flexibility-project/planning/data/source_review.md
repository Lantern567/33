# 初始数据来源核对

整理日期：2026-10-19。此文件将本次对话中先前已读的官方资料记录、两份用户方案和仓库既有核查报告合并到工作区；本次仓库整理没有重新在线核验全部来源、记录数或许可。下表区分“已读官方说明”和“已取得原始文件”；实际公开文件的接收、哈希和结构检查集中记录在[公开资料接收报告](../../data/metadata/public-seed/intake_report.md)。

## 本次读取的官方入口

| ID | 官方来源 | 可以支撑的准备 | 不能直接提供/当前状态 |
|---|---|---|---|
| PUB01 | [Alibaba GPU v2020说明](https://raw.githubusercontent.com/alibaba/clusterdata/master/cluster-trace-gpu-v2020/README.md) | 任务/实例/机器字段与小型机器规格入口 | 脱敏时间不是真实日历；实例均值不是功率时序；完整任务包未批量取回 |
| PUB02 | [Alibaba GPU v2026字段](https://raw.githubusercontent.com/alibaba/clusterdata/master/cluster-trace-gpu-v2026/docs/schema.md) | pod/server小时长表和匿名关联设计 | 相对日/小时、无真实日历；标识不得跨数据集直接拼接；本次读字段未取回全量 |
| PUB03 | [Microsoft Philly说明](https://raw.githubusercontent.com/msr-fiddle/philly-traces/master/README.md) | 任务重试和资源利用字段的备用映射 | 任务截尾与缺时需处理；虚拟集群不是地理站点；未取回大包 |
| PUB04 | [Zeus测量表说明](https://raw.githubusercontent.com/ml-energy/zeus/master/examples/research_reproducibility/zeus_nsdi23/trace/README.md) | 配置、功率上限、每轮耗时、GPU平均功率的校准准备 | 汇总测量不是设施逐时耗电；取回文件见接收报告 |
| PUB05 | [ERA5小时数据](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview) | 气象变量、时间分辨率和数据请求入口 | 本次只读入口；未定试点/时段，不提交全球下载；模拟出力不是可认领合同电量 |
| PUB06 | [DOE 2022储能评估](https://www.energy.gov/cmei/2022-grid-energy-storage-technology-cost-and-performance-assessment) | 技术成本、寿命、增补替换与费用类别的参考 | 地区和价格年需换算；LCOS不能替代本研究全过程成本 |
| PUB07 | [PNNL 2024核算说明](https://www.pnnl.gov/sites/default/files/media/file/ESGC_LCOS_Workbook_v2024_Documentation.pdf) | 成本、损耗、增补、更换、残值核算的参考 | 是说明文件，不是现场报价；本次未提取已校准参数 |
| PUB08 | [Epoch AI字段说明](https://epoch.ai/data/data-centers-documentation/records) | 大型AI设施属性的候选补充入口 | 本次已读取文档入口，未取回设施底表；功率容量不是负荷时序 |

官方说明的可读性不等于底表完整性、许可适配或模型适用性已验证。引用这些资料形成论文结论前仍应核对具体版本、表/页和研究地区；本阶段只完成入库准备和小文件接收。

## 既有POI报告的复用范围

已归档[数据源核查报告原件](../../sources/research-report.md)及[来源索引原件](../../sources/sources.csv)。其2026-07-27统计保留历史快照身份，本次没有重新验证全部POI规模和许可。

方向一可用设施位置/运营商/网区线索构造站点候选，但公开集群匿名机器ID不能直接关联真实设施。方向三只对真实既有站点讨论储能配置，POI列表不能解释成最优设施选址。城市质心不得用于设施精细暴露，容量缺失不得由点位数量推算用电。

优先沿用的旧来源角色为：PeeringDB/OSM作全球位置候选；IM3作美国几何候选；中国2024数据作中国设施核对；Epoch补充AI属性；Data Center Watch用于候选召回和来源线索。是否正式采用取决于试点、精度和当前许可，不能据此声称已取得底表。

## 数据到模型的分工

公开轨迹与GPU测量支持方向一的字段适配和原型设计；真实任务授权/期限仍须另取。方向三优先补连续设施负荷、可执行的小时CFE供给与合同、储能全生命周期参数三类决定性资料。共享天气、费用、属性和资产字典，分别保持各方向的服务与决策权限。


## 仓库新增可见证据与状态修正

本次检查仓库发现，方向一的[计算细节](../../sources/local-documents/方向一_CFE约束与柔性收益_计算细节_20261018.md)已归档，因此不再把该文件列为“缺失”。它提供定义和方法，不构成求解结果。

NC/NCC 不是“完全没有来源线索”：仓库已有[计算说明](../../data/metadata/existing-computations.md)、[迁移前清单](../../data/metadata/existing-data-inventory.json)和[网盘归档记录](../../data/metadata/baidu-netdisk-archive-20261019.json)。本轮仅核对这些元数据，没有重新下载其中的大文件或重算任何研究结果。两份方案引用的完整 NC/NCC 工程、运行环境、最终气候组合和参数版本，仍不能由选定文件清单推定齐备。

按证据等级整理的可用性和恢复清单见[Step 1 数据准备状态](../../data/metadata/step1-data-readiness.md)。来源登记应将归档元数据已读、文件已恢复、结构已核验及模型可用分别记录。
