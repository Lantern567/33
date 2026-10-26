import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from compute_load import ComputeLoadModel
from compute_load.model import SIZES_MW, sha256
from task_trace_inputs import integrate_jobs, load_acme, read_asi_hour, resource_profile


def native_granularity(tasks):
    result = {}
    for hardware, selected in tasks.groupby("hardware"):
        valid = selected.loc[selected.interval_valid]
        result[hardware] = {
            "rows": len(selected), "valid_execution_intervals": len(valid),
            "missing_or_invalid_intervals": len(selected) - len(valid),
            "zero_runtime_intervals": int(valid.runtime_s.eq(0).sum()),
            "runtime_seconds_quantiles": {str(q): float(valid.runtime_s.quantile(q)) for q in (.25, .5, .75, .9, .99)},
            "runtime_under_60s_fraction": float(valid.runtime_s.lt(60).mean()),
            "runtime_under_300s_fraction": float(valid.runtime_s.lt(300).mean()),
            "runtime_under_3600s_fraction": float(valid.runtime_s.lt(3600).mean()),
            "type_counts": selected.type.value_counts().to_dict(),
            "constraint_unknown_rows": int(selected.flexibility_status.eq("unknown").sum()),
        }
    return result


def event_peak(tasks, resource):
    events = pd.concat([pd.Series(tasks[resource].to_numpy(), index=tasks.start_time),
                        pd.Series(-tasks[resource].to_numpy(), index=tasks.end_time)])
    return float(events.groupby(level=0).sum().sort_index().cumsum().max())


