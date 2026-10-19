# 数据源核查报告

## 1. 数据源分级

### 1.1 可直接获取并适合研究

#### PeeringDB

- REST API：`https://www.peeringdb.com/api/fac`
- 2026-07-27 快照共 5,860 个设施；5,256 个有经纬度，5,804 个有地址，覆盖 169 个国家或地区。
- 数据包括设施名称、所属机构、地址、经纬度、园区 ID、接入网络数、IX 数和运营商数。
- 适合全球互联设施和托管机房研究，不代表企业私有机房、全部 hyperscale 园区或规划项目。

#### OpenStreetMap

- 推荐标签：`telecom=data_center`、`building=data_center`，并辅助检查 `industrial=data_center` 和历史标签变体。
- 可包含建筑 Polygon、园区关系或 Point。
- 公共 Overpass 端点不适合一次性执行全球重查询，建议按国家或网格分片。
- 使用 ODbL。

#### PNNL IM3 Open Source Data Center Atlas

- 美国专题数据。
- footprints 文件包含 1,239 个建筑 Polygon、135 个园区 MultiPolygon 和 94 个 Point。
- 是本次核查中空间几何最细的公开数据。
- 数据源含 OSM 派生内容，使用时遵守 ODbL。

#### Epoch AI

- 75 个大型 AI 数据中心项目。
- 主表包含名称、地址、所有者、用户、功率、资本成本和芯片类型；子表提供建设时间线、芯片数量、冷机和冷却塔。
- 将相邻且共享运营主体的楼宇视为一个项目，属于 campus/project 粒度。
- CC BY 4.0。

#### 中国 2024 年大型数据中心数据集

- 1,005 条设施记录，覆盖 31 个省级地区。
- 字段包括经纬度、温度、降水、海拔、气候区和设施类型，字段无缺失。
- 有 1,003 组唯一经纬度；使用前仍应处理重复 ID 和重复坐标。
- 数据 DOI：`10.57760/sciencedb.32970`；数据集元数据许可为 CC BY 4.0。

#### 米兰都会区数据集

- 67 条设施/项目记录。
- 包含 municipality、operator、name、address、nominal power range 和 status。
- 55 条有地址，无经纬度，需要二次地理编码。
- Zenodo 记录标注 Copyright，不能默认自由再分发。

#### 国家绿色数据中心公示名单

- PDF 共 44 个名称。
- 无地址、坐标和容量，只能作为权威名称清单或地理编码输入。

### 1.2 开放聚合数据

#### Data Center Watch

- 完整目录 27,525 条；15,927 条有坐标；23,466 条有地址；覆盖 179 个国家。
- 字段包括名称、运营商、所有者、状态、设施类型、地址、坐标、MW、IT power、面积、H100-equivalent、芯片、租户、供电、冷却、用途、网络数、来源和说明。
- 只有 616 条有 MW、75 条有 IT power、约 972 条有面积。
- ATLAS 行使用城市质心；不同来源在去重前可能双计数。

建议将 Data Center Watch 划分为：

1. `PeeringDB / OSM / FracTracker + coordinates`：设施级候选；
2. `Epoch + address`：待地理编码的 AI 园区；
3. `ATLAS + city centroid`：只用于城市/国家分布；
4. 特殊人工记录：逐条人工核查。

### 1.3 商业或受限来源

#### Data Center Map

- 支持 CSV、GeoJSON、SHP、KMZ 和 KML。
- 可包含坐标、地址、功率、白空间、建筑面积、PUE 和 Tier。
- 完整数据需要采购，只允许内部使用，不得再分发。

#### TeleGeography

- 商业 building-level geocoded data。
- 需申请样表或订阅。

#### Baxtel、Cloudscene、S&P Global 451

- 覆盖广、设施属性较深。
- 无公开完整批量下载，需商业授权。

### 1.4 不适合直接作为生产底表

#### Ringmast4r/Global-Data-Center-Map

- CSV 有 18,110 条，GeoJSON 有 6,131 个 Point。
- 国家字段存在未规范值，来源链指向 Data Center Map。
- 许可证为 All Rights Reserved，只适合结构检查和线索发现。

## 2. 对气候影响研究的建议

### 建筑尺度

使用 IM3 或 OSM 建筑 Polygon。设施点只能表示位置，不能可靠代表占地、地表覆盖和热力边界。

### 设施尺度

全球样本可使用 PeeringDB + OSM；中国使用 1,005 个核验点；美国使用 IM3 和 FracTracker。

### 城市或国家尺度

可以使用 Data Center Watch 的 ATLAS 目录，但必须将坐标标记为 `city_centroid`，不能用于局地暴露。

### 去重

推荐组合使用标准化名称、运营商、地址、园区 ID 和空间距离。50—100 m 聚类适合初筛，但不能自动合并同一园区内的独立楼宇。

### 时间和状态

不要把 PeeringDB 或 OSM 聚合后的 `operating` 当作严格运营核验。规划和建设状态优先采用 FracTracker、政府许可、运营商公告或商业项目跟踪库。

## 3. 论文证据

### 全球微气候研究

`Local heat islands and vegetation losses are microclimatic consequences of global data centers` 使用 S&P Global 的精确全球设施坐标，但原始数据为商业数据，未公开。

### 全球数据—水共生

`Global data–water symbiosis reduces AI infrastructure's carbon and water footprint` 使用 4,775 个数据中心，并直接计算数据中心与污水处理设施的距离。公开补充表主要是汇总结果，完整设施坐标未完全释放。

### 中国设施级数据

`Spatial distribution and environmental attributes dataset of China's large-scale data centers in 2024` 公开了 1,005 个核验点，是目前中国设施级气候和环境暴露研究的重要开放数据。

## 4. 结论

不存在单一、完整、免费、长期稳定且同时包含建筑几何和深层技术属性的全球数据中心底库。建议建立分层数据库：

- PeeringDB/OSM：开放全球基础层；
- IM3：中国 1,005 点、米兰和政府名单：区域核验层；
- Epoch AI：大型 AI 项目属性层；
- Data Center Watch：候选召回和来源索引层；
- 商业数据库：内部增强和交叉验证层。

