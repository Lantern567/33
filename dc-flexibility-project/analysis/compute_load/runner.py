import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd

from .model import ComputeLoadModel, ProfileLibrary, SIZES_MW, annual_summary, normalize_weather, sha256


def weather_fingerprint(weather):
    digest = hashlib.sha256()
    digest.update(pd.DatetimeIndex(weather.time_utc).asi8.astype("<i8").tobytes())
    for column in ("temperature_c", "relative_humidity_pct", "dew_point_c", "input_dew_point_c"):
        digest.update(column.encode())
        digest.update(weather[column].to_numpy(dtype="<f8").tobytes())
    return digest.hexdigest()


def run_frame(weather, library, output, *, model=None, sizes=SIZES_MW,
              hardware_types=("cpu", "gpu"), extrapolation="flag", source=None):
    model = ComputeLoadModel() if model is None else model
    if not sizes or len(set(sizes)) != len(sizes) or any(size not in SIZES_MW for size in sizes):
        raise ValueError("sizes 必须为 1、10、100、500 的非空无重复子集")
    if not hardware_types or len(set(hardware_types)) != len(hardware_types) or any(kind not in ("cpu", "gpu") for kind in hardware_types):
        raise ValueError("hardware_types 必须为 cpu、gpu 的非空无重复子集")
    if weather.empty or "grid_id" not in weather or weather.grid_id.isna().any():
        raise ValueError("批处理天气必须包含非空 grid_id 和有效记录")
    weather = weather.copy()
    weather["grid_id"] = weather.grid_id.astype(str)
    weather["time_utc"] = pd.to_datetime(weather.time_utc, utc=True)
    if weather.time_utc.isna().any():
        raise ValueError("天气时间列存在缺失值")
    weather["calendar_year"] = weather.time_utc.dt.year
    summaries = []
    for (grid, year), selected in weather.groupby(["grid_id", "calendar_year"], sort=True):
        frame = normalize_weather(selected.sort_values("time_utc").reset_index(drop=True))
        profiles = {kind: library.for_year(kind, int(year)) for kind in hardware_types}
        request = {"grid_id": grid, "year": int(year), "sizes_mw": list(sizes),
                   "hardware_types": list(hardware_types), "model": model.metadata,
                   "runner_sha256": sha256(Path(__file__)), "source": source,
                   "weather_values_sha256": weather_fingerprint(frame),
                   "profiles": {kind: item.provenance for kind, item in profiles.items()},
                   "extrapolation_policy": extrapolation}
        directory = Path(output) / ("grid_id=" + quote(grid, safe="")) / str(year)
        manifest = directory / "manifest.json"
        if manifest.exists():
            previous = json.loads(manifest.read_text(encoding="utf-8"))
            if previous["request"] != request:
                raise ValueError(f"已有结果的输入或模型版本不同，请使用独立输出目录：{manifest}")
            for record in previous["cases"]:
                if sha256(directory / record["file"]) != record["sha256"]:
                    raise ValueError(f"已有结果校验失败：{record['file']}")
                summaries.append(record["summary"])
            for name, expected in previous["summary_files"].items():
                if sha256(directory / name) != expected:
                    raise ValueError(f"已有汇总校验失败：{name}")
            continue
        directory.mkdir(parents=True, exist_ok=True)
        records, monthly = [], []
        for kind in hardware_types:
            for size in sizes:
                curve = model.calculate(frame, profiles[kind], size, extrapolation=extrapolation)
                relative = f"{kind}/{size}MW.parquet"
                path = directory / relative
                path.parent.mkdir(exist_ok=True)
                temporary = path.with_suffix(".parquet.part")
                curve.to_parquet(temporary, index=False, compression="zstd")
                temporary.replace(path)
                summary = annual_summary(curve)
                records.append({"file": relative, "sha256": sha256(path), "summary": summary})
                summaries.append(summary)
                for month, group in curve.groupby(curve.time_utc.dt.month):
                    monthly.append({"grid_id": grid, "year": int(year), "month": int(month),
                                    "hardware": kind, "reference_it_capacity_mw": size,
                                    **{f"{part}_mwh": float(group[f"{part}_mw"].sum()) for part in ("it", "cooling", "other", "facility")}})
        pd.DataFrame([item["summary"] for item in records]).to_csv(directory / "annual-summary.csv", index=False)
        pd.DataFrame(monthly).to_csv(directory / "monthly-summary.csv", index=False)
        record = {"request": request, "cases": records,
                  "summary_files": {name: sha256(directory / name) for name in ("annual-summary.csv", "monthly-summary.csv")}}
        temporary = manifest.with_suffix(".json.part")
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(manifest)
    return summaries


def main():
    parser = argparse.ArgumentParser(description="任意网格全年逐小时 CPU/GPU IT、散热、冷却及设施负荷")
    parser.add_argument("--weather", type=Path, required=True)
    parser.add_argument("--profiles-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument("--sizes-mw", type=int, nargs="+", default=list(SIZES_MW))
    parser.add_argument("--hardware", nargs="+", choices=("cpu", "gpu"), default=["cpu", "gpu"])
    parser.add_argument("--extrapolation", choices=("flag", "error"), default="flag")
    args = parser.parse_args()
    if args.weather.suffix.lower() == ".parquet":
        frame = pd.read_parquet(args.weather)
    elif args.weather.suffix.lower() == ".csv":
        frame = pd.read_csv(args.weather, dtype={"grid_id": "string"})
    else:
        raise ValueError("天气文件必须为 CSV 或 Parquet")
    years = pd.to_datetime(frame.time_utc, utc=True).dt.year
    if years.isna().any():
        raise ValueError("天气时间列存在缺失值")
    if not set(args.years).issubset(set(years)):
        raise ValueError("天气文件未覆盖所有请求年份")
    frame = frame.loc[years.isin(args.years)].copy()
    result = run_frame(frame, ProfileLibrary(args.profiles_dir), args.output_dir,
                       sizes=args.sizes_mw, hardware_types=args.hardware, extrapolation=args.extrapolation,
                       source={"file": str(args.weather.resolve()), "sha256": sha256(args.weather)})
    print(json.dumps({"status": "complete", "cases": len(result), "hourly_rows": sum(row["hours"] for row in result)}, ensure_ascii=False))
