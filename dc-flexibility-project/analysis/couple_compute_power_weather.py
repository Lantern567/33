import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import psychrolib
import requests
from bs4 import BeautifulSoup
from scipy.optimize import nnls


PROJECT = Path(__file__).resolve().parents[1]
VERSION = "20261025-v4"
OUT = PROJECT / f"results/compute-center-data-audit-20261022/coupled-power-weather-{VERSION}"
RAW = PROJECT / f"data/raw/coupled-power-weather-{VERSION}"
PRIOR = PROJECT / "results/compute-center-data-audit-20261022/observed-trace-extrapolation-20261024-v3"
ESIF = Path("D:/onedrive/01_科研与论文/12_气候对data center影响/data/24x7_cfe/raw/observed_demand/nlr_esif")
WEATHER = PROJECT / "results/compute-center-data-audit-20261022/gpu397/weather-trial/known-gpu-locations-hourly-unit-it.parquet"
SPEC_URL = "https://ftp.spec.org/power_ssj2008/results/res2021q1/power_ssj2008-20210221-01063.html"
GPU_URL = "https://arxiv.org/html/2412.08602v1"
SIZES = [1, 10, 100, 500]
YEARS = [2023, 2024, 2025]
COMPONENTS = ["outdoor_cooling_mw", "hvac_mw", "pump_mw", "other_mw"]
psychrolib.SetUnitSystem(psychrolib.SI)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(url, name):
    path = RAW / name
    if not path.exists():
        response = requests.get(url, timeout=90)
        response.raise_for_status()
        path.write_bytes(response.content)
    return path


def power_anchors():
    cpu_path = fetch(SPEC_URL, "specpower-hpe-dl385-7763.html")
    soup = BeautifulSoup(cpu_path.read_bytes(), "html.parser")
    cpu = []
    for row in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in row.find_all("td", recursive=False)]
        if len(cells) == 5 and cells[0].endswith("%") and cells[1].endswith("%"):
            cpu.append({"load_fraction": float(cells[1].removesuffix("%")) / 100,
                        "target_load_fraction": float(cells[0].removesuffix("%")) / 100,
                        "node_power_w": float(cells[3].replace(",", ""))})
        if len(cells) == 4 and cells[0] == "Active Idle" and not any(item["load_fraction"] == 0 for item in cpu):
            cpu.append({"load_fraction": 0., "target_load_fraction": 0., "node_power_w": float(cells[2])})
    cpu = pd.DataFrame(cpu).drop_duplicates().sort_values("load_fraction")
    assert len(cpu) == 11 and cpu.node_power_w.iloc[0] == 120 and cpu.node_power_w.iloc[-1] == 546
    cpu.to_csv(OUT / "cpu-measured-power-anchors.csv", index=False, encoding="utf-8-sig")

    gpu_path = fetch(GPU_URL, "latif-2024-hgx-h100.html")
    tables = pd.read_html(io.StringIO(gpu_path.read_text(encoding="utf-8")))
    gpu_table = next(table for table in tables if "Median Power (kW)" in table.columns)
    gpu_rows = []
    for row in gpu_table.to_dict("records"):
        label = str(row["Training Workload"])
        gpu_rows.append({"measurement": label, "load_fraction": 0. if label == "Idle Node" else float(row["Average GPU Utilization (%)"]) / 100,
                         "node_power_w": float(row["Median Power (kW)"]) * 1000})
    gpu = pd.DataFrame(gpu_rows)
    assert len(gpu) == 6
    assert gpu.loc[gpu.measurement.eq("Idle Node"), "node_power_w"].item() == 1860
    assert gpu.node_power_w.max() == 8430
    gpu.to_csv(OUT / "gpu-measured-power-anchors.csv", index=False, encoding="utf-8-sig")
    return cpu, gpu, [
        {"source": "SPECpower_ssj2008 HPE DL385 Gen10 Plus", "url": SPEC_URL, "path": str(cpu_path), "sha256": sha256(cpu_path),
         "configuration": "2×AMD EPYC 7763，128物理核心，256 GB内存；测试设置关闭Core Performance Boost。"},
        {"source": "Latif et al. 2024, arXiv:2412.08602v1 Table I", "url": GPU_URL, "path": str(gpu_path), "sha256": sha256(gpu_path),
         "configuration": "8×H100 80GB HGX节点，EPYC 9354宿主CPU，1.5 TB内存；节点PDU功率，RDHx另路供电。"}]


