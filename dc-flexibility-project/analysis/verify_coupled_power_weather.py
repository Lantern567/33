import hashlib
import importlib.metadata
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import fitz
import numpy as np
import pandas as pd

from couple_compute_power_weather import COMPONENTS, PRIOR, fit, predict


PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "results/compute-center-data-audit-20261022/coupled-power-weather-20261025-v4"
PDF = OUT / "CPU_GPU算力中心_IT散热与温湿度耦合负荷报告_20261025_v4.pdf"
OLD = PROJECT / "results/compute-center-data-audit-20261022/equipment-scale-profiles-20261024/算力中心分类_小时至全年负荷与线性成本外推报告_20261024.pdf"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    manifest = json.loads((OUT / "coupled-model-manifest.json").read_text(encoding="utf-8"))
    model = manifest["cooling"]
    for source in manifest["inputs"]:
        assert sha256(source["path"]) == source["sha256"], source["source"]
    cpu = pd.read_csv(OUT / "cpu-measured-power-anchors.csv")
    gpu = pd.read_csv(OUT / "gpu-measured-power-anchors.csv")
    np.testing.assert_array_equal(cpu.node_power_w, [120, 200, 232, 260, 287, 336, 391, 430, 470, 510, 546])
    np.testing.assert_array_equal(gpu.node_power_w, [1860, 4680, 6260, 7920, 7970, 8430])
    assert np.asarray(model["coefficients"]).shape == (8, 4)
    assert np.asarray(model["coefficients"]).min() >= 0
    hardware = pd.read_csv(OUT / "hardware-scale-parameters.csv")
    assert hardware.node_price.isna().all()
    assert len(hardware) == 12
    for row in hardware.itertuples():
        assert row.node_count == int(np.floor(row.reference_it_capacity_mw*1e6/row.node_full_reference_w))
        assert np.isclose(row.installed_reference_it_mw, row.node_count*row.node_full_reference_w/1e6)
        assert row.installed_reference_it_mw <= row.reference_it_capacity_mw
        assert np.isclose(row.installed_reference_it_mw+row.unallocated_reference_mw, row.reference_it_capacity_mw)

    resource_fractions = {}
    mapped_hours = 0
    for profile in ["cpu_fast", "cpu_rnd", "gpu"]:
        observed = pd.read_parquet(PRIOR / f"{profile}-observed-qualified-hours.parquet")
        field = "gpu_request_per_inventory_unit" if profile == "gpu" else "cpu_use_fraction"
        for year in [2023, 2024, 2025]:
            provenance = pd.read_parquet(OUT / f"{profile}-{year}-resource-hour-provenance.parquet")
            expected = 8784 if year == 2024 else 8760
            assert len(provenance) == expected
            np.testing.assert_array_equal(provenance.hour_of_scenario_year, np.arange(1, expected+1))
            assert provenance.calendar_year.eq(year).all()
            values = observed.loc[pd.to_datetime(provenance.source_time_index), field].to_numpy()
            resource_fractions[profile, year] = values
            assert np.isfinite(values).all() and ((values >= 0) & (values <= 1)).all()
            for number, block in provenance.groupby("block"):
                expected_block_hours = (48 if year == 2024 else 24) if number == 53 else 168
                assert len(block) == expected_block_hours
                assert pd.to_datetime(block.source_time_index).diff().iloc[1:].eq(pd.Timedelta(hours=1)).all()
            mapped_hours += len(provenance)

    weather = pd.read_parquet(OUT / "five-location-hourly-weather-2023-2025.parquet")
    annual = pd.read_csv(OUT / "annual-load-summary.csv")
    monthly = pd.read_csv(OUT / "monthly-load-summary.csv")
    assert len(annual) == 180 and len(monthly) == 2160
    keys = ["profile", "site_id", "year", "reference_it_capacity_mw"]
    assert not annual.duplicated(keys).any()
    assert not monthly.duplicated(keys+["month"]).any()
    files = list((OUT / "hourly").glob("*/*/*/*.parquet"))
    assert len(files) == 180
    checked_hours = 0
    consistency = {}
    for path in sorted(files):
        profile, site, year = path.parts[-4], path.parts[-3], int(path.parts[-2])
        k = int(path.stem.removesuffix("MW"))
        frame = pd.read_parquet(path)
        expected = 8784 if year == 2024 else 8760
        assert len(frame) == expected and frame.notna().all().all()
        assert frame.time_utc.is_unique and str(frame.time_utc.dt.tz) == "UTC"
        expected_times = pd.date_range(f"{year}-01-01", periods=expected, freq="1h", tz="UTC")
        np.testing.assert_array_equal(frame.time_utc.to_numpy(), expected_times.to_numpy())
        assert frame.profile.eq(profile).all() and frame.logical_site_id.eq(site).all()
        assert frame.reference_it_capacity_mw.eq(k).all()
        hw = hardware.loc[hardware.profile.eq(profile) & hardware.reference_it_capacity_mw.eq(k)].iloc[0]
        assert frame.node_count.eq(hw.node_count).all() and frame.gpu_count.eq(hw.gpu_count).all()
        u = resource_fractions[profile, year]
        np.testing.assert_array_equal(frame.resource_fraction.to_numpy(), u)
        anchors = gpu.loc[~gpu.measurement.str.contains("no CPU", regex=False)].sort_values("load_fraction") if profile == "gpu" else cpu
        expected_it = np.interp(u, anchors.load_fraction, anchors.node_power_w)*hw.node_count/1e6
        np.testing.assert_allclose(frame.it_mw, expected_it, atol=1e-12)
        assert frame.it_mw.le(hw.installed_reference_it_mw+1e-9).all()
        np.testing.assert_array_equal(frame.heat_demand_mw_th, frame.it_mw)
        np.testing.assert_allclose(frame.cooling_mw, frame[COMPONENTS[:3]].sum(axis=1), atol=1e-10)
        np.testing.assert_allclose(frame.facility_mw, frame.it_mw+frame.cooling_mw+frame.other_mw, atol=1e-10)
        np.testing.assert_allclose(frame.pue, frame.facility_mw/frame.it_mw)
        assert frame.pue.ge(1).all()
        assert frame[COMPONENTS+["it_mw"]].ge(0).all().all()
        np.testing.assert_allclose(frame[COMPONENTS], predict(frame, model, hw.installed_reference_it_mw), atol=1e-10)
        target_weather = weather.loc[weather.logical_site_id.eq(site) & weather.calendar_year.eq(year)].sort_values("time_utc")
        np.testing.assert_array_equal(frame[["temperature_c", "relative_humidity_pct", "dew_point_c"]].to_numpy(),
                                      target_weather[["temperature_c", "relative_humidity_pct", "dew_point_c"]].to_numpy())
        inside = np.ones(len(frame), dtype=bool)
        for field in ["temperature_c", "dew_point_c"]:
            low, high = model["calibration_range"][field]
            inside &= frame[field].between(low, high).to_numpy()
        np.testing.assert_array_equal(frame.outside_calibration_weather, ~inside)
        qlo, qhi = model["calibration_range"]["it_fraction"]
        np.testing.assert_array_equal(frame.outside_calibration_it_range, ~frame.it_fraction_of_reference.between(qlo, qhi))
        for component in ["it", "cooling", "other", "facility"]:
            np.testing.assert_allclose(frame[f"cumulative_{component}_mwh"], frame[f"{component}_mw"].cumsum())
        field, cumulative = ("allocated_gpu_equivalents", "cumulative_allocated_gpu_hours") if profile == "gpu" else ("cpu_core_usage_proxy", "cumulative_cpu_core_proxy_hours")
        np.testing.assert_allclose(frame[cumulative], frame[field].cumsum())
        row = annual.loc[annual.profile.eq(profile) & annual.site_id.eq(site) & annual.year.eq(year) & annual.reference_it_capacity_mw.eq(k)].iloc[0]
        assert np.isclose(row.annual_resource_proxy_hours, frame[field].sum())
        assert row.hours == expected and row.outside_calibration_weather_hours == (~inside).sum()
        assert row.outside_calibration_it_hours == frame.outside_calibration_it_range.sum()
        assert np.isclose(row.max_facility_mw, frame.facility_mw.max())
        for component in ["it", "cooling", "other", "facility"]:
            assert np.isclose(row[f"annual_{component}_mwh"], frame[f"{component}_mw"].sum())
        months = monthly.loc[monthly.profile.eq(profile) & monthly.site_id.eq(site) & monthly.year.eq(year) & monthly.reference_it_capacity_mw.eq(k)]
        assert len(months) == 12 and months.hours.sum() == expected
        for component in ["it", "cooling", "other", "facility"]:
            assert np.isclose(months[f"{component}_mwh"].sum(), row[f"annual_{component}_mwh"])
        signature = profile, year
        ratios = frame[["it_mw", "cooling_mw", "other_mw"]].to_numpy()/hw.installed_reference_it_mw
        if (profile, site, year) in consistency:
            np.testing.assert_allclose(ratios, consistency[profile, site, year], atol=1e-12)
        else:
            consistency[profile, site, year] = ratios
        if signature in consistency:
            np.testing.assert_allclose(frame.it_mw.to_numpy()/hw.node_count, consistency[signature], rtol=1e-13, atol=1e-15)
        else:
            consistency[signature] = frame.it_mw.to_numpy()/hw.node_count
        if year == 2024:
            assert frame.loc[frame.time_utc.dt.month.eq(2)].shape[0] == 696
            assert frame.loc[frame.time_utc.dt.month.eq(2) & frame.time_utc.dt.day.eq(29)].shape[0] == 24
        csv = path.with_suffix(".csv")
        if csv.exists():
            text = pd.read_csv(csv)
            np.testing.assert_allclose(text.facility_mw, frame.facility_mw, rtol=1e-12)
        checked_hours += len(frame)

    paired = pd.read_parquet(OUT / "esif-paired-power-weather-calibration-hours.parquet")
    holdout = pd.read_csv(OUT / "cooling-chronological-holdout-predictions.csv", index_col=0, parse_dates=True)
    cutoff = pd.Timestamp(model["holdout_start_source_clock"])
    train = paired.loc[paired.index < cutoff]
    test = paired.loc[paired.index >= cutoff]
    assert len(train) == 4775 and len(test) == 672
    assert train.index.max() < test.index.min()
    fixed_model = fit(train, model["reference_mw"])
    recomputed = predict(test, fixed_model, model["reference_mw"])[:, :3].sum(axis=1)
    np.testing.assert_allclose(recomputed, holdout.heat_temperature_humidity_cooling_mw, atol=1e-12)
    residual = recomputed-test[COMPONENTS[:3]].sum(axis=1).to_numpy()
    assert np.isclose(np.sqrt(np.mean(residual**2))*1000, model["chronological_validation"][1]["rmse_kw"])

    with fitz.open(PDF) as report, fitz.open(OLD) as original:
        assert len(report) == 12
        assert report[1].get_text() == original[1].get_text()
        assert report[1].get_pixmap().samples == original[1].get_pixmap().samples
        for i, page in enumerate(report, 1):
            assert page.get_text().strip()
            for block in page.get_text("blocks"):
                assert block[0] >= 20 and block[2] <= page.rect.width-20, (i, block)
                assert block[1] >= 15 and block[3] <= page.rect.height-15, (i, block)

    result = {"status": "passed", "version": manifest["version"], "hourly_cases": len(files),
              "main_cases": 120, "cpu_sample_sensitivity_cases": 60, "checked_hourly_rows": checked_hours,
              "checked_resource_source_hours": mapped_hours, "monthly_rows": len(monthly), "pdf_pages": 12,
              "chapter1_text_and_pixels_identical": True, "pdf_visual_review": "全部12页与7张源图已检查，修改公式和坐标轴的页面已复查",
              "checks": ["输入哈希一致", "原始资源小时逐值溯源", "节点数量按整机取整", "实测功率点与插值映射",
                         "IT与散热近似关系", "电功率分项守恒与PUE", "累计资源和电量", "月度与年度求和",
                         "天气与小时索引配对", "同IT路径的地点对照", "安装容量归一化的尺度一致性", "闰年8784小时",
                         "留出集独立于拟合期", "外推范围标记", "价格空值"],
              "scientific_scope": manifest["validation_scope"], "pdf_sha256": sha256(PDF),
              "software_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scipy", "PsychroLib", "reportlab", "PyMuPDF"]}}
    (OUT / "verification-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {"version": manifest["version"], "report": str(PDF.relative_to(PROJECT)), "input_versions": manifest["inputs"],
                "scope": "CPU/GPU、四档参考满载IT规模、五地点天气、2023—2025逐小时负荷",
                "completed": result["checks"], "cases": 180, "validation_scope": manifest["validation_scope"],
                "assumptions": manifest["assumptions"], "unidentified_parameters": manifest["not_identified"],
                "prior_report_retained": "observed-trace-extrapolation-20261024-v3",
                "calibration_rmse_kw": model["chronological_validation"][1]["rmse_kw"]}
    metadata_path = PROJECT / "data/metadata/coupled-power-weather-20261025-v4.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    archive_path = OUT.parent / "CPU_GPU温湿度耦合_小时负荷与计算文件_20261025_v4.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=f"outputs/{path.relative_to(OUT).as_posix()}")
        for name in ["couple_compute_power_weather.py", "plot_coupled_power_weather.py", "build_coupled_power_weather_report.py", "verify_coupled_power_weather.py"]:
            archive.write(PROJECT / "analysis" / name, arcname=f"analysis/{name}")
        for profile in ["cpu_fast", "cpu_rnd", "gpu"]:
            for suffix in ["observed-qualified-hours.parquet", "replayed-8760-hours.parquet"]:
                name = f"{profile}-{suffix}"
                archive.write(PRIOR / name, arcname=f"resource-inputs/{name}")
        archive.write(metadata_path, arcname="metadata/coupled-power-weather-20261025-v4.json")
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        count = len(archive.namelist())
    print(json.dumps({"verification": result, "archive": str(archive_path), "files": count,
                      "archive_size_mb": archive_path.stat().st_size/1e6}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
