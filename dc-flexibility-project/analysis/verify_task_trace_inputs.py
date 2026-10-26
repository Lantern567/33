import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from task_trace_inputs import integrate_jobs, load_acme, read_asi_hour, resource_profile


def verify(raw):
    raw = Path(raw)
    tasks = load_acme(raw / "trace_kalos.csv")
    assert tasks.flexibility_status.eq("unknown").all()
    assert tasks.deadline_utc.isna().all() and tasks.preemption_allowed.isna().all()
    valid = tasks.loc[tasks.interval_valid]
    checked = 0
    for hardware, column in (("cpu", "cpu_num"), ("gpu", "gpu_num")):
        selected = valid.loc[valid.hardware.eq(hardware)].iloc[:500]
        start = selected.start_time.min().floor("h")
        edges = pd.date_range(start, periods=25, freq="h")
        result = integrate_jobs(selected, edges, column)
        # 用逐作业与逐时间段的交集独立核对事件积分。
        expected = []
        for left, right in zip(edges[:-1], edges[1:]):
            overlap = (np.minimum(selected.end_time.array.asi8, right.value) -
                       np.maximum(selected.start_time.array.asi8, left.value)) / 3.6e12
            expected.append(float((np.maximum(overlap, 0) * selected[column]).sum()))
        np.testing.assert_allclose(result.resource_hours, expected, rtol=1e-10, atol=1e-8)
        checked += len(expected)
    invalid_checks = 0
    for capacity in (0, -1, np.nan, np.inf):
        try:
            resource_profile([1, 2], capacity, "cpu", "真实数据接口的无效参数验证", "显式无效容量")
        except ValueError:
            invalid_checks += 1
        else:
            raise AssertionError("无效容量未被拒绝")
    try:
        integrate_jobs(tasks, pd.date_range(valid.start_time.min().floor("h"), periods=3, freq="h"), "cpu_num")
    except ValueError:
        invalid_checks += 1
    else:
        raise AssertionError("来源中缺少结束时间的作业未经选择即进入了积分")
    manifest = json.loads((raw / "download-manifest.json").read_text(encoding="utf-8"))
    day, hour = manifest["asi_days"][0], manifest["asi_hours"][0]
    relative = f"day={day}/hour={hour:02d}/part-000.parquet"
    groups, quality = read_asi_hour(raw / f"asi_opensource_pod_hourly/{relative}",
                                  raw / f"asi_opensource_server_hourly/{relative}", day, hour)
    assert groups.constraint_status.eq("unknown").all()
    assert int(groups.pod_observations.sum()) == quality["gpu_pod_observations"]
    return {"status": "passed", "independent_interval_bin_checks": checked,
            "invalid_input_checks": invalid_checks,
            "permission_inference": "缺失权限保持未知",
            "input": "官方 AcmeTrace Kalos 作业与 ASI 真实小时分片，无模拟任务"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.raw_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
