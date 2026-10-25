import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from compute_load.model import sha256


def build_library(reference, destination, site="c3ba734448beea13"):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    profiles = {}
    for hardware, source_trace in (("cpu", "cpu_fast"), ("gpu", "gpu")):
        for year, hours in ((2025, 8760), (2024, 8784)):
            source = Path(reference) / f"hourly/{source_trace}/{site}/{year}/1MW.parquet"
            original = pd.read_parquet(source, columns=["resource_fraction"])
            if len(original) != hours:
                raise ValueError(f"来源资源曲线小时数不符：{source}")
            filename = f"{hardware}-{hours}.parquet"
            output = destination / filename
            table = pd.DataFrame({"hour_of_year": np.arange(hours), "resource_fraction": original.resource_fraction})
            table.to_parquet(output, index=False)
            pd.testing.assert_frame_equal(table, pd.read_parquet(output))
            profiles[f"{hardware}-{hours}"] = {
                "file": filename, "sha256": sha256(output), "hours": hours,
                "source": "已核验 20261025-v4 负荷工作包中的原值资源路径",
                "source_trace": source_trace, "source_year": year,
                "source_file": str(source.relative_to(reference)), "source_file_sha256": sha256(source),
            }
    manifest = {"version": "observed-resource-profiles-20261025-v1", "profiles": profiles,
                "interpretation": "CPU 使用率与 GPU 申请份额；保留原曲线，不调整平均忙碌比例，不按天气改变资源到达",
                "distribution": "本地或私有研究环境使用，按 Bitbrains 和 Alibaba 来源许可管理"}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = build_library(args.reference_dir, args.output_dir)
    print(json.dumps({"status": "passed", "profiles": len(result["profiles"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
