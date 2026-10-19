# 方向一 初始数据需求、字段字典与来源映射

状态：字段模板与采集清单；无填充的案例数值。依据：[方向一方案](../../sources/local-documents/方向一_24小时无碳电力匹配_研究方案_简版_20261017.md)及[计算细节](../../sources/local-documents/方向一_CFE约束与柔性收益_计算细节_20261018.md)。本文的字段名是建议的项目内部标准，不是声称上游数据集已有同名字段。下表来源与范围说明以两份原文为据；本步未重新执行全部外部来源核查。

## 1. 登记与接入规则

资料分为：`proposal_listed`（方案列出）、`local_present`（本地可定位）、`archived_restore_required`（有归档清单、待恢复）、`downloaded_unverified`（已取得未验证）、`validated_for_use`（完成字段/时间/地域/许可核验）、`missing`（缺失）。只有 `validated_for_use` 且证据类型为实测的记录允许作为实测输入参与正式运行；“文献参数”和“假设情景”另设 evidence_type，不能改名为实测。

每批数据先登记 `source_id`、原始文件相对路径、获取时间、原始来源、许可、版本/哈希、时间范围、时区、地域、单位、字段说明、缺失值规则、脱敏方式、核验人及状态。保留原文件，只把规范化副本写入处理目录。所有任务时间保留原始精度；能源侧至少支持逐小时匹配。

建议字段质量标记：`observed` 实测；`published_parameter` 公开参数；`assumed_scenario` 假设情景；`derived` 可追溯派生；`missing` 缺失。缺值用空值和原因表示，不填零。

## 2. 建议数据表与关键字段

下表中同一行的多个字段仍应在正式字典中逐个建行，填写来源字段、类型、单位和转换规则。P0 表示缺失会阻断相应组合的可信运行，P1 表示可先登记、在对应拓展前补齐。

