# CPU/GPU 算力中心：IT、散热与温湿度耦合逐小时负荷

版本：20261025-v4；计算、核验和服务器归档日期：2026-10-25。

本工作包采用现有 CPU/GPU 资源时间序列、实测整机功率点、ESIF 冷却与温湿度配对数据，以及五个地点的 ERA5 天气，生成 1、10、100、500 MW 参考 IT 规模的逐小时负荷。类型包括 CPU 和 GPU；`cpu_rnd` 是 CPU 的另一组样本敏感性。GPU 使用申请资源曲线，未区分推理和训练。

[阅读完整报告](CPU_GPU算力中心_IT散热与温湿度耦合负荷报告_20261025_v4.pdf)。[年度结果](annual-load-summary.csv)、[月度结果](monthly-load-summary.csv)、[设备数量](hardware-scale-parameters.csv)、[核验记录](verification-results.json)可直接查看。

## 参数与尺度

| 项目 | 参数及依据 |
| --- | --- |
| CPU 资源路径 | Bitbrains fast；rnd 为样本敏感性；采用已有逐小时原值重放 |
| GPU 资源路径 | Alibaba 申请资源份额；申请份额到实测利用率的映射属于跨数据集代理 |
| CPU 功率 | SPECpower HPE DL385 Gen10 Plus；2×EPYC 7763、128 物理核心、256 GB；空闲 120 W、实测高负载 546 W，使用 11 个实测点插值 |
| GPU 功率 | 8×H100 HGX 整机、EPYC 9354 宿主、1.5 TB 内存；空闲 1.86 kW，GPU 利用率 36%/77%/93% 对应 4.68/6.26/7.92 kW，CPU 与 GPU 联合压力点为 8.43 kW |
| 规模定义 | 参考高负载 IT 功率预算；CPU 按 546 W/节点、GPU 按 8.43 kW/节点，节点数量向下取整 |
| 散热需求 | 小时尺度忽略蓄热时，IT 散热 MW热近似等于 IT 功率 MW电；散热量单独报告 |
| 配套系统 | 使用 ESIF 同时间 IT、室外干球温度、相对湿度及分项电功率拟合；相对湿度换算露点参与拟合 |
| 年份与粒度 | 2023、2024、2025 年；每条记录 1 小时；分别为 8760、8784、8760 小时 |
| 气候情境 | 孟菲斯、博洛尼亚、橡树岭、盖恩斯维尔、卡亚尼；各地点采用相同的相对 IT 资源路径 |

1、10、100、500 MW GPU 情境分别为 118、1186、11862、59311 个节点，即 944、9488、94896、474488 张 H100 参考卡。CPU 情境分别为 1831、18315、183150、915750 个节点。全部节点持续通电；逐节点负载分布另做敏感性分析。全年平均资源份额由输入曲线自然形成。

这些规模表示实测高负载 IT 参考预算。工程容量还需按设备铭牌与配电、冷却容量核算，例如 500 MW GPU 参考情境对应约 604.97 MW 的 10.2 kW/节点厂商参考额定功率，配套设施用电另计。

## 从资源曲线计算功率与累计用量

逐小时资源份额先映射到单节点实测功率，再乘节点数量得到 `it_mw`。配套模型以归一化 IT 负载、干球温度和露点为输入，分别预测室外冷却、HVAC、泵与其他配套功率。各小时满足：

```text
cooling_mw = outdoor_cooling_mw + hvac_mw + pump_mw
facility_mw = it_mw + cooling_mw + other_mw
heat_demand_mw_th ≈ it_mw
```

功率字段为该小时平均 MW，乘以 1 小时后相加得到 MWh。CPU 资源累计为核心占用代理小时；GPU 为申请的等效卡小时。散热累计采用 MWh热。设备散热属于热量指标，设施电量由上述电功率分项相加得到。

## 文件及读取

仓库保存报告、图件、模型系数、设备功率点、年度/月度汇总、验证结果和生成脚本。完整逐小时文件、输入重放轨迹和来源映射归档在用户的研究服务器；来源数据继续按各自许可使用。