def esif_training_data():
    source = pd.read_parquet(PRIOR / "esif-observed-qualified-hours.parquet")
    power_path = ESIF / "esif_power_metrics.parquet"
    weather_path = ESIF / "esif_weather.parquet"
    native = pd.read_parquet(weather_path, columns=["ts", "outdoor_air_temp", "outdoor_air_humidity"],
                             filters=[("ts", ">=", pd.Timestamp("2025-01-01")), ("ts", "<", pd.Timestamp("2026-01-01"))])
    assert not native.ts.duplicated().any()
    native = native.set_index("ts").sort_index()
    valid = native.outdoor_air_humidity.gt(0) & native.outdoor_air_humidity.le(100) & native.outdoor_air_temp.notna()
    native = native.loc[valid]
    native["temperature_c"] = (native.outdoor_air_temp - 32) * 5 / 9
    native["relative_humidity_pct"] = native.outdoor_air_humidity
    regular = native[["temperature_c", "relative_humidity_pct"]].resample("1min").mean()
    hourly = regular.resample("1h").mean()
    hourly = hourly.loc[regular.temperature_c.resample("1h").count().ge(48)]
    paired = source.join(hourly, how="inner")
    paired["dew_point_c"] = psychrolib.GetTDewPointFromRelHum(paired.temperature_c.to_numpy(), paired.relative_humidity_pct.to_numpy()/100)
    # 保留发布的独立分项，塔过滤泵已经包含在cooling_kw中。
    power = pd.read_parquet(power_path, columns=["ts", "cooling_kw", "hvac_kw", "pump_kw", "plug_and_light_kw"],
                            filters=[("ts", ">=", pd.Timestamp("2025-01-01")), ("ts", "<", pd.Timestamp("2026-01-01"))])
    power = power.set_index("ts").sort_index().resample("1min").mean().resample("1h").mean()
    for target, original in zip(COMPONENTS, ["cooling_kw", "hvac_kw", "pump_kw", "plug_and_light_kw"]):
        paired[target] = power[original].reindex(paired.index) / 1000
    assert paired.notna().all().all()
    np.testing.assert_allclose(paired[COMPONENTS].sum(axis=1), paired.aux_mw, atol=1e-9)
    paired.to_parquet(OUT / "esif-paired-power-weather-calibration-hours.parquet")
    paired.to_csv(OUT / "esif-paired-power-weather-calibration-hours.csv", encoding="utf-8-sig")
    return paired, [{"source": "ESIF power", "path": str(power_path), "sha256": sha256(power_path)},
                    {"source": "ESIF onsite outdoor weather", "path": str(weather_path), "sha256": sha256(weather_path)}]


def knots(frame):
    return {"dry_warm": frame.temperature_c.quantile([.25, .75]).to_list(),
            "dew_warm": frame.dew_point_c.quantile([.25, .75]).to_list(),
            "dry_cold": float(frame.temperature_c.quantile(.1))}


def features(frame, reference_mw, k, thermal_only=False):
    q = frame.it_mw.to_numpy() / reference_mw
    values = [np.ones(len(frame)), q, q**2]
    names = ["capacity_fixed", "heat_linear", "heat_squared_over_capacity"]
    if not thermal_only:
        for i, threshold in enumerate(k["dry_warm"]):
            values.append(q * np.maximum(frame.temperature_c.to_numpy() - threshold, 0))
            names.append(f"heat_times_dry_hinge_{i+1}")
        for i, threshold in enumerate(k["dew_warm"]):
            values.append(q * np.maximum(frame.dew_point_c.to_numpy() - threshold, 0))
            names.append(f"heat_times_dew_hinge_{i+1}")
        values.append(np.maximum(k["dry_cold"] - frame.temperature_c.to_numpy(), 0))
        names.append("cold_weather_fixed_heater")
    return np.column_stack(values), names