| 表/主键 | 必备字段及建议单位 | 约束与用途 | 优先级 |
| --- | --- | --- | --- |
| sites：site_id | grid_region_id、timezone、location_precision、assessment_start/end | 地点可用匿名站点代号，但必须有可验证电网映射和共同覆盖期 | P0 |
| jobs：job_id | arrival_ts、job_type、effective_work、work_unit、quality_requirement、deadline_ts、dependency_ids | 时间保留原精度；真实期限不得由优先级或完成时间冒充 | P0 |
| jobs：job_id | origin_site_id、eligible_site_ids、location_allowed、delay_allowed、power_control_allowed、checkpoint_allowed、migration_allowed、eligibility_evidence_id | 区分资格与实际采用量；未知授权不能填 true | P0 |
| baseline_events：event_id | job_id、site_id、queue_enter_ts、start_ts、end_ts、retry_id、policy_version | 重建正常派发/排队/执行，不把历史自然排队延迟全部当作主动延后余量 | P0 |
| compute_profiles：profile_id | job_type、gpu_type、gpu_count、power_cap_W、effective_rate、rate_unit、whole_node_power_W、quality_score、latency_s、measurement_context | 功率档位与有效处理量、质量需成对校准；GPU 功率不等于整机功率 | P0（D3 尤其需要） |
| control_overheads：overhead_id | profile_id、action_type、init_s/kWh、save_s/kWh、restore_s/kWh、lost_work、state_size_GB、model_size_GB | 暂停恢复及迁移要计入时间、能耗、进度损失；单列单位避免混用 | P0（对应控制） |
| facility_capacity：site_id,time | available_gpu_by_type、cpu/memory_capacity、background_usage、idle_power_kW、facility_limit_kW、cooling_power_kW、aux_power_kW | 实际承接余量必须扣背景任务、资源和电力边界；冷却需可追溯模型或测量 | P0 |
| energy_assets：asset_id | site_id、technology、existing_capacity_MW、commission_date、asset_age_year、remaining_life_year | 公共初始资产快照，不用候选容量代替已投运容量 | P0 |
| clean_supply：asset_id,time | generation_MWh、grid_region_id、eligible_CFE_MWh、allocation_limit、prior_commitment_MWh、attribute_rule_id | 可认领清洁电量不能由模拟风光出力自动推定 | P0 |
| cfe_source_pool：contract_id,attribute_id,time | available_source_MWh、delivery_region、source_time、claim_owner、prior_claim_MWh | 跨站共享同一属性池，不能按站点复制可认领额度 | P0（S2） |
| cfe_allocations：contract_id,attribute_id,time,site_id | allocated_MWh、delivery_evidence_id | 按来源池汇总各站分配量不得超过可用量；交付资格单独核验 | P0（S2） |
| energy_contracts：contract_id | start/end_date、delivery_regions、allocation_rights、price、currency、price_year、procurement_cap、adjustment_terms、exit_cost | 合同地域、期限、已承诺份额和分配权共同限制 S2 | P0 |
| grid_hourly：grid_region_id,time | generation_by_tech_MWh、imports/exports_MWh、grid_CFE_share、CFE_accounting_rule_id、spot_price、retail_price、currency、price_unit | 核对进口和属性归属；小时 CFE 比例与排放因子不能互相替代 | P0 |
| tariffs：tariff_id | site_id、fixed_charge、demand_charge、billing_period、taxes_or_fees、currency、price_year | 完整电费；统一说明共同固定成本是否进入收益比例分母 | P0 |
| storage：storage_id | site_id、technology、power_MW、energy_MWh、charge/discharge_efficiency、self_discharge_rate、degradation_rule、life_years、reserve_MWh、initial_SOC_MWh、initial_CFE_inventory_MWh | 功率/电量分列；存量与充电来源需追踪，避免把普通购电充入储能后算作无碳 | P0 |
| storage_costs：technology,year | power_capex_per_kW、energy_capex_per_kWh、fixed/variable_opex、replacement_cost、residual_value、currency、price_year、build_lead_time | 区分技术参数、案例报价和情景参数；不能用 LCOS 直接替代净收益 | P0（投资比较） |
| network：path_id | origin/destination_site、bandwidth_Gbps、latency_ms、transfer_fee_per_GB、energy_per_GB、model_ready、data_residency_rule、permission_evidence_id | 数据许可、时延及模型就绪共同约束分配/迁移 | P0（跨站） |
| policies：policy_id | baseline_dispatch、queue_rule、baseline_power_control、purchase_rule、storage_rule、supply_permissions、task_permission_evidence、cross_region_delivery_rule | 使 S0/D0 可重放；区分现有规则与新增优化权 | P0 |
| forecasts：issue_time,target_time,variable | forecast_value、actual_value、unit、available_at、forecast_version | 只使用决策时可见信息，两种理念共享信息条件 | P1；现实信息验证前 P0 |
| targets：site_id,stage_id | CFE_metric、annual_weighted_target、hourly_floor、stage_start/end、final_deadline | 年加权值与小时下限分列；严格终点为逐站逐有负荷小时 100% | P0 |
| thresholds：case_id | eligible_task_share、eligible_job_list_version、max_active_delay_h、receiving_headroom_rule、power/performance_range、restore/migration_cost_rule、evidence_type | 计算细节拟定份额0/25/50/75/100%、延后0/1/4/12/24h；为研究扫描非实测。固定嵌套合格任务名单，真实期限与授权仍约束每个值 | P0（阈值实验） |
| business_costs：cost_id | task_revenue、alternative_order_net_contribution、control_fee、transfer_fee、flexibility_compensation、payer、beneficiary、contract_period | 机会成本须有证据；经济成本与企业现金收益分开，防止电费/租金重复计入 | P0（完整净收益） |
| future_scenarios：future_id,year | compute_demand/workload_mix、GPU_efficiency/performance_path、control_cost_path、energy/storage_cost_path、facility_expansion_limit | 各组合共用同一未来情景；情景假设不得当作预测事实 | P1；路线比较前 P0 |
| asset_path：scenario_id,stage_id,asset_id | invest_date、commission_date、capacity、remaining_life、replacement_date、retirement_cost、contract_commitment | 是求解后的路线结果表，目前应为空；承接各情境自己的历史 | P1；路线比较前 P0 |

正式字典建议列：`table_name, field_name, meaning, data_type, unit, nullable, missing_reason, source_id, source_field, transformation, evidence_type, validation_rule, applicable_scenarios, status, reviewer`。不得在没有核验时填 `status=validated_for_use`。

