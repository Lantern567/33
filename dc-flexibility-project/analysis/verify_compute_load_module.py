import argparse
import copy
import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from compute_load import ComputeLoadModel, ProfileLibrary, ResourceProfile
from compute_load.runner import run_frame
from global_grid_flex_solver import solve_four_scenarios
from prepare_compute_solver_input import attach_supply


def verify(reference, profiles, fixtures, output):
    model, library = ComputeLoadModel(), ProfileLibrary(profiles)
    observed = pd.read_parquet(reference / "five-location-hourly-weather-2023-2025.parquet")
    maximum, cases, checked_rows = 0.0, 0, 0
    columns = ["it_mw", "heat_demand_mw_th", "outdoor_cooling_mw", "hvac_mw", "pump_mw", "other_mw",
               "cooling_mw", "facility_mw", "pue", "cumulative_it_mwh", "cumulative_cooling_mwh",
               "cumulative_other_mwh", "cumulative_facility_mwh"]
    for (site, year), weather in observed.groupby(["logical_site_id", "calendar_year"], sort=True):
        weather = weather.sort_values("time_utc").reset_index(drop=True)
        weather["grid_id"] = str(site)
        for hardware, original_profile in (("cpu", "cpu_fast"), ("gpu", "gpu")):
            for size in (1, 10, 100, 500):
                curve = model.calculate(weather, library.for_year(hardware, int(year)), size)
                original = pd.read_parquet(reference / f"hourly/{original_profile}/{site}/{year}/{size}MW.parquet")
                np.testing.assert_allclose(curve[columns], original[columns], atol=1e-9, rtol=1e-12)
                np.testing.assert_array_equal(curve.resource_fraction, original.resource_fraction)
                np.testing.assert_array_equal(curve.outside_calibration_weather, original.outside_calibration_weather)
                np.testing.assert_array_equal(curve.outside_calibration_it_range, original.outside_calibration_it_range)
                maximum = max(maximum, float(np.abs(curve[columns].to_numpy() - original[columns].to_numpy()).max()))
                checked_rows += len(curve)
                cases += 1
    test = unittest.TestCase()
    weather = observed.loc[observed.logical_site_id.eq("c3ba734448beea13") & observed.calendar_year.eq(2025)].copy()
    weather = weather.sort_values("time_utc").reset_index(drop=True)
    weather["grid_id"] = "c3ba734448beea13"
    profile = library.for_year("gpu", 2025)
    baseline = model.calculate(weather, profile, 1)
    dew_only = model.calculate(weather.drop(columns="relative_humidity_pct"), profile, 1)
    np.testing.assert_allclose(baseline.facility_mw, dew_only.facility_mw, atol=1e-9, rtol=0)
    test.assertEqual(int(baseline.gpu_count.iloc[0]), 944)
    invalid_checks = 0
    for broken in (weather.drop(index=100), pd.concat([weather, weather.iloc[[1]]], ignore_index=True)):
        with test.assertRaises(ValueError):
            model.calculate(broken, profile, 1)
        invalid_checks += 1
    for column, value in (("temperature_c", np.nan), ("temperature_c", 290.0), ("relative_humidity_pct", 101.0), ("relative_humidity_pct", 0.0)):
        broken = weather.copy()
        broken.loc[0, column] = value
        with test.assertRaises(ValueError):
            model.calculate(broken, profile, 1)
        invalid_checks += 1
    with test.assertRaises(ValueError):
        model.calculate(weather, ResourceProfile("gpu", profile.fraction[:-1], {"source": "故意缺失一个资源小时"}), 1)
    with test.assertRaises(ValueError):
        model.calculate(weather, profile, 5)
    broken = weather.copy()
    broken.loc[0, "dew_point_c"] = broken.loc[0, "temperature_c"] + 1
    with test.assertRaises(ValueError):
        model.calculate(broken, profile, 1)
    with test.assertRaises(ValueError):
        model.calculate(weather, profile, 1, extrapolation="error")
    invalid_checks += 4
    batch = weather.drop(columns="dew_point_c")
    summaries = run_frame(batch, library, output / "batch")
    repeated = run_frame(batch, library, output / "batch")
    test.assertEqual(summaries, repeated)
    changed = batch.copy()
    changed.loc[0, "temperature_c"] += 0.1
    with test.assertRaisesRegex(ValueError, "输入或模型版本不同"):
        run_frame(changed, library, output / "batch")
    invalid_checks += 1
    real = pd.read_parquet(fixtures / "era5_g1274.parquet")
    real["time_utc"] = pd.to_datetime(real.time, utc=True)
    real = real.loc[real.time_utc.dt.year.eq(2023)].copy()
    real = real.rename(columns={"temperature_2m": "temperature_c", "relative_humidity_2m": "relative_humidity_pct"})
    real["grid_id"] = "era5_g1274"
    curve = model.calculate(real[["grid_id", "time_utc", "temperature_c", "relative_humidity_pct"]], library.for_year("gpu", 2023), 1)
    supply = pd.read_parquet(fixtures / "supply-168h.parquet")
    joined = attach_supply(curve.iloc[:len(supply)].copy(), supply)
    np.testing.assert_array_equal(joined.facility_mw, curve.facility_mw.iloc[:len(supply)])
    config = json.loads((fixtures / "validation-config.json").read_text(encoding="utf-8"))
    config["load_model"] = "weather_coupled_fixed_v1"
    solved = solve_four_scenarios(joined, config)
    test.assertEqual(set(solved["scenarios"]), {"C0", "CS"})
    statuses = {}
    for name, result in solved["scenarios"].items():
        statuses[name] = result["summary"]["status"]
        test.assertNotEqual(statuses[name], "not_solved")
        if result["summary"]["feasible"]:
            np.testing.assert_array_equal(result["hourly"].facility_power_mw, joined.facility_mw)
            test.assertLess(float(result["hourly"].power_balance_residual_mw.abs().max()), 2e-6)
            result["hourly"].to_parquet(output / f"{name}-integrated-real-168h.parquet", index=False)
    test.assertEqual(statuses["CS"], "optimal")
    with test.assertRaisesRegex(ValueError, "仅支持 C0/CS"):
        solve_four_scenarios(joined, config, ["CSD"])
    with test.assertRaises(ValueError):
        attach_supply(curve.iloc[:len(supply)].copy(), supply.iloc[:-1])
    bad_scale = copy.deepcopy(config)
    bad_scale["reference_it_mw"] = 10
    with test.assertRaises(ValueError):
        solve_four_scenarios(joined, bad_scale)
    invalid_checks += 3
    joined.to_parquet(output / "integrated-solver-input-real-168h.parquet", index=False)
    (output / "integrated-config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {"status": "passed", "regression_cases": cases, "regression_hourly_rows": checked_rows,
              "maximum_absolute_regression_error": maximum, "real_weather_source": "既有ERA5五地点与全球求解器ERA5实测天气输入",
              "batch_cases": len(summaries), "idempotent_resume": True, "invalid_input_checks": invalid_checks,
              "fixed_load_solver_real_168h": statuses, "flexible_schedule_misuse_rejected": True,
              "cost_scope": "168h求解仅验证接口与守恒；沿用既有明确标记的技术价格情景，不作为全年经济结论",
              "model": model.metadata}
    (output / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-dir", required=True, type=Path)
    parser.add_argument("--profiles-dir", required=True, type=Path)
    parser.add_argument("--fixtures-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps(verify(args.reference_dir, args.profiles_dir, args.fixtures_dir, args.output_dir), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
