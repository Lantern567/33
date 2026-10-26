import argparse
import copy
import hashlib
import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

from global_grid_flex_solver import solve_four_scenarios, solve_grid, write_outputs


def reconstruct_deadlines(frame, fraction, deadline, return_metrics=False):
    pending = deque()
    maximum_lag = 0
    delayed_work = 0.0
    waiting_integral = 0.0
    for hour, amount in enumerate(frame.flexible_service_module_hours):
        if fraction > 0:
            pending.append([hour, fraction])
        remaining = float(amount)
        if remaining < -2e-6:
            raise ArithmeticError("柔性工作量为负数")
        while remaining > 1e-9 and pending:
            arrival, unfinished = pending[0]
            completed = min(remaining, unfinished)
            remaining -= completed
            pending[0][1] -= completed
            if hour > arrival:
                delayed_work += completed
                waiting_integral += completed * (hour - arrival)
            if completed > 2e-6:
                maximum_lag = max(maximum_lag, hour - arrival)
            if pending[0][1] < 1e-9:
                pending.popleft()
        if remaining > 2e-6:
            raise ArithmeticError("执行量超过已到达任务量")
        if pending and hour - pending[0][0] >= deadline and pending[0][1] > 2e-6:
            raise ArithmeticError("按最早截止时间重建时发现超期任务")
    if sum(item[1] for item in pending) > 2e-6 or maximum_lag > deadline:
        raise ArithmeticError("任务重建存在期末遗漏或完成超期")
    np.testing.assert_allclose(waiting_integral, frame.backlog_module_hours.sum(), atol=2e-6, rtol=0)
    if return_metrics:
        return {"edf_maximum_completion_lag_h": maximum_lag,
                "edf_delayed_service_module_hours": delayed_work,
                "edf_waiting_integral_module_hour_hours": waiting_integral,
                "edf_mean_lag_flexible_work_h": waiting_integral / (fraction * len(frame)) if fraction > 0 else 0.0}
    return maximum_lag


def compare_same_solution(left, right, label):
    first, second = left["summary"], right["summary"]
    if first["feasible"] is None or second["feasible"] is None:
        raise RuntimeError(f"{label}存在未完成求解的情景")
    if first["feasible"] != second["feasible"]:
        raise ArithmeticError(f"{label}可行性不一致")
    if first["feasible"] is not True:
        return {"check": label, "status": "same_feasibility", "feasible": first["feasible"]}
    np.testing.assert_allclose(first["annual_cost_usd"], second["annual_cost_usd"], rtol=1e-7, atol=0.1)
    return {"check": label, "status": "passed", "annual_cost_difference_usd": first["annual_cost_usd"] - second["annual_cost_usd"]}


