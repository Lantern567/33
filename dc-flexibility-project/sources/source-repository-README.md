# 全球数据中心 POI 数据调研

本仓库汇总全球数据中心 POI、建筑轮廓、设施地址和技术属性数据源，并核查它们的空间粒度、覆盖范围、字段完整性、开放程度与许可限制。

数据核查日期：**2026-07-27**；研究方案更新：**2026-07-29**。

> 本仓库只发布调研结果、来源索引和可复现查询，不再分发受限制的上游原始数据。

## 核心结论

“数据中心 POI 数据更细”至少包含三种含义：

1. **空间几何细**：精确到单栋建筑 Polygon 或园区边界；
2. **设施点位细**：一条记录对应一个设施或园区，并有经纬度或完整地址；
3. **设施属性细**：包含功率、面积、PUE、芯片、冷却方式、状态和时间线。

当前最值得使用的数据组合是：

| 目标 | 推荐数据 |
|---|---|
| 美国建筑级气候风险 | PNNL IM3 Open Source Data Center Atlas |
| 中国设施级气候风险 | 中国 2024 年 1,005 个大型数据中心核验点 |
| 全球设施级开放底表 | PeeringDB + OpenStreetMap |
| 全球候选设施召回 | Data Center Watch，必须按来源和精度分层 |
| AI 数据中心功率与建设时序 | Epoch AI AI Data Centers |
| 商业深字段增强 | Data Center Map、TeleGeography、Baxtel、S&P Global 451 |

## 已核验的数据规模

| 数据源 | 本次核验结果 | 实际粒度 | 主要限制 |
|---|---:|---|---|
| PNNL IM3 | 1,468 个空间要素：1,239 建筑面、135 园区面、94 点 | 建筑/园区 | 仅美国 |
| 中国大型数据中心 2024 | 1,005 条，1,003 组唯一坐标 | 经核验设施点 | 仅中国大型设施 |
| PeeringDB | 5,860 条；5,256 条有坐标；169 国 | 互联设施/楼宇地址 | 对互联和托管机房有明显偏向 |
| Data Center Watch | 27,525 条；15,927 条有坐标；179 国 | 混合粒度 | 有城市质心和跨来源重复 |
| OpenStreetMap 子集 | 4,521 条有坐标记录 | OSM 点或建筑对象派生点 | 全球完整性不均，公开 Overpass 全局查询易超时 |
| Epoch AI | 75 个 AI 园区/项目 | 园区/项目 | 主表无经纬度，不是全行业名录 |
| 米兰都会区 | 67 条 | 设施/项目地址 | 无经纬度，部分记录包含多个楼宇 |
| 国家绿色数据中心名单 | 44 个名称 | 名称清单 | 无地址和坐标，不是 POI 表 |

## Data Center Watch 的来源组成

Data Center Watch 是聚合库，而非单一机构自行采集的全球底表。本次下载的 27,525 条记录包括：

| 上游来源 | 条数 | 坐标情况 | 主要内容 |
|---|---:|---:|---|
| ATLAS | 16,096 | 4,573 条城市质心 | 全球名称、城市和地址目录 |
| PeeringDB | 5,219 | 全部有坐标 | 互联/托管设施 |
| OpenStreetMap | 4,521 | 全部有坐标 | OSM 数据中心对象 |
| FracTracker | 1,608 | 全部有坐标 | 美国运行、规划、在建、暂停和取消项目 |
| Epoch AI | 75 | 无坐标，65 条有地址 | 大型 AI 园区、功率和算力属性 |
| 人工补充 | 6 | 有坐标 | 特殊企业或科研计算设施 |

其中只有 616 条公开披露 MW，75 条有 IT power，约 972 条有面积。ATLAS 坐标是城市质心，不应直接用于建筑附近热岛、洪水深度或百米级气候暴露分析。

## 使用设施级精细数据的研究

- **Local heat islands and vegetation losses are microclimatic consequences of global data centers**：使用 S&P Global 的 13,587 条精确坐标；清理父子设施后为 12,639 条，热生态分析约使用 8,300 个唯一坐标。原始坐标未公开，论文地图对坐标做了随机偏移。
- **Global data–water symbiosis reduces AI infrastructure's carbon and water footprint**：使用 4,775 个全球数据中心，融合 OSM、IM3、Epoch、运营商页面和 Google Maps；完整全球点位未在公开补充表中提供。
- **Spatial distribution and environmental attributes dataset of China's large-scale data centers in 2024**：公开 1,005 个经人工和卫星影像核验的中国设施点，并提供 10 m 概率栅格。
- **The impact of data center construction on urban energy green transformation**：输入为 97 个 OSM 设施坐标，但实证分析单元最终是 282 个地级市。

## 推荐的精度字段

合并多源 POI 时，至少应保留：

```text
source
source_id
source_url
record_level
geometry_precision
coordinate_source
location_verified
status
status_as_of
license
redistribution_allowed
```

建议的 `geometry_precision` 分类：

```text
building_polygon
campus_polygon
verified_point
address_geocode
city_centroid
name_only
```

不要将云区域、城市质心、园区、单栋建筑和租户机房直接混为同一层级。

## 仓库内容

- [`docs/research-report.md`](docs/research-report.md)：详细来源核查与使用建议；
- [`docs/climate-24x7-cfe-literature-review.md`](docs/climate-24x7-cfe-literature-review.md)：气候变化对数据中心 24/7 CFE 的文献证据、研究缺口与论文设计；
- [`docs/research-proposal.md`](docs/research-proposal.md)：完整研究方案，包含 S1–S5 地理匹配情境、需求—供给耦合、未来气候压力测试与适应优化；
- [`docs/demand-growth-technology-learning.md`](docs/demand-growth-technology-learning.md)：最近三年需求模板、未来需求增长、风光储学习曲线与三因素全因子实验；
- [`sources.csv`](sources.csv)：机器可读来源清单；
- [`queries/overpass_data_centers.ql`](queries/overpass_data_centers.ql)：OSM 数据中心查询；

## 许可提醒

- OSM、IM3 和 Data Center Watch 涉及 ODbL/DbCL；公开衍生数据库时需要署名并核查 Share-Alike 条款。
- Epoch AI 和中国 1,005 点数据集标注为 CC BY 4.0。
- PeeringDB AUP 对整库传递和再分发有限制。
- Ringmast4r/Global-Data-Center-Map 标注 All Rights Reserved，仅适合线索核验。
- Data Center Map、TeleGeography、Baxtel、Cloudscene 和 S&P Global 451 属于商业或授权数据，不应抓取或再分发。

本仓库的统计数字是特定下载日期的快照，不代表上游数据库永远保持相同数量。

## 主要链接

- [PeeringDB API](https://www.peeringdb.com/apidocs/)
- [OpenStreetMap `telecom=data_center`](https://wiki.openstreetmap.org/wiki/Tag:telecom%3Ddata_center)
- [Data Center Watch](https://www.datacentr.net/)
- [Epoch AI AI Data Centers](https://epoch.ai/data/ai-data-centers)
- [PNNL IM3 Data Center Atlas](https://immm-sfa.github.io/datacenter-atlas/)
- [中国 1,005 个大型数据中心数据集](https://doi.org/10.57760/sciencedb.32970)
- [米兰都会区数据集](https://zenodo.org/records/20377445)
