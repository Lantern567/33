import argparse
import json
from pathlib import Path
import zipfile

import fsspec
import pyarrow.parquet as pq
import requests

from compute_load.model import sha256


ASI_URL = "https://tre-clusterdata.oss-cn-hangzhou.aliyuncs.com/cluster-trace-gpu-v2026/data/"
ACME_URL = "https://raw.githubusercontent.com/InternLM/AcmeTrace/master/data/job_trace/trace_kalos.csv"
POD_COLUMNS = ["pod_id", "workload_id", "server_id", "cluster_id", "state_public",
               "gpu_spec_public", "priority_class", "job_type_public", "model_type_public",
               "gpu_request", "cpu_request_cores", "used_gpu_hours", "avg_gpu_sm_util",
               "schedule_delay_sec", "ready_delay_sec"]


def fetch(output, days, hours):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if not days or len(set(days)) != len(days) or any(day not in range(185) for day in days):
        raise ValueError("days 必须为 0 至 184 内无重复的相对日")
    if not hours or len(set(hours)) != len(hours) or any(hour not in range(24) for hour in hours):
        raise ValueError("hours 必须为 0 至 23 内无重复的小时")
    manifest = {"source": "Alibaba GPU 2026 与 AcmeTrace Kalos 官方公开记录",
                "asi_days": days, "asi_hours": hours, "files": []}
    path = output / "trace_kalos.csv"
    if not path.exists():
        with requests.get(ACME_URL, stream=True, timeout=90) as response:
            response.raise_for_status()
            temporary = path.with_suffix(".csv.part")
            with temporary.open("wb") as target:
                for block in response.iter_content(1024 * 1024):
                    target.write(block)
            temporary.replace(path)
    manifest["files"].append({"file": path.name, "url": ACME_URL, "sha256": sha256(path)})
    for kind in ("pod", "server"):
        archive_name = f"asi_opensource_{kind}_hourly"
        url = ASI_URL + archive_name + ".zip"
        with fsspec.open(url, block_size=1024 * 1024).open() as remote:
            with zipfile.ZipFile(remote) as archive:
                for day in sorted(days):
                    for hour in sorted(hours):
                        member = f"{archive_name}/day={day}/hour={hour:02d}/part-000.parquet"
                        path = output / member
                        if not path.exists():
                            columns = POD_COLUMNS if kind == "pod" else None
                            with archive.open(member) as stream:
                                table = pq.read_table(stream, columns=columns)
                            path.parent.mkdir(parents=True, exist_ok=True)
                            temporary = path.with_suffix(".parquet.part")
                            pq.write_table(table, temporary, compression="zstd")
                            temporary.replace(path)
                        record = {"file": path.relative_to(output).as_posix(), "url": url,
                                  "archive_member": member, "archive_member_crc32": archive.getinfo(member).CRC,
                                  "column_selection": POD_COLUMNS if kind == "pod" else "all",
                                  "sha256": sha256(path)}
                        manifest["files"].append(record)
                        print(json.dumps({"kind": kind, "day": day, "hour": hour, "bytes": path.stat().st_size}), flush=True)
    (output / "download-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="按 ZIP 分片读取官方 GPU 小时样本，并获取有秒级时间的 CPU/GPU 作业")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--days", nargs="+", type=int, default=[109])
    parser.add_argument("--hours", nargs="+", type=int, default=list(range(24)))
    args = parser.parse_args()
    result = fetch(args.output_dir, args.days, args.hours)
    print(json.dumps({"files": len(result["files"]), "status": "complete"}), flush=True)


if __name__ == "__main__":
    main()