def audit(raw, output, weather_path=None):
    raw, output = Path(raw), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    tasks = load_acme(raw / "trace_kalos.csv")
    tasks.to_parquet(output / "acme-tasks.parquet", index=False)
    valid = tasks.loc[tasks.interval_valid].copy()
    beginning, ending = valid.start_time.min().floor("h"), valid.end_time.max().ceil("h")
    edges = pd.date_range(beginning, ending, freq="h")
    five_edges = pd.date_range(beginning, ending, freq="5min")
    demands, fives, checks = [], [], {}
    for hardware, resource in (("cpu", "cpu_num"), ("gpu", "gpu_num")):
        selected = valid.loc[valid.hardware.eq(hardware)]
        hourly = integrate_jobs(selected, edges, resource)
        five = integrate_jobs(selected, five_edges, resource)
        expected = float((selected.runtime_s * selected[resource]).sum() / 3600)
        np.testing.assert_allclose(hourly.resource_hours.sum(), expected, rtol=1e-11, atol=1e-7)
        rebinned = five.set_index("time_utc").resource_hours.resample("h").sum()
        np.testing.assert_allclose(rebinned.to_numpy(), hourly.resource_hours, rtol=1e-10, atol=1e-7)
        hourly["hardware"], five["hardware"] = hardware, hardware
        demands.append(hourly)
        fives.append(five)
        checks[hardware] = {"integrated_resource_hours": expected,
                            "maximum_concurrent_allocated_units": event_peak(selected, resource),
                            "mean_allocated_units": float(hourly.mean_allocated_units.mean()),
                            "five_minute_to_hourly_conservation": "passed"}
    demand = pd.concat(demands, ignore_index=True)
    demand.to_parquet(output / "acme-hourly-resource-demand.parquet", index=False)
    pd.concat(fives, ignore_index=True).to_parquet(output / "acme-5min-resource-demand.parquet", index=False)
    manifest = json.loads((raw / "download-manifest.json").read_text(encoding="utf-8"))
    grouped, quality = [], []
    for day in sorted(manifest["asi_days"]):
        for hour in sorted(manifest["asi_hours"]):
            part = f"day={day}/hour={hour:02d}/part-000.parquet"
            groups, record = read_asi_hour(raw / f"asi_opensource_pod_hourly/{part}",
                                          raw / f"asi_opensource_server_hourly/{part}", day, hour)
            grouped.append(groups)
            quality.append({"relative_day": day, "hour": hour, **record})
    groups = pd.concat(grouped, ignore_index=True)
    groups.to_csv(output / "asi-hourly-type-priority.csv", index=False)
    gpu = groups.groupby(["relative_day", "hour"]).agg(
        requested_gpu_equivalents=("requested_gpu_equivalents", "sum"),
        used_gpu_hours=("used_gpu_hours", "sum"), inventory_gpu_count=("inventory_gpu_count", "first")).reset_index()
    gpu["requested_fraction"] = gpu.requested_gpu_equivalents / gpu.inventory_gpu_count
    gpu["used_gpu_hour_fraction"] = gpu.used_gpu_hours / gpu.inventory_gpu_count
    gpu.to_csv(output / "asi-hourly-resource-demand.csv", index=False)
    quality_frame = pd.DataFrame(quality)
    quality_frame.to_csv(output / "asi-quality-by-hour.csv", index=False)
    summary = {"source": "AcmeTrace Kalos 原始 CSV 与 Alibaba GPU 2026 小时分片",
               "acme": {"rows": len(tasks), "first_submit_utc": str(tasks.submit_time.min()),
                        "last_end_utc": str(tasks.end_time.max()), "granularity": native_granularity(tasks),
                        "reported_duration_matches_execution_interval": int(tasks.duration.eq(tasks.runtime_s).sum()),
                        "reported_duration_matches_turnaround": int(tasks.duration.eq(tasks.turnaround_s).sum()),
                        "resource_integrals": checks},
               "asi": {"native_grain_seconds": 3600, "available_days": 185, "available_hours": 4440,
                       "sample_hours": len(gpu), "quality_totals": quality_frame.drop(columns=["relative_day", "hour"]).sum().astype(int).to_dict(),
                       "by_type": groups.groupby("job_type_public")[["pod_observations", "used_gpu_hours"]].sum().to_dict("index"),
                       "request_fraction_range": [float(gpu.requested_fraction.min()), float(gpu.requested_fraction.max())]},
               "flexibility": {"published_deadline_rows": 0, "published_preemption_permission_rows": 0,
                               "classification": "所有业务期限与抢占权限保留未知；类型与优先级用于候选筛选",
                               "low_priority": "LP 保留来源的低优先级/spot 含义，不转换成允许延迟小时数"},
               "validation": {"resource_hour_conservation": "passed", "five_minute_to_hourly": "passed"}}
    if weather_path is not None:
        if len(gpu) < 2 or not np.array_equal(np.diff(gpu.relative_day * 24 + gpu.hour), np.ones(len(gpu) - 1)):
            raise ValueError("功率接口验证须选择至少两个连续的 ASI 小时")
        weather = pd.read_parquet(weather_path, columns=["grid_id", "time_utc", "temperature_c",
                                                       "dew_point_c", "relative_humidity_pct"]).iloc[:len(gpu)].copy()
        cpu = demand.loc[demand.hardware.eq("cpu")].copy()
        cpu["date"] = cpu.time_utc.dt.floor("D")
        peak_day = cpu.groupby("date").resource_hours.sum().idxmax()
        selected = cpu.loc[cpu.time_utc.ge(peak_day)].iloc[:len(gpu)]
        if len(selected) != len(gpu):
            raise ValueError("CPU 源窗口不足以匹配功率接口验证小时数")
        profiles = {
            "cpu": resource_profile(selected.mean_allocated_units, checks["cpu"]["maximum_concurrent_allocated_units"], "cpu",
                                    "Acme CPU 独立作业运行区间的实际分配核心小时",
                                    "全部有效 CPU 作业的观测并发峰值作为规模参考，非源设施安装容量"),
            "gpu": resource_profile(gpu.used_gpu_hours, gpu.inventory_gpu_count, "gpu",
                                    "ASI 小时归属 GPU 小时除以同小时服务器库存",
                                    "同小时 GPU 库存；异构 GPU 数量，未建立与 H100 的吞吐等价")}
        model = ComputeLoadModel()
        powers = []
        for hardware, profile in profiles.items():
            for size in SIZES_MW:
                curve = model.calculate(weather, profile, size, full_year=False)
                np.testing.assert_allclose(curve.facility_mw, curve.it_mw + curve.cooling_mw + curve.other_mw)
                np.testing.assert_allclose(curve.heat_demand_mw_th, curve.it_mw)
                folder = output / "power-interface" / hardware
                folder.mkdir(parents=True, exist_ok=True)
                curve.to_parquet(folder / f"{size}MW.parquet", index=False)
                powers.append({"hardware": hardware, "reference_it_mw": size,
                               "hours": len(curve), "facility_mwh": float(curve.facility_mw.sum())})
        summary["power_interface"] = {"cases": powers, "weather_sha256": sha256(weather_path),
                                      "cpu_source_window_start_utc": str(selected.time_utc.iloc[0]),
                                      "cpu_reference_cores": checks["cpu"]["maximum_concurrent_allocated_units"],
                                      "gpu_source_relative_start_hour": int(gpu.relative_day.iloc[0] * 24 + gpu.hour.iloc[0]),
                                      "scope": "固定资源路径的功率接口验证；跨数据集功率代理；资源相对小时映射到所选真实天气，非原设施实测功率",
                                      "flexible_scheduling": "未赋予缺失的业务权限"}
    summary["inputs_sha256"] = {"trace_kalos.csv": sha256(raw / "trace_kalos.csv"),
                                "download-manifest.json": sha256(raw / "download-manifest.json")}
    summary["analysis_code_sha256"] = {name: sha256(Path(__file__).with_name(name)) for name in
                                       ("audit_task_trace_sources.py", "task_trace_inputs.py")}
    summary["software"] = {"numpy": np.__version__, "pandas": pd.__version__}
    summary["outputs_sha256"] = {path.relative_to(output).as_posix(): sha256(path) for path in sorted(output.rglob("*"))
                                 if path.is_file() and path.name != "validation.json"}
    (output / "validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="核对任务记录时间粒度、业务约束和资源小时，验证负荷接口")
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--weather-parquet", type=Path)
    args = parser.parse_args()
    result = audit(args.raw_dir, args.output_dir, args.weather_parquet)
    print(json.dumps({"acme_rows": result["acme"]["rows"], "asi_sample_hours": result["asi"]["sample_hours"],
                      "validation": result["validation"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