完整服务器包文件名为 `full-results-20261025-v4.zip`，大小 240376758 字节，SHA-256 为 `c54bea8cf4384da48969af8d3da85603efd0ed80295568a56aa4e1b47da03dcf`。解压后的 `package/` 包含 `outputs/`、`analysis/`、`resource-inputs/` 和 `metadata/`。其中：

- `outputs/hourly/{profile}/{site_id}/{year}/{size}MW.parquet`：全部 180 条全年曲线。
- `outputs/hourly/{profile}/{site_id}/2025/10MW.csv`：15 条可直接用表格软件读取的样例。
- `outputs/{profile}-{year}-resource-hour-provenance.parquet`：每个重放小时的来源记录。
- `outputs/annual-load-summary.csv`、`monthly-load-summary.csv`：各情境汇总。

例如，橡树岭对应 `site_id=c3ba734448beea13`。在已解压包中运行：

```python
from pathlib import Path
import pandas as pd

outputs = Path("package/outputs")
curve = pd.read_parquet(outputs / "hourly/gpu/c3ba734448beea13/2025/10MW.parquet")
print(curve[["time_utc", "it_mw", "heat_demand_mw_th", "cooling_mw", "facility_mw"]].head())
print("全年设施电量 MWh:", curve["facility_mw"].sum())
daily_mwh = curve.set_index("time_utc")["facility_mw"].resample("1D").sum()
```

`time_utc` 是天气与目标曲线的 UTC 小时索引。`resource_fraction` 是输入轨迹份额；`outside_calibration_weather` 与 `outside_calibration_it_range` 标记模型校准范围以外的小时。`cooling_residual_band_*` 由 ESIF 留出残差构成，适用范围限于该经验模型。

[生成脚本](../../../analysis/couple_compute_power_weather.py)及绘图、报告、核验脚本保留本次计算的来源版本。重新生成全部结果前，需要恢复其中 `PRIOR`、`ESIF` 和 `WEATHER` 所指输入；报告构建还使用原报告第一页和本机中文字体。读取已生成的 Parquet/CSV 无需运行这些构建脚本。

## 核验及科学适用范围

180 条情境曲线包括 120 条 CPU/GPU 主情境和 60 条 CPU rnd 敏感性，共核验 1578240 条逐小时记录、78912 个资源来源小时及 2160 条月度汇总。电功率分项、资源累计、月年度累计、闰年、设备取整和同 IT 路径地点对照均通过本次核验。

冷却模型由 5447 个 ESIF 配对小时校准，以末尾 672 小时作为时间留出集。冷却预测 RMSE 为 17.754 kW，等于测试集平均冷却功率的 10.276%，R²=0.374。校准范围为干球 −19.31～38.13℃、露点 −29.42～17.68℃、归一化 IT 负载 0.2315～1.0；跨范围小时在输出中标记。

CPU/GPU 资源到瓦特的迁移尚无同机联合测量验证。GPU 申请份额不能证明实际 GPU 利用率或 H100 吞吐等价。ESIF 的冷却配置迁移到目标硬件时，供水温度、热接口和设备容量仍需工程核验。外部共享网络与存储功率、绝对价格尚未识别；价格字段保留为空。五个地点用于气候对照，这些曲线属于研究情境；实际园区设备数量和历史耗电仍需独立证据。

## 来源

- [SPECpower HPE DL385 Gen10 Plus 完整结果](https://ftp.spec.org/power_ssj2008/results/res2021q1/power_ssj2008-20210221-01063.html)
- [8×H100 HGX 实测节点功率，Latif 等，Table I](https://arxiv.org/html/2412.08602v1)
- CPU、GPU、ESIF 和 ERA5 的原始数据记录、处理口径与输入 SHA-256 保留于完整包的 `metadata/` 和模型清单；报告列明对应来源。

## 两个研究方向的使用方式

方向一 `33` 使用 `facility_mw` 作为供需匹配与柔性研究的负荷基线，并保留资源需求与服务约束。方向二 `data-center-carbon-free-storage` 使用同版本负荷作为储能研究输入，另行设定电价、合同、储能与 CFE 约束。两项目分别维护研究方案，共用经过版本标记的负荷证据。
