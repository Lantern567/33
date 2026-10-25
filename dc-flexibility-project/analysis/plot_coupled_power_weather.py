import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import psychrolib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

from couple_compute_power_weather import predict


PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "results/compute-center-data-audit-20261022/coupled-power-weather-20261025-v4"
OAK = "c3ba734448beea13"
COLORS = ["#32788E", "#BD7839", "#7B6794", "#4D8761", "#A45861"]
LABELS = {"35dd981fe96fa50c": "孟菲斯", "7a5cb7bae095e8c6": "博洛尼亚", OAK: "橡树岭", "cfa607ecb913aa41": "盖恩斯维尔", "e2e82e8e4a8b7f3d": "卡亚尼"}


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=320, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    font = Path("C:/Windows/Fonts/msyh.ttc")
    fm.fontManager.addfont(str(font))
    plt.rcParams.update({"font.family": fm.FontProperties(fname=str(font)).get_name(), "font.size": 10,
                         "axes.unicode_minus": False, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": .16, "legend.frameon": False})
    model = json.loads((OUT / "cooling-calibration.json").read_text(encoding="utf-8"))
    cpu = pd.read_csv(OUT / "cpu-measured-power-anchors.csv")
    gpu = pd.read_csv(OUT / "gpu-measured-power-anchors.csv")
    curve = gpu.loc[~gpu.measurement.str.contains("no CPU", regex=False)].sort_values("load_fraction")
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 2.8), constrained_layout=True)
    for ax, frame, label, color in [(axes[0], cpu, "CPU参考节点", COLORS[1]), (axes[1], curve, "8×H100参考节点", COLORS[0])]:
        ax.plot(frame.load_fraction*100, frame.node_power_w/1000, "o-", color=color, ms=4)
        ax.set(xlabel="基准记录中的相对负载或GPU利用率 (%)", ylabel="整机功率 (kW)", title=label)
        ax.set_ylim(bottom=0)
    save(fig, "01-measured-node-power-mapping")

    for profile, label in [("cpu_fast", "CPU"), ("gpu", "GPU")]:
        frame = pd.read_parquet(OUT / "hourly" / profile / OAK / "2025/10MW.parquet").iloc[:168]
        fig, ax = plt.subplots(figsize=(8.2, 2.6), constrained_layout=True)
        ax.stackplot(np.arange(168), frame.it_mw, frame.cooling_mw, frame.other_mw,
                     labels=["IT", "冷却相关", "其他配套"], colors=[COLORS[0] if profile == "gpu" else COLORS[1], "#79A9AF", "#B4BABE"], alpha=.85)
        ax.plot(np.arange(168), frame.facility_mw, color="#33434B", lw=.8, label="总功率")
        ax.set(xlabel="2025年相对第一周小时", ylabel="平均功率 (MW)", title=f"{label}｜10 MW参考满载IT规模｜橡树岭天气情境")
        ax.set_xlim(0, 168)
        ax.set_xticks(np.arange(0, 168, 24))
        ax.set_ylim(0, frame.facility_mw.max()*1.22)
        ax.legend(loc="upper center", ncol=4, fontsize=9)
        save(fig, f"02-{profile}-hourly-components")

    paired = pd.read_parquet(OUT / "esif-paired-power-weather-calibration-hours.parquet")
    q = float((paired.it_mw/model["reference_mw"]).median())
    dry = np.linspace(paired.temperature_c.min(), paired.temperature_c.max(), 150)
    rh = float(paired.relative_humidity_pct.median())
    reference = pd.DataFrame({"it_mw": q*10, "temperature_c": dry,
                              "dew_point_c": psychrolib.GetTDewPointFromRelHum(dry, rh/100)})
    values = predict(reference, model, 10)
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 2.9), constrained_layout=True)
    dew_lower, dew_upper = model["calibration_range"]["dew_point_c"]
    inside = reference.dew_point_c.between(dew_lower, dew_upper).to_numpy()
    axes[0].plot(dry, np.where(inside, values[:, :3].sum(axis=1), np.nan), color=COLORS[0])
    axes[0].plot(dry, np.where(~inside, values[:, :3].sum(axis=1), np.nan), color=COLORS[0], ls="--")
    axes[0].set(xlabel="室外气温 (°C)", ylabel="冷却相关功率 (MW)", title=f"固定观测中位负荷与湿度 {rh:.1f}%")
    humid = np.linspace(paired.relative_humidity_pct.min(), paired.relative_humidity_pct.max(), 150)
    temp = float(paired.temperature_c.median())
    reference = pd.DataFrame({"it_mw": q*10, "temperature_c": temp,
                              "dew_point_c": psychrolib.GetTDewPointFromRelHum(temp, humid/100)})
    values = predict(reference, model, 10)
    axes[1].plot(humid, values[:, :3].sum(axis=1), color=COLORS[3])
    axes[1].set(xlabel="室外相对湿度 (%)", ylabel="冷却相关功率 (MW)", title=f"固定观测中位负荷与气温 {temp:.1f}°C")
    for ax in axes:
        ax.set_ylim(bottom=0)
    save(fig, "03-calibrated-weather-response")

    weather = pd.read_parquet(OUT / "five-location-hourly-weather-2023-2025.parquet")
    monthly = pd.read_csv(OUT / "monthly-load-summary.csv")
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.0), constrained_layout=True)
    for color, (site, label) in zip(COLORS, LABELS.items()):
        w = weather.loc[weather.logical_site_id.eq(site) & weather.calendar_year.eq(2025)]
        t = w.groupby(w.time_utc.dt.month).temperature_c.mean()
        axes[0].plot(t.index, t, color=color, marker="o", ms=3, label=label)
        m = monthly.loc[monthly.profile.eq("gpu") & monthly.site_id.eq(site) & monthly.year.eq(2025) & monthly.reference_it_capacity_mw.eq(10)]
        axes[1].plot(m.month, m.cooling_mwh/1000, color=color, marker="o", ms=3, label=label)
    axes[0].set(xlabel="2025年月序", ylabel="平均室外气温 (°C)")
    axes[1].set(xlabel="2025年月序", ylabel="GPU情境月冷却电量 (GWh)")
    axes[0].legend(fontsize=8, ncol=2)
    for ax in axes:
        ax.set_xticks([1, 3, 5, 7, 9, 12])
    save(fig, "04-climate-and-monthly-cooling")

    holdout = pd.read_csv(OUT / "cooling-chronological-holdout-predictions.csv", index_col=0, parse_dates=True)
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.1), constrained_layout=True)
    days = (holdout.index-holdout.index.min()).total_seconds()/86400
    axes[0].plot(days, holdout.observed_cooling_mw*1000, lw=.7, color="#454D52", label="观测")
    axes[0].plot(days, holdout.heat_temperature_humidity_cooling_mw*1000, lw=.8, color=COLORS[0], label="IT＋温湿度")
    axes[0].set(xlabel="留出期相对日（2025年8月）", ylabel="冷却相关功率 (kW)")
    axes[0].legend(fontsize=8)
    axes[1].scatter(holdout.observed_cooling_mw*1000, holdout.heat_only_cooling_mw*1000, s=5, alpha=.35, color=COLORS[1], label="仅IT热负荷")
    axes[1].scatter(holdout.observed_cooling_mw*1000, holdout.heat_temperature_humidity_cooling_mw*1000, s=5, alpha=.35, color=COLORS[0], label="IT＋温湿度")
    lower, upper = holdout.observed_cooling_mw.min()*1000, holdout.observed_cooling_mw.max()*1000
    axes[1].plot([lower, upper], [lower, upper], color="#777777", ls="--", lw=.8)
    axes[1].set(xlabel="观测冷却功率 (kW)", ylabel="模型冷却功率 (kW)")
    axes[1].legend(fontsize=8)
    save(fig, "05-cooling-holdout-validation")

    fig, axes = plt.subplots(1, 2, figsize=(8.2, 2.9), constrained_layout=True)
    for ax, profile, label in [(axes[0], "cpu_fast", "CPU"), (axes[1], "gpu", "GPU")]:
        for color, (site, short) in zip(COLORS, LABELS.items()):
            frame = pd.read_parquet(OUT / "hourly" / profile / site / "2025/10MW.parquet")
            ax.plot(np.arange(1, len(frame)+1)/24, frame.cumulative_facility_mwh/1000, color=color, lw=1, label=short)
        ax.set(xlabel="2025年相对日", ylabel="累计设施电量 (GWh)", title=f"{label}｜10 MW参考规模")
    axes[1].legend(fontsize=7, loc="upper left", ncol=2)
    save(fig, "06-cumulative-energy-five-climates")
    print(json.dumps({"figures": 7, "path": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
