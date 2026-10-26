import argparse
import copy
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import linprog


COST_KEYS = (
    "compute_module_usd_year", "pv_usd_mw_year", "wind_usd_mw_year",
    "battery_power_usd_mw_year", "battery_energy_usd_mwh_year",
    "battery_throughput_usd_mwh",
)
LIMIT_KEYS = (
    "pv_mw", "wind_mw", "battery_power_mw", "battery_energy_mwh",
    "compute_capacity_multiple",
)
SCENARIOS = {
    "C0": (False, False), "CS": (True, False),
    "CD": (False, True), "CSD": (True, True),
}


def evidenced_values(config, group, keys):
    values = {}
    for key in keys:
        entry = config[group][key]
        value = float(entry["value"])
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"{group}.{key}必须为有限非负数")
        for field in ("source", "status"):
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise ValueError(f"{group}.{key}.{field}必须说明来源或情景性质")
        values[key] = value
    return values


def check_inputs(hourly, config):
    frame = hourly.copy()
    frame["time_utc"] = pd.to_datetime(frame.time_utc, utc=True)
    if len(frame) < 2 or frame.time_utc.isna().any():
        raise ValueError("必须提供至少两个连续UTC小时")
    if frame.time_utc.diff().iloc[1:].ne(pd.Timedelta(hours=1)).any():
        raise ValueError("时间索引必须无重复、无缺口且按小时递增")
    for name in ("pv_capacity_factor", "wind_capacity_factor", "pue"):
        values = frame[name].to_numpy(float)
        if not np.isfinite(values).all():
            raise ValueError(f"{name}存在非有限值")
        if name == "pue":
            if (values < 1).any():
                raise ValueError("PUE必须不小于1")
        elif ((values < 0) | (values > 1)).any():
            raise ValueError(f"{name}必须位于0至1")
    costs = evidenced_values(config, "costs", COST_KEYS)
    limits = evidenced_values(config, "capacity_limits", LIMIT_KEYS)
    if any(costs[key] <= 0 for key in COST_KEYS[:-1]):
        raise ValueError("设备与容量年化费用必须为正数")
    positive = ("reference_it_mw", "annual_operating_multiplier")
    for name in positive:
        value = float(config[name])
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name}必须为有限正数")
    if float(config["baseline_service_per_hour"]) != 1:
        raise ValueError("本模型工作量单位要求每小时到达1个参考模块时")
    for name in ("flexible_fraction", "idle_fraction", "battery_hourly_loss"):
        value = float(config[name])
        if not np.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{name}必须位于0至1")
    if float(config["battery_hourly_loss"]) == 1:
        raise ValueError("储能每小时损失率必须小于1")
    for name in ("battery_charge_efficiency", "battery_discharge_efficiency"):
        value = float(config[name])
        if not np.isfinite(value) or not 0 < value <= 1:
            raise ValueError(f"{name}必须大于0且不超过1")
    deadline = config["deadline_h"]
    if int(deadline) != deadline or deadline < 0:
        raise ValueError("deadline_h必须为非负整数")
    rmax = float(config["capacity_multiple_max"])
    if not np.isfinite(rmax) or not 1 <= rmax <= 2:
        raise ValueError("capacity_multiple_max必须位于1至2")
    if not config["scenario_label"] or not config["cost_basis"]["source"]:
        raise ValueError("必须说明参数情景及成本来源")
    if config["cost_basis"]["currency"] != "USD" or int(config["cost_basis"]["price_year"]) < 1900:
        raise ValueError("必须登记美元成本的价格年份")
    if not config["cost_basis"]["parameter_status"]:
        raise ValueError("必须标明成本的资料等级或情景性质")
    return frame, costs, limits


