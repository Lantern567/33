from pathlib import Path

import numpy as np
import pandas as pd

from compute_load import ResourceProfile
from compute_load.model import sha256


ACME_TYPES = {"CPU": "cpu_unspecified", "Pretrain": "training", "SFT": "fine_tuning",
              "Eval": "evaluation", "Debug": "development", "Other": "unknown"}


def load_acme(path):
    raw = pd.read_csv(path, dtype={"job_id": str})
    required = {"job_id", "gpu_num", "cpu_num", "type", "state", "submit_time", "start_time", "end_time"}
    if not required.issubset(raw.columns) or raw.job_id.isna().any() or raw.job_id.duplicated().any():
        raise ValueError("Acme 作业字段不全或 job_id 缺失、重复")
    frame = raw.copy()
    frame["task_id"] = "acme-kalos:" + frame.job_id
    for name in ("submit_time", "start_time", "end_time"):
        frame[name] = pd.to_datetime(frame[name], format="mixed", utc=True)
    for name in ("gpu_num", "cpu_num"):
        values = frame[name].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{name} 必须为有限非负资源数量")
    frame["runtime_s"] = (frame.end_time - frame.start_time).dt.total_seconds()
    frame["observed_wait_s"] = (frame.start_time - frame.submit_time).dt.total_seconds()
    frame["turnaround_s"] = (frame.end_time - frame.submit_time).dt.total_seconds()
    frame["interval_valid"] = frame.runtime_s.ge(0) & frame.observed_wait_s.ge(0)
    frame["hardware"] = np.where(frame.gpu_num.gt(0), "gpu", "cpu")
    frame["task_type"] = frame.type.map(ACME_TYPES).fillna("unknown")
    frame["candidate_for_service_review"] = frame.task_type.isin(["training", "fine_tuning", "evaluation"])
    frame["deadline_utc"] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    frame["preemption_allowed"] = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    frame["flexibility_status"] = "unknown"
    frame["constraint_evidence"] = "来源未公开业务截止时间与任务抢占权限"
    frame.attrs = {"source": "AcmeTrace Kalos 官方作业表", "source_sha256": sha256(path),
                   "interval": "start_time 至 end_time；原始 duration 与 gpu_time 保留各自口径",
                   "cpu_scope": "gpu_num=0 的独立 CPU 作业；GPU 作业宿主 CPU 不另建独立负荷"}
    return frame


def interval_resource_hours(starts, ends, units, edges):
    starts, ends, edges = (np.asarray(values, dtype=np.int64) for values in (starts, ends, edges))
    units = np.asarray(units, dtype=float)
    if starts.ndim != 1 or starts.shape != ends.shape or starts.shape != units.shape:
        raise ValueError("作业区间与资源数量必须为等长的一维数组")
    if len(edges) < 2 or edges.ndim != 1 or (np.diff(edges) <= 0).any() or (ends < starts).any():
        raise ValueError("积分边界必须递增且作业结束不能早于启动")
    if not np.isfinite(units).all() or (units < 0).any():
        raise ValueError("资源数量必须有限且非负")
    # 对运行区间积分，保留短作业在每个时间段内的实际占用。
    times = np.concatenate([starts, ends])
    changes = np.concatenate([units, -units])
    if len(times):
        event_times, inverse = np.unique(times, return_inverse=True)
        delta = np.bincount(inverse, weights=changes)
        rate = delta.cumsum()
        origin = event_times[0]
        seconds = (event_times - origin) / 1e9
        cumulative = np.concatenate([[0.0], np.cumsum(rate[:-1] * np.diff(seconds))])
        integrated = np.interp((edges - origin) / 1e9, seconds, cumulative,
                               left=0, right=float(cumulative[-1]))
        work = np.diff(integrated) / 3600
    else:
        work = np.zeros(len(edges) - 1)
    if (work < -1e-8).any():
        raise ValueError("区间积分出现负资源小时")
    return work