def validate(hourly, config):
    paired = solve_four_scenarios(hourly, config)
    if any(item["summary"]["feasible"] is None for item in paired["scenarios"].values()):
        raise RuntimeError("主验证情景存在未完成求解的状态")
    checks = []
    fixed = paired["scenarios"]["CS"]
    for key, value in (("flexible_fraction", 0), ("deadline_h", 0)):
        changed = copy.deepcopy(config)
        changed[key] = value
        limited = solve_grid(hourly, changed, f"boundary_{key}_zero", True, True)
        checks.append(compare_same_solution(fixed, limited, f"{key}=0与固定任务一致"))
    changed = copy.deepcopy(config)
    changed["capacity_multiple_max"] = 1
    changed["capacity_limits"]["compute_capacity_multiple"] = {"value": 1, "source": "共同工作量与无新增算力的边界验证", "status": "validation_boundary"}
    no_extra_fixed = solve_grid(hourly, changed, "boundary_r1_fixed", True, False)
    no_extra_flex = solve_grid(hourly, changed, "boundary_r1_flexible", True, True)
    checks.append(compare_same_solution(no_extra_fixed, no_extra_flex, "满载r=1无额外移峰收益"))
    if no_extra_flex["summary"]["feasible"] is True:
        np.testing.assert_allclose(no_extra_flex["hourly"].service_module_hours, 1, rtol=0, atol=2e-6)
        checks.append({"check": "满载r=1逐小时工作量固定为1", "status": "passed"})
    # 在真实资源曲线上将可建设发电容量限定为零，检查缺电不能由未完成任务补偿。
    zero_generation = copy.deepcopy(config)
    for key in ("pv_mw", "wind_mw"):
        zero_generation["capacity_limits"][key] = {"value": 0, "source": "无可建设发电容量边界验证", "status": "validation_boundary"}
    impossible = solve_grid(hourly, zero_generation, "boundary_no_generation", True, True)
    if impossible["summary"]["status"] != "infeasible":
        raise ArithmeticError("没有发电容量时仍被报告可行")
    checks.append({"check": "零发电容量严格不可行", "status": "passed"})
    for name, item in paired["scenarios"].items():
        if item["summary"]["feasible"] is not True:
            continue
        frame = item["hourly"]
        # 从输出功率和工作量独立重算，避免仅依赖优化矩阵的残差。
        np.testing.assert_allclose(frame.service_module_hours.sum(), len(frame), atol=2e-6, rtol=0)
        np.testing.assert_allclose(frame.pv_power_mw + frame.wind_power_mw + frame.battery_discharge_mw,
                                   frame.facility_power_mw + frame.battery_charge_mw + frame.curtailment_mw, atol=2e-6, rtol=0)
        previous = np.r_[frame.battery_soc_mwh.iloc[-1], frame.battery_soc_mwh.iloc[:-1]]
        np.testing.assert_allclose(frame.battery_soc_mwh,
                                   (1 - config["battery_hourly_loss"]) * previous + config["battery_charge_efficiency"] * frame.battery_charge_mw - frame.battery_discharge_mw / config["battery_discharge_efficiency"], atol=2e-6, rtol=0)
        if name in ("C0", "CD"):
            np.testing.assert_allclose(frame[["battery_charge_mw", "battery_discharge_mw", "battery_soc_mwh"]], 0, atol=2e-6, rtol=0)
        np.testing.assert_allclose(np.minimum(frame.battery_charge_mw, frame.battery_discharge_mw), 0, atol=2e-6, rtol=0)
        flexible = name in ("CD", "CSD")
        lag = reconstruct_deadlines(frame, config["flexible_fraction"] if flexible else 0, config["deadline_h"] if flexible else 0)
        checks.append({"check": f"{name}独立复算工作量、电力、循环库存、充放电及逐批期限", "status": "passed", "edf_maximum_completion_lag_h": lag})
    if not any(item["summary"]["feasible"] is True for item in paired["scenarios"].values()):
        raise ArithmeticError("真实资源验证没有任何可行的主情景，不能完成可行解验证")
    return paired, {"status": "passed", "real_weather_hours": len(hourly), "checks": checks,
                    "validation_scope": "真实天气小段上的参考模块技术情景；不形成全球或年度收益结论",
                    "mock_or_generated_weather": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hourly", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--hours", type=int, default=168)
    args = parser.parse_args()
    frame = pd.read_parquet(args.hourly)
    if args.hours < 48 or args.hours > len(frame):
        raise ValueError("真实天气验证时长必须至少48小时且不得超过输入")
    frame = frame.iloc[:args.hours].copy()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    paired, report = validate(frame, config)
    write_outputs(paired, args.output_dir)
    report.update(hourly_input_path=str(args.hourly.resolve()), hourly_input_sha256=hashlib.sha256(args.hourly.read_bytes()).hexdigest(),
                  config_input_path=str(args.config.resolve()), config_input_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest(),
                  solver_script_sha256=hashlib.sha256(Path(__file__).with_name("global_grid_flex_solver.py").read_bytes()).hexdigest())
    (args.output_dir / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
