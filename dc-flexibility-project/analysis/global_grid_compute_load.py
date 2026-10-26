import argparse
import json
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

from compute_load import ComputeLoadModel, ProfileLibrary
from compute_load.model import SIZES_MW, sha256
from compute_load.runner import run_frame


def grid_weather(dataset, mapping_row, years):
    native = int(mapping_row.native_flat_index)
    table = dataset.to_table(columns=["time", "2m_temperature", "2m_dewpoint_temperature"],
                             filter=ds.field("native_flat_index") == native).to_pandas()
    if table.empty:
        raise FileNotFoundError(f"网格 {mapping_row.grid_id} 的中心天气节点 {native} 尚未到齐")
    table["time_utc"] = pd.to_datetime(table.time, utc=True)
    if table.time_utc.isna().any():
        raise ValueError(f"网格 {mapping_row.grid_id} 的天气时间存在缺失值")
    if not set(years).issubset(set(table.time_utc.dt.year)):
        raise ValueError(f"网格 {mapping_row.grid_id} 缺少请求年份")
    table = table.loc[table.time_utc.dt.year.isin(years)].sort_values("time_utc").reset_index(drop=True)
    result = pd.DataFrame({"grid_id": str(mapping_row.grid_id), "time_utc": table.time_utc,
                           "temperature_c": table["2m_temperature"].to_numpy(dtype=float) - 273.15,
                           "dew_point_c": table["2m_dewpoint_temperature"].to_numpy(dtype=float) - 273.15})
    return result


def main():
    parser = argparse.ArgumentParser(description="把现有全球网格 ERA5 原生节点接入通用算力负荷模块")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--weather-path", type=Path)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--profiles-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--grid-ids", nargs="+")
    selection.add_argument("--all-grids", action="store_true")
    parser.add_argument("--years", type=int, nargs="+", default=[2023, 2024, 2025])
    parser.add_argument("--sizes-mw", type=int, nargs="+", default=list(SIZES_MW))
    parser.add_argument("--extrapolation", choices=("flag", "error"), default="flag")
    args = parser.parse_args()
    root = args.root.resolve()
    weather_path = args.weather_path or root / "data/processed/era5-eligible-2023-2025"
    mapping_path = args.mapping or root / "data/processed/era5-landuse-selection/grid-weather-mapping.parquet"
    profiles = args.profiles_dir or root / "inputs/compute-load-profiles-20261025"
    output = args.output_dir or root / "results/compute-load-20261025-v1"
    mapping = pd.read_parquet(mapping_path)
    center = mapping.loc[mapping.row_offset.eq(1) & mapping.col_offset.eq(1)].copy()
    if center.grid_id.duplicated().any():
        raise ValueError("一个研究网格存在多个中心天气节点")
    if args.grid_ids:
        if not set(args.grid_ids).issubset(set(center.grid_id)):
            raise ValueError("请求网格未登记唯一中心天气节点")
        center = center.loc[center.grid_id.isin(args.grid_ids)]
    if center.empty:
        raise ValueError("未选择任何研究网格")
    if weather_path.is_dir():
        completed = sorted(str(path) for path in weather_path.rglob("*.parquet"))
        if not completed:
            raise FileNotFoundError(f"尚无完整 Parquet 天气文件：{weather_path}")
        dataset = ds.dataset(completed, format="parquet", exclude_invalid_files=False)
    else:
        dataset = ds.dataset(weather_path, format="parquet", exclude_invalid_files=False)
    library, model = ProfileLibrary(profiles), ComputeLoadModel()
    source = {"dataset": str(weather_path.resolve()), "mapping_sha256": sha256(mapping_path),
              "weather_selection": "0.5度研究网格的中心原生0.25度节点，row_offset=1、col_offset=1",
              "time_interpretation": "UTC记录时刻的干球与露点作为该小时代表天气；近饱和0.01℃内超差保留原值及修正标记，其余不填补",
              "adapter_sha256": sha256(Path(__file__))}
    count = 0
    for row in center.sort_values("grid_id").itertuples(index=False):
        weather = grid_weather(dataset, row, args.years)
        result = run_frame(weather, library, output, model=model, sizes=args.sizes_mw,
                           extrapolation=args.extrapolation,
                           source={**source, "native_flat_index": int(row.native_flat_index)})
        count += len(result)
        print(json.dumps({"grid_id": row.grid_id, "cases": len(result), "total_cases": count}, ensure_ascii=False), flush=True)
    print(json.dumps({"status": "complete", "grids": len(center), "cases": count}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
