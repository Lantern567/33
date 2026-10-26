import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def attach_supply(curve, supply):
    load = curve.copy()
    load["time_utc"] = pd.to_datetime(load.time_utc, utc=True)
    columns = ["time_utc", "pv_capacity_factor", "wind_capacity_factor"]
    selected = supply[columns].copy()
    selected["time_utc"] = pd.to_datetime(selected.time_utc, utc=True)
    if load.time_utc.duplicated().any() or selected.time_utc.duplicated().any():
        raise ValueError("负荷或风光数据存在重复小时")
    if not pd.DatetimeIndex(load.time_utc).sort_values().equals(pd.DatetimeIndex(selected.time_utc).sort_values()):
        raise ValueError("负荷与风光数据必须覆盖完全相同的 UTC 小时")
    if any(column in load for column in columns[1:]):
        raise ValueError("负荷文件已包含风光容量因子，请明确选择输入版本")
    result = load.merge(selected, on="time_utc", how="left", validate="one_to_one", sort=False)
    for column in columns[1:]:
        values = result[column].to_numpy(float)
        if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
            raise ValueError(f"{column}必须位于0至1且没有缺失")
    result.attrs = dict(curve.attrs)
    return result


def main():
    parser = argparse.ArgumentParser(description="按 UTC 小时把新负荷与现有风光容量因子连接")
    parser.add_argument("--load-curve", required=True, type=Path)
    parser.add_argument("--supply-hourly", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = attach_supply(pd.read_parquet(args.load_curve), pd.read_parquet(args.supply_hourly))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(args.output, index=False)
    print(f"已连接 {len(result)} 个 UTC 小时")


if __name__ == "__main__":
    main()