def solve_fixed_load(hourly, config, scenario_name, storage_enabled):
    frame = hourly.copy().reset_index(drop=True)
    frame["time_utc"] = pd.to_datetime(frame.time_utc, utc=True)
    if len(frame) < 2 or frame.time_utc.isna().any() or frame.time_utc.diff().iloc[1:].ne(pd.Timedelta(hours=1)).any():
        raise ValueError("固定负荷求解输入必须为连续 UTC 小时")
    for column in ("it_mw", "cooling_mw", "other_mw", "facility_mw", "pv_capacity_factor", "wind_capacity_factor"):
        values = frame[column].to_numpy(float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{column}必须为有限非负数")
        if column.endswith("capacity_factor") and (values > 1).any():
            raise ValueError(f"{column}必须不超过1")
    if not np.allclose(frame.it_mw + frame.cooling_mw + frame.other_mw, frame.facility_mw, rtol=1e-10, atol=1e-9):
        raise ValueError("固定负荷的设施总功率与分项之和不一致")
    reference = float(config["reference_it_mw"])
    if not np.isfinite(reference) or reference <= 0 or not frame.reference_it_capacity_mw.eq(reference).all():
        raise ValueError("成本配置的 reference_it_mw 与负荷的 IT 参考规模不一致")
    if "grid_id" in frame and frame.grid_id.nunique() != 1:
        raise ValueError("固定负荷求解一次只能处理一个网格")
    if "hardware" in frame and frame.hardware.nunique() != 1:
        raise ValueError("固定负荷求解一次只能处理一种硬件")
    costs = evidenced_values(config, "costs", COST_KEYS)
    limits = evidenced_values(config, "capacity_limits", LIMIT_KEYS)
    if any(costs[key] <= 0 for key in COST_KEYS[:-1]):
        raise ValueError("设备与容量年化费用必须为正数")
    multiplier = float(config["annual_operating_multiplier"])
    etac, etad = float(config["battery_charge_efficiency"]), float(config["battery_discharge_efficiency"])
    loss = float(config["battery_hourly_loss"])
    if not np.isfinite([multiplier, etac, etad, loss]).all() or multiplier <= 0 or not 0 < etac <= 1 or not 0 < etad <= 1 or not 0 <= loss < 1:
        raise ValueError("年化系数、充放电效率或储能自放电参数错误")
    basis = config["cost_basis"]
    if basis["currency"] != "USD" or int(basis["price_year"]) < 1900 or not basis["source"] or not basis["parameter_status"] or not config["scenario_label"]:
        raise ValueError("必须登记成本价格年份、来源、情景性质和情景名称")
    n = len(frame)
    summary = {"scenario": scenario_name, "scenario_label": config["scenario_label"],
               "load_model": "weather_coupled_fixed_v1", "storage_enabled": bool(storage_enabled),
               "flexible_enabled": False, "hours": n, "source_parameters": copy.deepcopy(config),
               "cost_basis": copy.deepcopy(basis), "compute_capacity_multiple": 1.0,
               "task_model_scope": "给定资源路径与设备规模，逐小时设施负荷固定；未调度任务",
               "battery_boundary": "交流母线，首尾循环，仅由本地风光充电",
               "reference_it_mw": float(config["reference_it_mw"]),
               "load_provenance": copy.deepcopy(hourly.attrs),
               "facility_energy_mwh": float(frame.facility_mw.sum()), "it_energy_mwh": float(frame.it_mw.sum())}
    for column in ("grid_id", "hardware", "node_count", "installed_reference_it_mw"):
        if column in frame:
            value = frame[column].iloc[0]
            summary[column] = value.item() if isinstance(value, np.generic) else value
    if limits["compute_capacity_multiple"] < 1:
        summary.update(status="infeasible", feasible=False, reason="计算设施容量上限不能容纳给定设备规模")
        return {"summary": summary, "hourly": pd.DataFrame()}
    # 四项可建设能源容量，随后为充电、放电、库存和弃电；设施负荷直接进入功率平衡右侧。
    count = 4 + 4 * n
    index = np.arange(n)
    charge, discharge, soc, curtail = (4 + i * n + index for i in range(4))
    objective = np.zeros(count)
    objective[:4] = [costs[key] for key in COST_KEYS[1:5]]
    objective[discharge] = costs["battery_throughput_usd_mwh"] * multiplier
    upper = np.full(count, np.inf)
    upper[:4] = [limits[key] for key in LIMIT_KEYS[:4]]
    if not storage_enabled:
        upper[2:4] = 0
    equality = sparse.lil_matrix((2 * n, count))
    equality[index, 0] = frame.pv_capacity_factor.to_numpy()[:, None]
    equality[index, 1] = frame.wind_capacity_factor.to_numpy()[:, None]
    equality[index, charge] = -1
    equality[index, discharge] = 1
    equality[index, curtail] = -1
    equality[n + index, soc] = 1
    equality[n + index, 4 + 2 * n + (index - 1) % n] = -(1 - loss)
    equality[n + index, charge] = -etac
    equality[n + index, discharge] = 1 / etad
    inequality = sparse.lil_matrix((3 * n, count))
    for offset, (variables, capacity_column) in enumerate(((charge, 2), (discharge, 2), (soc, 3))):
        inequality[offset * n + index, variables] = 1
        inequality[offset * n + index, capacity_column] = -1
    rhs = np.r_[frame.facility_mw.to_numpy(), np.zeros(n)]
    options = {"primal_feasibility_tolerance": 1e-8, "dual_feasibility_tolerance": 1e-8}
    if "solver_time_limit_seconds" in config:
        options["time_limit"] = float(config["solver_time_limit_seconds"])
    started = time.monotonic()
    result = linprog(objective, A_ub=inequality.tocsr(), b_ub=np.zeros(3 * n),
                     A_eq=equality.tocsr(), b_eq=rhs, bounds=np.column_stack((np.zeros(count), upper)),
                     method="highs", options=options)
    summary.update(solver_status=int(result.status), solver_message=result.message,
                   solve_seconds=time.monotonic() - started)
    if not result.success:
        summary.update(status="infeasible" if result.status == 2 else "not_solved", feasible=False if result.status == 2 else None)
        return {"summary": summary, "hourly": pd.DataFrame()}
    values = result.x
    residual = float(np.max(np.abs(equality @ values - rhs)))
    simultaneous = float(np.minimum(values[charge], values[discharge]).max())
    inequality_error = float(max(0, np.max(inequality @ values)))
    bound_error = float(max(0, np.max(-values), np.max(values - upper)))
    if max(residual, simultaneous, inequality_error, bound_error) > 2e-6:
        raise ArithmeticError("固定负荷求解未通过功率、电量守恒或同时充放电核验")
    frame["it_power_mw"], frame["facility_power_mw"] = frame.it_mw, frame.facility_mw
    frame["pv_power_mw"] = values[0] * frame.pv_capacity_factor
    frame["wind_power_mw"] = values[1] * frame.wind_capacity_factor
    for indices, column in ((charge, "battery_charge_mw"), (discharge, "battery_discharge_mw"), (soc, "battery_soc_mwh"), (curtail, "curtailment_mw")):
        frame[column] = values[indices]
    frame["power_balance_residual_mw"] = frame.pv_power_mw + frame.wind_power_mw + frame.battery_discharge_mw - frame.facility_mw - frame.battery_charge_mw - frame.curtailment_mw
    summary.update(status="optimal", feasible=True, annual_cost_usd=float(result.fun + costs[COST_KEYS[0]]),
                   solver_objective_usd=float(result.fun), compute_annual_usd=costs[COST_KEYS[0]],
                   pv_mw=float(values[0]), wind_mw=float(values[1]), battery_power_mw=float(values[2]),
                   battery_energy_mwh=float(values[3]), diagnostics={"equality_max_abs_residual": residual,
                   "inequality_max_violation": inequality_error, "bound_max_violation": bound_error,
                   "simultaneous_charge_discharge_max_mw": simultaneous})
    return {"summary": summary, "hourly": frame}


def solve_grid(hourly, config, scenario_name, storage_enabled, flexible_enabled):
    mode = config.get("load_model", "legacy_affine")
    if mode == "weather_coupled_fixed_v1":
        if flexible_enabled:
            raise ValueError("天气耦合固定曲线支持 C0/CS；CD/CSD 须按调度后的资源路径重算功率与冷却，当前线性任务模型不能直接使用")
        return solve_fixed_load(hourly, config, scenario_name, storage_enabled)
    if mode != "legacy_affine":
        raise ValueError(f"未识别的负荷模型：{mode}")
    frame, costs, limits = check_inputs(hourly, config)
    started = time.monotonic()
    n = len(frame)
    rmax = min(float(config["capacity_multiple_max"]), limits["compute_capacity_multiple"])
    summary = {
        "scenario": scenario_name, "scenario_label": config["scenario_label"],
        "storage_enabled": bool(storage_enabled), "flexible_enabled": bool(flexible_enabled),
        "hours": n, "start_utc": frame.time_utc.iloc[0].isoformat(),
        "end_utc": frame.time_utc.iloc[-1].isoformat(),
        "service_unit": "reference_compute_module_hour",
        "service_interpretation": "1MW满载IT参考模块的等效计算服务；研究情景，未标定H100实测吞吐",
        "task_model_scope": "连续均匀到达、同一完成期限、可中断任务；期初和期末积压均为零",
        "battery_boundary": "交流母线功率与电量；全时段首尾循环；仅由本地风光充电",
        "battery_throughput_cost_basis": "交流母线放电MWh",
        "cost_basis": copy.deepcopy(config["cost_basis"]),
        "annual_operating_multiplier": float(config["annual_operating_multiplier"]),
        "source_parameters": copy.deepcopy(config),
    }
    if rmax < 1:
        summary.update(status="infeasible", feasible=False, solver_status=None,
                       reason="计算设施建设上限不能容纳共同基准模块")
        return {"summary": summary, "hourly": pd.DataFrame()}
    # 五项容量之后依次为工作量、积压、充电、放电、库存和弃电。
    count = 5 + 6 * n
    offsets = {key: 5 + index * n for index, key in enumerate(("service", "backlog", "charge", "discharge", "soc", "curtailment"))}
    index = np.arange(n, dtype=np.int32)
    objective = np.zeros(count)
    objective[:5] = [costs[key] for key in COST_KEYS[:5]]
    objective[offsets["discharge"] + index] = costs["battery_throughput_usd_mwh"] * float(config["annual_operating_multiplier"])
    lower, upper = np.zeros(count), np.full(count, np.inf)
    lower[0], upper[0] = 1, rmax
    upper[1:5] = [limits[key] for key in LIMIT_KEYS[:4]]
    if not storage_enabled:
        upper[3:5] = 0
    fraction = float(config["flexible_fraction"]) if flexible_enabled else 0.0
    deadline = int(config["deadline_h"]) if flexible_enabled else 0
    lower[offsets["service"] + index] = 1 - fraction
    upper[offsets["backlog"] + index] = fraction * deadline
    upper[offsets["backlog"] + n - 1] = 0
    if not flexible_enabled:
        lower[offsets["service"] + index] = 1
        upper[offsets["service"] + index] = 1
    rows, columns, coefficients = [], [], []

    def block(row, column, value):
        rows.append(np.broadcast_to(row, np.broadcast(row, column, value).shape).ravel())
        columns.append(np.broadcast_to(column, np.broadcast(row, column, value).shape).ravel())
        coefficients.append(np.broadcast_to(value, np.broadcast(row, column, value).shape).ravel())

    pue = frame.pue.to_numpy(float)
    reference = float(config["reference_it_mw"])
    idle = float(config["idle_fraction"])
    etac = float(config["battery_charge_efficiency"])
    etad = float(config["battery_discharge_efficiency"])
    loss = float(config["battery_hourly_loss"])
    block(index, 0, -pue * reference * idle)
    block(index, 1, frame.pv_capacity_factor.to_numpy(float))
    block(index, 2, frame.wind_capacity_factor.to_numpy(float))
    block(index, offsets["service"] + index, -pue * reference * (1 - idle))
    block(index, offsets["charge"] + index, -1)
    block(index, offsets["discharge"] + index, 1)
    block(index, offsets["curtailment"] + index, -1)
    block(n + index, offsets["soc"] + index, 1)
    block(n + index, offsets["soc"] + (index - 1) % n, -(1 - loss))
    block(n + index, offsets["charge"] + index, -etac)
    block(n + index, offsets["discharge"] + index, 1 / etad)
    block(2 * n + index, offsets["backlog"] + index, 1)
    block(2 * n + index[1:], offsets["backlog"] + index[:-1], -1)
    block(2 * n + index, offsets["service"] + index, 1)
    equality = sparse.coo_matrix((np.concatenate(coefficients), (np.concatenate(rows), np.concatenate(columns))), shape=(3 * n, count)).tocsr()
    rhs = np.r_[np.zeros(2 * n), np.ones(n)]
    rows, columns, coefficients = [], [], []
    for number, (key, capacity_column) in enumerate((("service", 0), ("charge", 3), ("discharge", 3), ("soc", 4))):
        block(number * n + index, offsets[key] + index, 1)
        block(number * n + index, capacity_column, -1)
    inequality = sparse.coo_matrix((np.concatenate(coefficients), (np.concatenate(rows), np.concatenate(columns))), shape=(4 * n, count)).tocsr()
    options = {"primal_feasibility_tolerance": 1e-8, "dual_feasibility_tolerance": 1e-8, "threads": 1}
    if "solver_time_limit_seconds" in config:
        options["time_limit"] = float(config["solver_time_limit_seconds"])
    result = linprog(objective, A_ub=inequality, b_ub=np.zeros(4 * n), A_eq=equality, b_eq=rhs,
                     bounds=np.column_stack((lower, upper)), method="highs", options=options)
    summary.update(solver_status=int(result.status), solver_message=result.message,
                   solve_seconds=time.monotonic() - started, variables=count,
                   equality_constraints=3 * n, inequality_constraints=4 * n)
    if not result.success:
        summary.update(status="infeasible" if result.status == 2 else "not_solved", feasible=False if result.status == 2 else None)
        return {"summary": summary, "hourly": pd.DataFrame()}
    solution = np.asarray(result.x)
    charge = solution[offsets["charge"] + index]
    discharge = solution[offsets["discharge"] + index]
    simultaneous = float(np.minimum(charge, discharge).max())
    if simultaneous > 2e-6:
        raise ArithmeticError(f"求解结果存在显著同时充放电：{simultaneous} MW")
    frame["service_module_hours"] = solution[offsets["service"] + index]
    frame["backlog_module_hours"] = solution[offsets["backlog"] + index]
    frame["online_service_module_hours"] = 1 - fraction
    frame["flexible_service_module_hours"] = frame.service_module_hours - (1 - fraction)
    for key, label in (("charge", "battery_charge_mw"), ("discharge", "battery_discharge_mw"), ("soc", "battery_soc_mwh"), ("curtailment", "curtailment_mw")):
        frame[label] = solution[offsets[key] + index]
    r, pv, wind, power, energy = solution[:5]
    frame["it_power_mw"] = reference * (idle * r + (1 - idle) * frame.service_module_hours)
    frame["facility_power_mw"] = frame.it_power_mw * frame.pue
    frame["pv_power_mw"] = pv * frame.pv_capacity_factor
    frame["wind_power_mw"] = wind * frame.wind_capacity_factor
    frame["power_balance_residual_mw"] = frame.pv_power_mw + frame.wind_power_mw + frame.battery_discharge_mw - frame.facility_power_mw - frame.battery_charge_mw - frame.curtailment_mw
    frame["task_balance_residual_module_hours"] = frame.backlog_module_hours + frame.service_module_hours - frame.backlog_module_hours.shift(1, fill_value=0) - 1
    previous_soc = np.roll(frame.battery_soc_mwh.to_numpy(), 1)
    frame["soc_balance_residual_mwh"] = frame.battery_soc_mwh - (1 - loss) * previous_soc - etac * frame.battery_charge_mw + frame.battery_discharge_mw / etad
    cumulative_flexible = frame.flexible_service_module_hours.cumsum().to_numpy()
    minimum_due = fraction * np.maximum(np.arange(1, n + 1) - deadline, 0)
    diagnostics = {
        "equality_max_abs_residual": float(np.abs(equality @ solution - rhs).max()),
        "inequality_max_violation": float(max(0, (inequality @ solution).max())),
        "bound_max_violation": float(max(0, (lower - solution).max(), (solution - upper).max())),
        "power_max_abs_residual_mw": float(frame.power_balance_residual_mw.abs().max()),
        "soc_max_abs_residual_mwh": float(frame.soc_balance_residual_mwh.abs().max()),
        "task_max_abs_residual_module_hours": float(frame.task_balance_residual_module_hours.abs().max()),
        "total_service_error_module_hours": float(abs(frame.service_module_hours.sum() - n)),
        "final_backlog_module_hours": float(abs(frame.backlog_module_hours.iloc[-1])),
        "deadline_max_violation_module_hours": float(max(0, (minimum_due - cumulative_flexible).max())),
        "simultaneous_charge_discharge_max_mw": float(np.minimum(frame.battery_charge_mw, frame.battery_discharge_mw).max()),
    }
    if max(diagnostics.values()) > 2e-6:
        raise ArithmeticError(f"优化结果没有通过守恒及服务核查：{diagnostics}")
    components = {
        "compute_annual_usd": float(r * objective[0]), "pv_annual_usd": float(pv * objective[1]),
        "wind_annual_usd": float(wind * objective[2]), "battery_power_annual_usd": float(power * objective[3]),
        "battery_energy_annual_usd": float(energy * objective[4]),
        "battery_throughput_annual_usd": float(frame.battery_discharge_mw.sum() * costs["battery_throughput_usd_mwh"] * config["annual_operating_multiplier"]),
    }
    annual_cost = sum(components.values())
    if abs(annual_cost - float(result.fun)) > max(0.01, abs(result.fun) * 1e-8):
        raise ArithmeticError("输出成本分项与求解目标值不一致")
    summary.update(status="optimal", feasible=True, annual_cost_usd=annual_cost,
                   solver_objective_usd=float(result.fun), cost_components=components,
                   compute_capacity_multiple=float(r), pv_mw=float(pv), wind_mw=float(wind),
                   battery_power_mw=float(power), battery_energy_mwh=float(energy),
                   completed_service_module_hours=float(frame.service_module_hours.sum()),
                   facility_energy_mwh=float(frame.facility_power_mw.sum()),
                   it_energy_mwh=float(frame.it_power_mw.sum()),
                   curtailment_mwh=float(frame.curtailment_mw.sum()),
                   maximum_backlog_module_hours=float(frame.backlog_module_hours.max()),
                   maximum_service_deviation_from_fixed=float(np.abs(frame.service_module_hours - 1).max()),
                   diagnostics=diagnostics)
    return {"summary": summary, "hourly": frame}


def solve_four_scenarios(hourly, config, scenario_names=None):
    names = scenario_names if scenario_names is not None else (("C0", "CS") if config.get("load_model") == "weather_coupled_fixed_v1" else tuple(SCENARIOS))
    if not names or len(set(names)) != len(names) or any(name not in SCENARIOS for name in names):
        raise ValueError("求解情景必须为 C0、CS、CD、CSD 的非空无重复子集")
    if config.get("load_model") == "weather_coupled_fixed_v1" and any(name not in ("C0", "CS") for name in names):
        raise ValueError("天气耦合固定曲线仅支持 C0/CS；任务柔性情景需要重新建立调度与非线性功率关系")
    solved = {name: solve_grid(hourly, config, name, *SCENARIOS[name]) for name in names}
    summaries = {name: value["summary"] for name, value in solved.items()}

    def difference(left, right):
        if left not in summaries or right not in summaries:
            return None
        if summaries[left]["feasible"] is True and summaries[right]["feasible"] is True:
            return summaries[left]["annual_cost_usd"] - summaries[right]["annual_cost_usd"]
        return None

    comparison = {"demand_value_given_storage_usd_year": difference("CS", "CSD"),
                  "demand_only_value_usd_year": difference("C0", "CD"),
                  "storage_only_value_usd_year": difference("C0", "CS")}
    comparison["synergy_usd_year"] = summaries["CS"]["annual_cost_usd"] + summaries["CD"]["annual_cost_usd"] - summaries["C0"]["annual_cost_usd"] - summaries["CSD"]["annual_cost_usd"] if all(name in summaries and summaries[name]["feasible"] is True for name in SCENARIOS) else None
    for parent, child in (("C0", "CS"), ("C0", "CD"), ("CS", "CSD"), ("CD", "CSD")):
        if parent not in summaries or child not in summaries:
            continue
        first, second = summaries[parent], summaries[child]
        if first["feasible"] is True:
            if second["status"] == "infeasible":
                raise ArithmeticError(f"权限嵌套异常：{parent}可行而{child}不可行")
            if second["feasible"] is True and second["annual_cost_usd"] > first["annual_cost_usd"] + max(0.1, first["annual_cost_usd"] * 1e-7):
                raise ArithmeticError(f"权限嵌套异常：{child}成本超过{parent}")
    return {"scenarios": solved, "comparison": comparison}


def write_outputs(solved, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for name, item in solved["scenarios"].items():
        summaries[name] = item["summary"]
        (output / f"{name}-summary.json").write_text(json.dumps(item["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
        if not item["hourly"].empty:
            item["hourly"].to_parquet(output / f"{name}-hourly.parquet", index=False)
    (output / "comparison.json").write_text(json.dumps(solved["comparison"], ensure_ascii=False, indent=2), encoding="utf-8")
    return summaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hourly", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scenarios", nargs="+", choices=tuple(SCENARIOS))
    args = parser.parse_args()
    frame = pd.read_parquet(args.hourly)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    solved = solve_four_scenarios(frame, config, args.scenarios)
    summaries = write_outputs(solved, args.output_dir)
    provenance = {"hourly_path": str(args.hourly.resolve()), "hourly_sha256": hashlib.sha256(args.hourly.read_bytes()).hexdigest(),
                  "config_path": str(args.config.resolve()), "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
                  "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (args.output_dir / "input-provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scenarios": {name: item["status"] for name, item in summaries.items()}, "comparison": solved["comparison"]}, ensure_ascii=False), flush=True)
    if any(item["status"] == "not_solved" for item in summaries.values()):
        raise RuntimeError("存在未完成求解的情景，已保存对应状态与输入证据")


if __name__ == "__main__":
    main()