def integrate_jobs(tasks, edges, resource_column):
    edges = pd.DatetimeIndex(pd.to_datetime(edges, utc=True))
    if edges.isna().any():
        raise ValueError("积分边界不能缺少时间")
    if not tasks.interval_valid.all():
        raise ValueError("积分输入包含无有效执行区间的作业，须在审阅后显式选择有效记录")
    work = interval_resource_hours(tasks.start_time.array.asi8, tasks.end_time.array.asi8,
                                   tasks[resource_column], edges.asi8)
    duration_h = np.diff(edges.asi8) / 3.6e12
    return pd.DataFrame({"time_utc": edges[:-1], "interval_end_utc": edges[1:],
                         "resource_hours": work, "mean_allocated_units": work / duration_h})


def read_asi_hour(pod_path, server_path, relative_day, hour):
    if relative_day not in range(185) or hour not in range(24):
        raise ValueError("ASI 相对日或小时超出公开范围")
    pods, servers = pd.read_parquet(pod_path), pd.read_parquet(server_path)
    if servers.server_id.isna().any() or servers.server_id.duplicated().any():
        raise ValueError("服务器库存需要唯一非空 server_id")
    gpu = pods.loc[pods.gpu_request.gt(0)].copy()
    if gpu.pod_id.isna().any() or gpu.duplicated(["pod_id", "server_id"]).any():
        raise ValueError("同一小时的 GPU pod/server 记录存在缺失标识或重复")
    if not gpu.server_id.isin(servers.server_id).all():
        raise ValueError("GPU 作业引用的服务器未出现在同小时库存")
    for name in ("gpu_request", "used_gpu_hours"):
        values = gpu[name].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{name} 必须为有限非负值")
    capacity = float(servers.gpu_count.sum())
    if capacity <= 0 or not np.isfinite(capacity):
        raise ValueError("同小时 GPU 库存必须为有限正数")
    gpu["constraint_status"] = "unknown"
    gpu["candidate_for_service_review"] = gpu.job_type_public.isin(["training", "offline_inference"])
    groups = gpu.groupby(["job_type_public", "priority_class"], dropna=False).agg(
        pod_observations=("pod_id", "size"), requested_gpu_equivalents=("gpu_request", "sum"),
        used_gpu_hours=("used_gpu_hours", "sum")).reset_index()
    groups["relative_day"] = relative_day
    groups["hour"] = hour
    groups["inventory_gpu_count"] = capacity
    groups["requested_fraction"] = groups.requested_gpu_equivalents / capacity
    groups["used_gpu_hour_fraction"] = groups.used_gpu_hours / capacity
    groups["constraint_status"] = "unknown"
    quality = {"all_pod_observations": len(pods), "gpu_pod_observations": len(gpu),
               "excluded_zero_gpu_observations": len(pods) - len(gpu),
               "unknown_type_gpu_observations": int(gpu.job_type_public.eq("unknown").sum()),
               "missing_sm_util_gpu_observations": int(gpu.avg_gpu_sm_util.isna().sum()),
               "sm_util_above_100_gpu_observations": int(gpu.avg_gpu_sm_util.gt(100).sum()),
               "published_deadline_observations": 0, "published_preemption_permission_observations": 0}
    return groups, quality


def resource_profile(demand, capacity, hardware, source, capacity_basis):
    if not source or not capacity_basis:
        raise ValueError("必须说明需求来源和参考资源容量依据")
    demand = np.asarray(demand, dtype=float)
    capacity = np.asarray(capacity, dtype=float)
    if capacity.ndim not in (0, 1) or (capacity.ndim == 1 and capacity.shape != demand.shape):
        raise ValueError("容量须为标量或与需求等长的逐小时序列")
    if not np.isfinite(capacity).all() or (capacity <= 0).any():
        raise ValueError("参考资源容量必须有限且为正数")
    return ResourceProfile(hardware, demand / capacity, {
        "source": source, "capacity_basis": capacity_basis,
        "resource_semantics": "分配资源或归属 GPU 小时的代理份额；非实测节点利用率",
        "flexibility_evidence": "业务期限与抢占权限须另外提供"})
