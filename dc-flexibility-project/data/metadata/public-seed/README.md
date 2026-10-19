# 公开小样本元数据与本地恢复

本目录只含接收报告、来源/哈希清单和 CSV 结构检查结果。6 个 CSV、1 个原始压缩包、2 个 PDF 和 1 个许可证原件共 10 个文件保留在本地成果包 `cfe-two-directions-step1-20261019/05_public_seed/`，不随 Git 仓库分发。2026-10-19 入库准备已重新检查这 10 个本地文件的大小与 SHA-256；没有重新获取全量数据或执行模型。

- [接收报告](intake_report.md)：记录数、字段、缺失值与使用边界。
- [来源清单](manifest.json)：官方 URL、原接收时间、字节数、SHA-256、许可状态。
- [CSV 结构检查](csv_checks.json)：6 个 CSV 的列结构、缺失计数和候选键检查。

## 从本地成果包恢复

1. 在项目中创建已被忽略的 `data/raw/public-seed/` 目录。
2. 从本地成果包的 `05_public_seed/` 中复制 `raw/` 与 `references/` 两个子目录至该目录，保留文件名和字节。不要覆盖来源清单。
3. `manifest.json` 每条记录的 `path` 均相对这个恢复根目录。示例：`raw/alibaba_gpu_v2020/pai_machine_spec.csv` 应落到项目内 `data/raw/public-seed/raw/alibaba_gpu_v2020/pai_machine_spec.csv`。
4. 对每份文件核对字节数和 SHA-256；若不符，保留原件并登记差异，不能标为原版本已恢复。不要将校验失败解释成自动接受的新版本。
5. 在自己使用的数据来源台账中记录本次恢复日期、路径、校验结果和使用者；这不会改变本清单记录的原始接收日期。

## 从官方来源重新获取

如果本地成果包不可用，按 `manifest.json` 的 `source_url` 逐项获取。`pai_machine_spec.csv` 是压缩包内文件，按 `derived_from` 从已核验压缩包提取，不把压缩包 URL 下载内容直接保存成 CSV。其 CSV 无表头，字段名见 `csv_checks.json`，原件不添加表头。

GitHub 的 `master` 链接指向可变内容；重下后如果 SHA-256 不同，应登记一个新的来源版本，重新做结构检查，不能声称复现了本清单版本。记录成功获取不等于允许再分发；使用前分别复核 Alibaba、Zeus 与 PNNL 的适用条款。

这些小文件仅支持字段适配、GPU 测量口径与成本参考资料准备。它们没有真实设施表计、SLA、可认领 CFE 合同或本地成本参数，不能直接组成可求解的生产模型输入。网盘既有 NC/NCC 大数据恢复另见[准备状态](../step1-data-readiness.md)。