## 3. 原方案所列公开基础与可支持范围

本表记录**方案列出的候选来源；实际取得情况以项目共享来源登记为准**。启动期间取得的公开样例须单独记录范围，不把“存在官方网址”或“小量样例已取得”当作全量下载、许可及研究适配完成。

| 来源（原方案入口） | 可作为哪些表的候选输入 | 不能补足的关键字段/限制 | 下一动作 |
| --- | --- | --- | --- |
| [Alibaba GPU v2020 官方说明](https://raw.githubusercontent.com/alibaba/clusterdata/master/cluster-trace-gpu-v2020/README.md) | jobs、baseline_events；秒级提交/启动/结束、资源请求、GPU 类型 | 无真实期限、地理、功率时序和经营数据；传感器多为生命周期均值 | 确认文件可获得性/许可，再做字段抽样和观察截尾记录 |
| [Alibaba GPU v2026 字段说明](https://raw.githubusercontent.com/alibaba/clusterdata/master/cluster-trace-gpu-v2026/docs/schema.md) | facility_capacity、工作负载类型/小时利用率；网络仅部分时间 | 相对第 0—184 天，不自带真实日历/站点/精确到达；优先级不是期限或授权 | 保留相对时间；若与天气合成，必须明示为情景对齐 |
| [Microsoft Philly 官方说明](https://raw.githubusercontent.com/msr-fiddle/philly-traces/master/README.md) | baseline_events、背景资源竞争、重试 | 虚拟集群不是地理站点；任务截尾、期限、功率需另补 | 检查事件/分钟粒度可连接性及观察边界 |
| [Zeus 公开字段](https://raw.githubusercontent.com/ml-energy/zeus/master/examples/research_reproducibility/zeus_nsdi23/trace/README.md)、[测量工具](https://ml.energy/zeus/measure/) | compute_profiles 中特定训练配置的时间/功率关联 | 配置汇总不等于本案例 GPU 和任务的实测；GPU 能耗不是设施能耗 | 列目标设备与任务的再校准需求 |
| [ERA5 小时气象](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview) | 风光/冷却模型外生气象输入 | 不能直接当作可认领 CFE、实际 PPA 出力或电价 | 先确认站点和年份，再确定变量/转换模型/许可 |
| [PNNL 技术评估](https://www.pnnl.gov/sites/default/files/media/file/ESGC%20Cost%20Performance%20Report%202022%20PNNL-33283.pdf)、[2024 核算说明](https://www.pnnl.gov/sites/default/files/media/file/ESGC_LCOS_Workbook_v2024_Documentation.pdf) | storage、storage_costs 的参考参数 | 特定地区/年份，不等同于案例报价；单一 LCOS 不能替代系统比较 | 记录币种、价格年、技术适配和转换方式 |
| NC 研究复现材料 | 仓库已有全年风光/活动代理、Azure请求、价格文件的元数据与归档路径 | 当前有证据目录，不等于当前工作副本具备可运行原始数据；代理量不等于设施负荷或真实业务 | 按[既有计算说明](../../data/metadata/existing-computations.md)恢复所需文件，核验哈希、标定方法与许可，再登记采用版本 |
| NCC 气候与需求归档 | 仓库已有多年气候、模拟IT负荷、学习成本和周样例说明 | 未来序列不是逐小时天气预报；模拟IT负荷不含PUE；快照不能证明全部最终气候组合齐备 | 按[归档清单](../../data/metadata/baidu-netdisk-archive-20261019.json)恢复并核验SSP标签、光伏版本、站点映射和连续时间范围 |

## 4. 需要业务数据或明确假设的缺口

公开运行轨迹不能单独识别本研究全部权限及净收益。以下当前均待提供或确认：真实期限、任务控制/迁移许可、真实站点及电网、模型和数据驻留限制、实际供能合同/属性归属、正常供能规程、初始资产及库存、完整费用和有依据的机会成本、阶段目标/期限、建设限制。

如果只能采用公开轨迹，需先写“公开轨迹驱动的假设案例”边界，单列全部外加参数和敏感性范围，并明确结果不代表原企业真实业务。该选择目前只是备选实施路径；本步取得的公开样例以共享登记为准，尚未具备全部运行输入，也未完成模型计算。
