import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from compute_load.model import sha256
from task_trace_inputs import interval_resource_hours


def audit_lisa(jobs_zip, hardware_path, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(jobs_zip) as archive:
        members = [name for name in archive.namelist() if name.endswith(".parquet")]
        if not members:
            raise ValueError("Lisa 作业压缩包不包含 Parquet 文件")
        jobs = pd.concat([pd.read_parquet(io.BytesIO(archive.read(name))) for name in members], ignore_index=True)
    if jobs.id.isna().any() or jobs.id.duplicated().any():
        raise ValueError("Lisa 作业标识必须唯一且非空")
    for column in ("submit_date", "start_date", "end_date"):
        if jobs[column].isna().any():
            raise ValueError(f"Lisa {column} 存在缺失值")
    jobs["runtime_s"] = (jobs.end_date - jobs.start_date).dt.total_seconds()
    jobs["observed_wait_s"] = (jobs.start_date - jobs.submit_date).dt.total_seconds()
    if jobs.runtime_s.lt(0).any() or jobs.observed_wait_s.lt(0).any() or jobs.numcores.le(0).any():
        raise ValueError("Lisa 作业包含负运行时长、负等待或无效核心数量")
    jobs["hardware_group"] = jobs.nodetypes.str.startswith("gpu").map({True: "gpu_partition", False: "cpu_partition"})
    jobs["task_id"] = "lisa:" + jobs.id.astype(str)
    jobs["flexibility_status"] = "unknown"
    jobs["deadline_source"] = "not_published"
    jobs["preemption_permission_source"] = "not_published"
    jobs.to_parquet(output / "lisa-tasks.parquet", index=False)
    hardware = pd.read_parquet(hardware_path)
    summary = {"source": "SURF Lisa 官方 Zenodo 13685426 v3",
               "source_url": "https://zenodo.org/records/13685426",
               "job_rows": len(jobs), "unique_job_ids": int(jobs.id.nunique()),
               "first_submit_source_time": str(jobs.submit_date.min()), "last_end_source_time": str(jobs.end_date.max()),
               "job_time_unit": "秒级时间戳",
               "source_timezone": "Parquet 时间未携带时区，连接全球 UTC 气象前须向来源核实",
               "monitoring": {"published_sampling_seconds": 30,
                              "evidence": "官方数据说明及数据整合代码；本次未下载全套监测"},
               "hardware_metadata_rows": len(hardware), "hardware_metadata_cpu_cores": int(hardware.cpu_core_count_total.sum()),
               "hardware_metadata_gpus": int(hardware.gpu_count.sum()),
               "groups": {}, "constraint_unknown_rows": len(jobs),
               "classification_scope": "按来源分区名称区分 CPU 与 GPU 分区，未从 GPU 分区推定任务使用卡数或训练/推理类型",
               "inputs_sha256": {"jobs_zip": sha256(jobs_zip), "hardware": sha256(hardware_path)}}
    begin, end = jobs.start_date.min().floor("h"), jobs.end_date.max().ceil("h")
    demands, fives = [], []
    for name, selected in jobs.groupby("hardware_group"):
        summary["groups"][name] = {"job_count": len(selected),
                                  "runtime_seconds_quantiles": {str(q): float(selected.runtime_s.quantile(q)) for q in (.25, .5, .75, .9, .99)},
                                  "runtime_under_60s_fraction": float(selected.runtime_s.lt(60).mean()),
                                  "runtime_under_3600s_fraction": float(selected.runtime_s.lt(3600).mean()),
                                  "allocated_core_hours": float((selected.runtime_s * selected.numcores).sum() / 3600),
                                  "source_partitions": selected.nodetypes.value_counts().to_dict()}
        results = {}
        for frequency, label in (("h", "hourly"), ("5min", "5min")):
            edges = pd.date_range(begin, end, freq=frequency)
            work = interval_resource_hours(selected.start_date.array.asi8, selected.end_date.array.asi8,
                                           selected.numcores, edges.asi8)
            np.testing.assert_allclose(work.sum(), summary["groups"][name]["allocated_core_hours"], rtol=1e-11)
            result = pd.DataFrame({"source_time": edges[:-1],
                                   "relative_hour": (edges[:-1] - begin).total_seconds() / 3600,
                                   "hardware_group": name, "allocated_core_hours": work})
            results[label] = result
        rebinned = results["5min"].set_index("source_time").allocated_core_hours.resample("h").sum()
        np.testing.assert_allclose(rebinned, results["hourly"].allocated_core_hours, rtol=1e-9, atol=1e-6)
        demands.append(results["hourly"])
        fives.append(results["5min"])
    pd.concat(demands, ignore_index=True).to_parquet(output / "lisa-hourly-core-demand.parquet", index=False)
    pd.concat(fives, ignore_index=True).to_parquet(output / "lisa-5min-core-demand.parquet", index=False)
    summary["resource_time_reference"] = "保留源文件无时区时间和相对小时，不直接赋予 UTC 时区"
    summary["input_md5"] = {}
    for name, path in (("slurm_table_cleaned.zip", jobs_zip), ("node_hardware_info.parquet", hardware_path)):
        digest = hashlib.md5()
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        summary["input_md5"][name] = digest.hexdigest()
    expected = {"slurm_table_cleaned.zip": "ae697e29d3d4ce10c4b1ab670b82d06c",
                "node_hardware_info.parquet": "9c004d3ac06a97f6de1e0917640a9464"}
    if summary["input_md5"] != expected:
        raise ValueError("Lisa 输入文件与官方公开 MD5 不一致")
    summary["validation"] = {"official_md5": "passed", "job_id_uniqueness": "passed",
                             "nonnegative_run_and_wait": "passed", "core_hour_conservation": "passed",
                             "five_minute_to_hourly": "passed"}
    summary["analysis_code_sha256"] = {name: sha256(Path(__file__).with_name(name)) for name in
                                       ("audit_lisa_tasks.py", "task_trace_inputs.py")}
    summary["software"] = {"numpy": np.__version__, "pandas": pd.__version__}
    (output / "lisa-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="核对 Lisa CPU/GPU 作业粒度、分区和服务约束")
    parser.add_argument("--jobs-zip", type=Path, required=True)
    parser.add_argument("--hardware-parquet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = audit_lisa(args.jobs_zip, args.hardware_parquet, args.output_dir)
    print(json.dumps({key: result[key] for key in ("job_rows", "groups", "validation")}, ensure_ascii=False))