def fit(frame, reference_mw, thermal_only=False):
    k = knots(frame)
    x, names = features(frame, reference_mw, k, thermal_only)
    y = frame[COMPONENTS].to_numpy()/reference_mw
    scale = np.maximum(np.sqrt((x*x).mean(axis=0)), 1e-12)
    beta = np.column_stack([nnls(x/scale, y[:, i], maxiter=10000)[0]/scale for i in range(4)])
    return {"reference_mw": reference_mw, "knots": k, "feature_names": names, "coefficients": beta.tolist(), "thermal_only": thermal_only}


def predict(frame, model, capacity_mw):
    x, names = features(frame, capacity_mw, model["knots"], model["thermal_only"])
    assert names == model["feature_names"]
    return x @ np.asarray(model["coefficients"]) * capacity_mw


def errors(actual, predicted):
    residual = predicted - actual
    return {"mae_kw": float(np.abs(residual).mean()*1000), "rmse_kw": float(np.sqrt(np.mean(residual**2))*1000),
            "mean_bias_kw": float(residual.mean()*1000), "rmse_percent_mean": float(np.sqrt(np.mean(residual**2))/np.mean(actual)*100),
            "r_squared": float(1-np.sum(residual**2)/np.sum((actual-actual.mean())**2))}


def calibrate(paired):
    reference = float(paired.it_mw.max())
    cutoff = paired.index.max().floor("D") - pd.Timedelta(days=27)
    train, test = paired.loc[paired.index < cutoff], paired.loc[paired.index >= cutoff]
    predictions = test[["it_mw", "temperature_c", "relative_humidity_pct", "dew_point_c"]].copy()
    metrics = []
    actual = test[COMPONENTS[:3]].sum(axis=1).to_numpy()
    for thermal_only in [True, False]:
        model = fit(train, reference, thermal_only)
        estimated = predict(test, model, reference)
        label = "heat_only" if thermal_only else "heat_temperature_humidity"
        cooling = estimated[:, :3].sum(axis=1)
        predictions[f"{label}_cooling_mw"] = cooling
        metrics.append({"model": label, "train_hours": len(train), "test_hours": len(test), **errors(actual, cooling)})
    predictions["observed_cooling_mw"] = actual
    predictions.to_csv(OUT / "cooling-chronological-holdout-predictions.csv", encoding="utf-8-sig")
    pd.DataFrame(metrics).to_csv(OUT / "cooling-holdout-validation.csv", index=False, encoding="utf-8-sig")
    residual = actual - predictions.heat_temperature_humidity_cooling_mw.to_numpy()
    final = fit(paired, reference)
    final["chronological_validation"] = metrics
    final["holdout_start_source_clock"] = str(cutoff)
    final["calibration_hours"] = len(paired)
    final["calibration_range"] = {column: [float(paired[column].min()), float(paired[column].max())]
                                  for column in ["temperature_c", "dew_point_c"]}
    final["calibration_range"]["it_fraction"] = [float(paired.it_mw.min()/reference), 1.]
    final["cooling_holdout_residual_quantiles_per_reference_mw"] = (np.quantile(residual, [.05, .95])/reference).tolist()
    final["interpretation"] = "ESIF同时间IT、室外温湿度和分项电功率拟合的非负分段线性响应；属于原冷却配置的转移情境，未标定COP、供水温度或目标硬件改造。"
    (OUT / "cooling-calibration.json").write_text(json.dumps(final, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return final


def resource_year(key, year):
    frame = pd.read_parquet(PRIOR / f"{key}-replayed-8760-hours.parquet")
    mapping = pd.read_parquet(PRIOR / "every-hour-source-provenance.parquet")
    mapping = mapping.loc[mapping.source.eq(key)].reset_index(drop=True)
    if year == 2024:
        original = pd.read_parquet(PRIOR / f"{key}-observed-qualified-hours.parquet")
        last = pd.Timestamp(mapping.source_time_index.iloc[-1])
        addition = original.loc[last+pd.Timedelta(hours=1):last+pd.Timedelta(hours=24)].copy().reset_index()
        assert len(addition) == 24
        extra = addition.reindex(columns=frame.columns)
        frame = pd.concat([frame, extra], ignore_index=True)
        mapping = pd.concat([mapping, pd.DataFrame({"source": key, "block": 53, "source_time_index": addition.source_time_index.astype(str)})], ignore_index=True)
    for column in ["hour_of_scenario_year"]:
        frame[column] = np.arange(1, len(frame)+1)
        mapping[column] = frame[column]
    required = 8784 if year == 2024 else 8760
    assert len(frame) == len(mapping) == required
    # 累计量在新日历上重新计算，运行强度逐值保持源记录。
    frame = frame.loc[:, ~frame.columns.str.startswith("cumulative_")].copy()
    mapping.insert(1, "calendar_year", year)
    mapping.to_parquet(OUT / f"{key}-{year}-resource-hour-provenance.parquet", index=False)
    return frame


def hardware_table():
    rows = []
    for profile in ["cpu_fast", "cpu_rnd", "gpu"]:
        full_w, cards, cores = (8430., 8, None) if profile == "gpu" else (546., 0, 128)
        for k in SIZES:
            count = int(np.floor(k*1e6/full_w))
            rows.append({"profile": profile, "reference_it_capacity_mw": k, "node_count": count,
                         "node_full_reference_w": full_w, "installed_reference_it_mw": count*full_w/1e6,
                         "unallocated_reference_mw": k-count*full_w/1e6,
                         "gpu_count": cards*count, "physical_cpu_cores": None if cores is None else cores*count,
                         "gpu_node_manufacturer_reference_kw": 10.2 if profile == "gpu" else None,
                         "node_price": None})
    result = pd.DataFrame(rows)
    result.to_csv(OUT / "hardware-scale-parameters.csv", index=False, encoding="utf-8-sig")
    return result


def calculate(cpu, gpu, model):
    weather = pd.read_parquet(WEATHER)
    assert weather.groupby("logical_site_id").size().eq(26304).all()
    weather["dew_point_c"] = psychrolib.GetTDewPointFromRelHum(weather.temperature_c.to_numpy(), weather.relative_humidity_pct.to_numpy()/100)
    weather = weather[["logical_site_id", "example_label", "time_utc", "calendar_year", "temperature_c", "relative_humidity_pct", "dew_point_c"]].copy()
    weather.to_parquet(OUT / "five-location-hourly-weather-2023-2025.parquet", index=False)
    hardware = hardware_table()
    gpu_curve = gpu.loc[~gpu.measurement.str.contains("no CPU", regex=False)].sort_values("load_fraction")
    annual, monthly, uncertainty = [], [], []
    for profile in ["cpu_fast", "cpu_rnd", "gpu"]:
        for year in YEARS:
            resource = resource_year(profile, year)
            u = resource.gpu_request_per_inventory_unit.to_numpy() if profile == "gpu" else resource.cpu_use_fraction.to_numpy()
            assert np.isfinite(u).all() and ((u >= 0) & (u <= 1)).all()
            anchors = gpu_curve if profile == "gpu" else cpu
            node_w = np.interp(u, anchors.load_fraction, anchors.node_power_w)
            for site, source_weather in weather.loc[weather.calendar_year.eq(year)].groupby("logical_site_id"):
                w = source_weather.sort_values("time_utc").reset_index(drop=True)
                assert len(w) == len(resource)
                for k in SIZES:
                    hw = hardware.loc[hardware.profile.eq(profile) & hardware.reference_it_capacity_mw.eq(k)].iloc[0]
                    cap = float(hw.installed_reference_it_mw)
                    frame = w.copy()
                    frame["profile"], frame["reference_it_capacity_mw"] = profile, k
                    frame["resource_fraction"] = u
                    frame["node_count"], frame["gpu_count"] = int(hw.node_count), int(hw.gpu_count)
                    frame["it_mw"] = node_w*hw.node_count/1e6
                    frame["heat_demand_mw_th"] = frame.it_mw
                    prediction = predict(frame, model, cap)
                    for i, column in enumerate(COMPONENTS):
                        frame[column] = prediction[:, i]
                    frame["cooling_mw"] = frame[COMPONENTS[:3]].sum(axis=1)
                    frame["facility_mw"] = frame.it_mw + frame.cooling_mw + frame.other_mw
                    frame["pue"] = frame.facility_mw / frame.it_mw
                    frame["it_fraction_of_reference"] = frame.it_mw/cap
                    support = np.ones(len(frame), dtype=bool)
                    for column in ["temperature_c", "dew_point_c"]:
                        lower, upper = model["calibration_range"][column]
                        support &= frame[column].between(lower, upper).to_numpy()
                    qlo, qhi = model["calibration_range"]["it_fraction"]
                    frame["outside_calibration_weather"] = ~support
                    frame["outside_calibration_it_range"] = ~frame.it_fraction_of_reference.between(qlo, qhi)
                    lo, hi = model["cooling_holdout_residual_quantiles_per_reference_mw"]
                    frame["cooling_residual_band_low_mw"] = np.maximum(0, frame.cooling_mw + lo*cap)
                    frame["cooling_residual_band_high_mw"] = np.maximum(0, frame.cooling_mw + hi*cap)
                    if profile == "gpu":
                        frame["allocated_gpu_equivalents"] = hw.gpu_count*u
                        frame["cumulative_allocated_gpu_hours"] = frame.allocated_gpu_equivalents.cumsum()
                    else:
                        frame["cpu_core_usage_proxy"] = hw.physical_cpu_cores*u
                        frame["cumulative_cpu_core_proxy_hours"] = frame.cpu_core_usage_proxy.cumsum()
                    for component in ["it", "cooling", "other", "facility"]:
                        frame[f"cumulative_{component}_mwh"] = frame[f"{component}_mw"].cumsum()
                    path = OUT / "hourly" / profile / site / str(year)
                    path.mkdir(parents=True, exist_ok=True)
                    frame.to_parquet(path / f"{k}MW.parquet", index=False)
                    if year == 2025 and k == 10:
                        frame.to_csv(path / f"{k}MW.csv", index=False, encoding="utf-8-sig")
                    row = {"profile": profile, "site_id": site, "location": w.example_label.iloc[0], "year": year,
                           "reference_it_capacity_mw": k, "installed_reference_it_mw": cap,
                           "node_count": int(hw.node_count), "gpu_count": int(hw.gpu_count), "hours": len(frame),
                           "mean_resource_fraction": float(u.mean()), "mean_it_mw": float(frame.it_mw.mean()),
                           "mean_facility_mw": float(frame.facility_mw.mean()), "max_facility_mw": float(frame.facility_mw.max()),
                           "heat_energy_mwh_th": float(frame.heat_demand_mw_th.sum()),
                           "energy_weighted_pue": float(frame.facility_mw.sum()/frame.it_mw.sum()),
                           "outside_calibration_weather_hours": int(frame.outside_calibration_weather.sum()),
                           "outside_calibration_it_hours": int(frame.outside_calibration_it_range.sum())}
                    resource_column = "allocated_gpu_equivalents" if profile == "gpu" else "cpu_core_usage_proxy"
                    row["annual_resource_proxy_hours"] = float(frame[resource_column].sum())
                    row["resource_proxy_unit"] = "allocated_gpu_equivalent_hours" if profile == "gpu" else "cpu_core_usage_proxy_hours"
                    for component in ["it", "cooling", "other", "facility"]:
                        row[f"annual_{component}_mwh"] = float(frame[f"{component}_mw"].sum())
                    annual.append(row)
                    for month, group in frame.groupby(frame.time_utc.dt.month):
                        monthly.append({"profile": profile, "site_id": site, "location": row["location"], "year": year,
                                        "reference_it_capacity_mw": k, "month": int(month), "hours": len(group),
                                        **{f"{component}_mwh": float(group[f"{component}_mw"].sum()) for component in ["it", "cooling", "other", "facility"]}})
                    if k == 10 and year == 2025 and profile == "gpu":
                        lower_curve = gpu.loc[~gpu.measurement.str.contains("+", regex=False)].sort_values("load_fraction")
                        low_it = np.interp(u, lower_curve.load_fraction, lower_curve.node_power_w)*hw.node_count/1e6
                        alternative = frame.copy()
                        alternative["it_mw"] = low_it
                        low_cooling = predict(alternative, model, cap).sum(axis=1)
                        uncertainty.append({"site_id": site, "location": row["location"], "profile": profile,
                                            "comparison": "满负载锚点7.97对8.43kW，其余锚点不变", "reference_it_capacity_mw": k,
                                            "main_facility_mwh": row["annual_facility_mwh"],
                                            "alternative_facility_mwh": float(low_it.sum()+low_cooling.sum())})
                    if k == 10 and year == 2025:
                        mixed_w = anchors.node_power_w.iloc[0] + u*(anchors.node_power_w.iloc[-1]-anchors.node_power_w.iloc[0])
                        mixed_it = mixed_w*hw.node_count/1e6
                        alternative = frame.copy()
                        alternative["it_mw"] = mixed_it
                        mixed_support = predict(alternative, model, cap).sum(axis=1)
                        uncertainty.append({"site_id": site, "location": row["location"], "profile": profile,
                                            "comparison": "同资源份额：各节点同强度与满载/空闲节点混合", "reference_it_capacity_mw": k,
                                            "main_facility_mwh": row["annual_facility_mwh"],
                                            "alternative_facility_mwh": float(mixed_it.sum()+mixed_support.sum())})
            print(json.dumps({"completed_profile": profile, "year": year}, ensure_ascii=False), flush=True)
    pd.DataFrame(annual).to_csv(OUT / "annual-load-summary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(monthly).to_csv(OUT / "monthly-load-summary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(uncertainty).to_csv(OUT / "power-mapping-sensitivity.csv", index=False, encoding="utf-8-sig")
    return len(annual)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    cpu, gpu, hardware_sources = power_anchors()
    paired, esif_sources = esif_training_data()
    model = calibrate(paired)
    cases = calculate(cpu, gpu, model)
    inputs = hardware_sources + esif_sources + [{"source": "五地点ERA5 2023—2025年小时温湿度", "path": str(WEATHER), "sha256": sha256(WEATHER)}]
    for key in ["cpu_fast", "cpu_rnd", "gpu"]:
        for suffix in ["observed-qualified-hours.parquet", "replayed-8760-hours.parquet"]:
            path = PRIOR / f"{key}-{suffix}"
            inputs.append({"source": key, "path": str(path), "sha256": sha256(path)})
    manifest = {"version": VERSION, "cases": cases, "main_types": ["CPU", "GPU"], "profiles": ["cpu_fast", "cpu_rnd", "gpu"],
                "cpu_rnd_role": "同CPU类型的另一组资源样本敏感性", "locations": 5, "years": YEARS, "sizes_mw": SIZES,
                "time_step_hours": 1, "hours_per_year": {2023: 8760, 2024: 8784, 2025: 8760},
                "scale_definition": "参考满载IT容量；按CPU实测546W/节点和GPU联合压力实测8430W/节点配置整机并向下取整。",
                "gpu_manufacturer_reference_kw": 10.2, "thermal_approximation": "小时尺度忽略蓄热及建筑得热，设备散热MW热近似等于节点IT功率MW电。",
                "inputs": inputs, "cooling": model,
                "assumptions": ["CPU使用率作为SPECpower相对基准负载的迁移代理；GPU申请份额作为HGX实测利用率—功率曲线的迁移代理。",
                                "未设置全年平均忙碌比例；使用既有逐小时原值重放；不同年份使用相同相对资源路径，闰年从最后源周延长24小时。",
                                "全部参考节点持续通电，逐时等强度映射；未识别真实任务装箱和单机负载分布。",
                                "同一ESIF冷却与配套系统响应分别用于CPU/GPU参考情境，未验证其供水温度和热接口与目标节点兼容。",
                                "气象来自五个地点的ERA5资料；这些地点用于气候情境，不代表真实场站的设备配置和耗电。",
                                "参考规模下固定与可变配套功率均按相同模块重复；未识别规模效率、冷却机组切换、设备降额或工程容量不足。"],
                "not_identified": ["申请份额对应的真实GPU利用率及H100吞吐等价", "外部共享交换网络和存储功率", "目标冷却设备COP、供水温度及容量", "绝对设备与设施报价"],
                "validation_scope": "冷却关系只在ESIF时间留出集验证；CPU/GPU资源到瓦特的跨数据集映射尚无同机联合验证。"}
    (OUT / "coupled-model-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"cases": cases, "cooling_validation": model["chronological_validation"], "calibration_range": model["calibration_range"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
