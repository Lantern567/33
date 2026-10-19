# 共享数据字典与接收规范

模板见 [initial_input.template.json](initial_input.template.json)。模板没有实测记录。方向一任务及执行控制、方向三工程门槛分别按照[项目当前研究入口](../../README.md)中的方向文档确认。

## 必须保留的共同字段

所有表保留 `record_id`、`source_id`、`source_row_or_page`、`evidence_type`、`missing_reason`。来源表使用 `source_id` 为主键；其他表的 source_id 必须能关联。`evidence_type` 为 observed/reported/derived/assumed，分别表示观测、来源报告、推导和情景假设。来源明确不等于参数已适合试点。

未知数值用 null，不能填0；空 records 表示未录入。原始数据不覆盖。时间保留原始时区、采样间隔与日历；真实时间可映射UTC，脱敏相对时间保留原样，另建明确的合成映射说明，不能伪造观测日期。

## 核心表

| 表/唯一键 | 主要字段 | 单位/检查 | 两方向使用方式 |
|---|---|---|---|
| source_register/source_id | title、url_or_holder、local_path、retrieved_at、version、sha256、license、use_scope、status | 日期/版本/许可；status区分文档已读、文件已收、已校验、可入模 | 追溯每个输入 |
| facilities/facility_id | name、country、grid_region、record_level、lat/lon、geometry_precision、timezone、service_type、connection_limit_mw | 点位与园区层级分开；纬经度WGS84；接电MW | D1站点及D3既有站点，不自动关联匿名机器 |
| facility_intervals/(facility_id,start,interval_minutes) | meter_boundary、start、time_kind、interval_minutes、energy_kwh、average_power_kw、it_power_kw、pue、quality_flag | 15/30分钟原序列保留；kWh与kW区分；总表计不得重复乘PUE | D3至少12连续月+计费追溯；D1验证总设施用电 |
| cfe_supply/(contract_id,attribute_id,interval_start) | node/grid_region、eligible_mwh、available_mwh、attributable_share、already_committed_mwh、delivery_path、loss_fraction、attribute_id | MWh、0–1；合同资格、地域、时段、唯一属性需证据 | 计算合格CFE；不能用气象模拟代替权利 |
| cfe_allocations/allocation_id | contract_id、attribute_id、facility_id、interval_start、matched_to_load_mwh、charged_to_clean_storage_mwh、claimed_loss_aux_mwh、delivered_mwh、delivery_evidence | 单站分配关联同一合同属性池；各站同时段认领合计不超扣除既有承诺与交付损耗后的可分配量；负荷、入储和损耗用途互斥 | 支持方向一多站合同分配；两方向均防重复认领 |
| tariffs/(tariff_id,valid_from) | customer_class、currency、price_year、energy_charge_per_kwh、demand_charge_per_kw、billing_interval_minutes、lookback_months、fixed_fee、valid_to | 需量/容量/电量收费分开；负电价可真实存在；原账单另留 | 15/30分钟计费与小时CFE分别计算 |
| storage_parameters/(technology_id,parameter_name,version) | parameter_name、value、unit、region、price_year、basis、lifetime_type、boundary | kW/kWh成本分开；效率/自耗/寿命；多日路线拆链条 | 两方向共同参数，D3按站点准入 |
| site_technology_eligibility/(facility_id,technology_id,version) | engineering_status、land_available、connection_verified、reserve_response_verified、lead_time_months、evidence_path、reviewer、reviewed_at | 工程准入按站点/技术/版本独立判定；不能由通用参数直接推断 | 磷酸铁锂、液流、多日路线均逐站取证 |
| asset_cohorts/(asset_id,vintage) | facility_id、technology_id、commission_year、remaining_life、power_mw、energy_mwh、initial_soc_mwh、initial_cfe_soc_mwh、reserve_mwh、lead_time_months、replacement_rule、salvage_rule | 总SOC≥CFE SOC≥0；存量、备用、退化与替换不能漏计 | 分阶段承接；GPU更新路径同未来情境保持一致 |
| emission_factors/(factor_id,valid_from) | value、unit、location、temporal_resolution、average_or_marginal、included_stages、includes_charging、allocation_rule | kgCO2e/kWh等；制造/运行/退役；平均和边际分别命名 | CFE、电力碳足迹与系统净减排分别报告 |
| workload_tasks/job_id | arrival、time_kind、work_amount、work_unit、quality_target、true_deadline、origin_site、allowed_sites、control_eligibility、gpu_type、profile_id | 真实期限不能从结束时刻/优先级推断；控制权限有证据 | D1调节；D3仅共同正常运行输入 |
| stages/(pathway_id,stage_id) | start/end、annual_weighted_cfe_target、hourly_floor、final_deadline、budget、information_set、hardware_update_path | 阶段目标、小时下限与终点分开；共同信息；金额币种价格年统一 | 两理念/多投资路径公平比较 |

## 最低接收检查

1. 主键重复、来源缺失、空值、采样间隔变化、断点、时区与闰日分别登记。缺失率和可接受阈值按试点决定，不能先填“通过”。
2. 原始区间电量可求和得到小时电量；原始功率需按实际时长积分。小时平均不能替代需量计费峰值。
3. 记录CFE属性来源、承诺、分配和消耗；同一合同属性池在各站认领之和不得超过该小时可分配量，供给总量只在来源表记录一次，不能随站点分配重复求和；总储能库存与合格无碳库存分别记账，充电和放电不能双重认领，损耗/自耗与终端库存需核对。
4. 费用统一币种、价格年和折现口径；真实现金流不再叠加同额会计折旧；净购电账单不能再叠加相同套利收益。
5. 生命周期因子写清是否已含运行/充电用电，避免重复核算；物理排放按发生年度累计，经济残值不能直接转成负排放。
6. 每个假设保留理由、范围和适用场景；没有概率依据的未来情景报告范围，不报告风险概率。

此处是后续数据入模的检查清单。已取得公开小文件的实际结构检查另见[接收报告](../../data/metadata/public-seed/intake_report.md)，不表示真实设施输入已经通过检查。
