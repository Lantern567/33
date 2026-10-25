import json
from pathlib import Path
from xml.sax.saxutils import escape

import fitz
import pandas as pd
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "results/compute-center-data-audit-20261022/coupled-power-weather-20261025-v4"
TEMP = PROJECT / ".codex-temp/coupled-power-weather-20261025-v4"
OLD = PROJECT / "results/compute-center-data-audit-20261022/equipment-scale-profiles-20261024/算力中心分类_小时至全年负荷与线性成本外推报告_20261024.pdf"
PDF = OUT / "CPU_GPU算力中心_IT散热与温湿度耦合负荷报告_20261025_v4.pdf"
D = json.loads((OUT / "coupled-model-manifest.json").read_text(encoding="utf-8"))
MODEL = D["cooling"]
A = pd.read_csv(OUT / "annual-load-summary.csv")
H = pd.read_csv(OUT / "hardware-scale-parameters.csv")
V = pd.read_csv(OUT / "cooling-holdout-validation.csv")
U = pd.read_csv(OUT / "power-mapping-sensitivity.csv")
OAK = "c3ba734448beea13"
WIDTH = A4[0] - 36*mm
LOCATIONS = {"35dd981fe96fa50c": "孟菲斯", "7a5cb7bae095e8c6": "博洛尼亚", OAK: "橡树岭", "cfa607ecb913aa41": "盖恩斯维尔", "e2e82e8e4a8b7f3d": "卡亚尼"}


def annual(profile, site=OAK, k=10, year=2025):
    return A.loc[A.profile.eq(profile) & A.site_id.eq(site) & A.reference_it_capacity_mw.eq(k) & A.year.eq(year)].iloc[0]


def hardware(profile, k):
    return H.loc[H.profile.eq(profile) & H.reference_it_capacity_mw.eq(k)].iloc[0]


def main():
    TEMP.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("YaHei", "C:/Windows/Fonts/msyh.ttc"))
    pdfmetrics.registerFont(TTFont("YaHeiBold", "C:/Windows/Fonts/msyhbd.ttc"))
    pdfmetrics.registerFontFamily("YaHei", normal="YaHei", bold="YaHeiBold", italic="YaHei", boldItalic="YaHeiBold")
    body = ParagraphStyle("Body", fontName="YaHei", fontSize=10.0, leading=15.6, wordWrap="CJK", spaceAfter=7)
    small = ParagraphStyle("Small", parent=body, fontSize=8.3, leading=12, textColor=colors.HexColor("#444444"), spaceAfter=5)
    heading = ParagraphStyle("Heading", parent=body, fontName="YaHeiBold", fontSize=14, leading=20, spaceAfter=10)
    sub = ParagraphStyle("Sub", parent=body, fontName="YaHeiBold", fontSize=11, leading=16, spaceBefore=5, spaceAfter=6)
    title = ParagraphStyle("Title", parent=body, fontName="YaHeiBold", fontSize=22, leading=31, spaceAfter=12)
    cell = ParagraphStyle("Cell", parent=body, fontSize=8.3, leading=12, spaceAfter=0)
    head = ParagraphStyle("Head", parent=cell, fontName="YaHeiBold")
    formula = ParagraphStyle("Formula", parent=body, leftIndent=10, leading=17)
    story = []

    def p(text, style=body):
        story.append(Paragraph(text, style))

    def h(text):
        p(text, sub)

    def page(text):
        story.append(PageBreak())
        p(text, heading)

    def table(rows, widths):
        result = Table([[Paragraph(str(value), head if i == 0 else cell) for value in row] for i, row in enumerate(rows)],
                       colWidths=[WIDTH*w for w in widths], hAlign="LEFT", repeatRows=1)
        result.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F3F4")),
            ("LINEABOVE", (0, 0), (-1, 0), .6, colors.HexColor("#333333")),
            ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#999999")),
            ("LINEBELOW", (0, 1), (-1, -1), .3, colors.HexColor("#D9DFE1")),
            ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(result)
        story.append(Spacer(1, 7))

    def fig(name, caption):
        path = OUT / f"{name}.png"
        with PILImage.open(path) as image:
            ratio = image.height/image.width
        story.append(Image(str(path), width=WIDTH, height=WIDTH*ratio))
        p(caption, small)

    p("CPU、GPU算力中心<br/>IT、散热与温湿度耦合负荷", title)
    p("1、10、100、500 MW参考规模 | 逐小时至全年 | 2026年10月25日", small)
    p("本报告将CPU与GPU资源记录、整机实测功率和逐小时气象连接，计算节点IT功率、设备散热需求、冷却相关用电与总电负荷。资源强度沿用已有记录；冷却响应由ESIF同时间的功率和现场气温、湿度标定。")
    table([
        ["计算内容", "输入与参数", "覆盖范围"],
        ["CPU参考中心", "Bitbrains资源路径＋双路EPYC 7763整机11档实测功率", "fast为主样本；rnd为同类型敏感性"],
        ["GPU参考中心", "Alibaba整体申请路径＋8×H100 HGX整机实测点", "统一GPU类型；使用申请份额迁移代理"],
        ["冷却与配套", "ESIF分项功率及现场气温、相对湿度", f"{MODEL['calibration_hours']:,}个配对小时；最后672小时留出检验"],
        ["天气与规模", "五地点2023—2025年ERA5天气；四档参考IT规模", "120组主结果＋60组CPU样本敏感性"],
    ], [.21, .45, .34])
    h("规模和结果性质")
    p("四档MW表示按实测高负载节点功率配置的参考满载IT容量。CPU采用546 W/节点，GPU采用8.43 kW/节点，整机数量向下取整。GPU论文同时报告10.2 kW厂家额定参照；工程电源与冷却设计仍需依据额定规格、设计天气和冗余标准。")
    p("资源使用率或申请份额映射到另一配置的整机基准负载，以及将ESIF冷却关系迁移到目标节点，均属于明确的转移假设。结果为参考设施情境，未解释为五个真实场站的历史用电。节点内CPU、内存和风扇随整机计入；外部共享网络和存储功率仍待补充。")
    h("温湿度模型的验证范围")
    p(f"ESIF最后四周的冷却功率RMSE由仅考虑IT热负荷时的{V.iloc[0].rmse_kw:.1f} kW降至{V.iloc[1].rmse_kw:.1f} kW；后者约占留出期平均冷却功率的{V.iloc[1].rmse_percent_mean:.1f}%。湿热地点存在较多超出露点标定范围的小时，输出逐时保留外推标记。")
    p("第1章保留原数据来源页，第2至10章说明耦合计算、设备参数、验证和结果。全年小时数分别为8760、8784、8760；全部时序输出附来源与计算脚本。", small)

    page("2　模型结构、基本参数与实测依据")
    fig("01-measured-node-power-mapping", "图1　CPU为SPECpower相对基准负载与平均整机功率；GPU为论文中的平均GPU利用率与整机功率中位数。连线为相邻测量点间的分段线性插值。[6,7]")
    table([
        ["环节", "主参数或操作", "参数性质"],
        ["资源曲线", "CPU使用MHz/容量MHz；GPU申请量/6,742张库存", "原资源记录计算，均值保持重放结果"],
        ["节点功率", "CPU 120—546 W；GPU 1.86—8.43 kW", "指定配置与实验条件下的实测参考"],
        ["设备规模", "节点数N=floor(K×10^6/参考满载瓦特数)", "相同节点复制；K取1、10、100、500 MW"],
        ["设备散热", "Q_IT(t)≈P_IT(t)", "小时能量平衡近似，忽略蓄热和建筑得热"],
        ["冷却响应", "IT热负荷、室外气温、由相对湿度求得的露点", "ESIF同时间实测分项拟合"],
        ["总电负荷", "IT＋室外冷却＋HVAC＋泵＋其他配套", "按电功率分项相加，PUE作为输出"],
    ], [.20, .49, .31])
    p("研究中的CPU、GPU是两种计算节点参考配置。冷却侧统一采用ESIF配置的实测响应情境，以便观察相同技术关系在不同天气中的变化；当前数据未识别目标节点与ESIF供水温度、液冷接口和热回收条件的工程兼容性。")
    p("分档整机测量为功率函数提供依据；跨数据集的资源比例到负载映射另列为假设，尚无同设备资源—瓦特联合观测验证。", small)

    page("3　CPU：资源路径、节点功率与散热")
    fig("02-cpu_fast-hourly-components", "图2　CPU主样本在10 MW参考满载IT规模、橡树岭2025年天气下的第一周分项电功率。资源路径来自Bitbrains重放，气象按UTC小时对应。")
    table([
        ["参考节点参数", "采用值", "来源与范围"],
        ["配置", "2×EPYC 7763；128物理核心；256 GB内存", "HPE DL385 Gen10 Plus公布测试配置[6]"],
        ["实测功率", "空闲120 W；10%负载200 W；20%为232 W", "SPECpower基准负载；节点整机电源输入"],
        ["实测功率", "50%为336 W；最高测试负载546 W", "完整11档功率表随数据交付"],
        ["10 MW节点数量", f"{int(hardware('cpu_fast',10).node_count):,}台；{int(hardware('cpu_fast',10).physical_cpu_cores):,}核心", "参考容量9.99999 MW；核心使用量为代理"],
    ], [.23, .40, .37])
    p("u_C(t)=观测VM使用MHz/同小时观测容量MHz；<br/>P_IT,C(t)=N_C×p_SPEC(u_C(t))/10^6；Q_IT,C(t)≈P_IT,C(t)。", formula)
    p(f"全年重放的平均资源比例：fast为{annual('cpu_fast').mean_resource_fraction:.2%}，rnd为{annual('cpu_rnd').mean_resource_fraction:.2%}。10 MW主样本平均节点IT功率为{annual('cpu_fast').mean_it_mw:.3f} MW；该值由分段功率函数逐时计算。")
    p("VM使用率被用作SPEC相对基准负载的代理；SPEC负载表示Java基准吞吐水平，两者的对应关系需要目标服务器验证。实测节点关闭了Core Performance Boost并采用特定电源管理设置，不能据此覆盖所有CPU服务器。源样本观测VM容量变化也继续保留。[2,6]")
    p("所有节点在主计算中持续通电，每个小时采用相同资源强度。满载/空闲节点混合的另一种负载分布单列敏感性，见第10章。", small)

    page("4　GPU：整体申请路径与整机功率")
    fig("02-gpu-hourly-components", "图3　GPU参考中心在10 MW参考满载IT规模、橡树岭2025年天气下的第一周电功率。宿主CPU、内存、机内互连和风扇随HGX整机功率计入。")
    table([
        ["实测观测档位", "GPU平均利用率", "整机功率中位数"],
        ["空闲节点", "空闲状态", "1.86 kW"],
        ["论文观测点1", "36%", "4.68 kW"],
        ["论文观测点2", "77%", "6.26 kW"],
        ["论文观测点3", "93%", "7.92 kW"],
        ["GPU与CPU联合压力负载", "100% GPU利用率", "8.43 kW"],
    ], [.43, .27, .30])
    p("u_G(t)=已纳入任务的GPU申请等效数量/6,742；<br/>P_IT,G(t)=N_G×p_HGX(u_G(t))/10^6；Q_IT,G(t)≈P_IT,G(t)。", formula)
    p(f"本次全年申请比例均值为{annual('gpu').mean_resource_fraction:.2%}。10 MW参考规模安装{int(hardware('gpu',10).node_count):,}台8卡节点，共{int(hardware('gpu',10).gpu_count):,}张H100，平均节点IT功率为{annual('gpu').mean_it_mw:.3f} MW。申请路径未分解任务类型。")
    p("Alibaba分母为多型号库存快照，申请份额也未表示实际GPU利用率。将其比例映射至HGX观测曲线，是参考资源强度迁移，未建立旧GPU与H100的吞吐等价。功率观测点来自不同工作负载，插值只用于本情境。[1,7]")
    p("论文节点采用8×H100 80 GB、EPYC 9354宿主CPU及1.5 TB内存；RDHx另路供电。节点用电已含机内风扇，外部冷却电耗单列；对ESIF冷却关系的迁移另有工程匹配限制。", small)

    page("5　IT散热与温湿度响应的连接")
    fig("03-calibrated-weather-response", "图4　10 MW参考容量下，固定观测中位IT负荷与湿度或气温得到的冷却响应。左图虚线部分超出露点单变量标定范围；曲线为模型条件响应。")
    p("设备散热需求Q_IT按节点IT电功率近似，单位MW热。其年度累计为MWh热；电费只按IT与冷却等电功率计入。室外实际排热还涉及冷却设备耗电转热与热回收，本报告未单独重建这一热回收过程。[8]")
    p("室外相对湿度与气温经PsychroLib转换为露点T_d，以表达空气含湿状况。冷却关系直接使用气温T、露点T_d和IT负荷，避免把未测量的COP、供水温度或自然冷却切换点写成实测参数。[9]")
    p("q=P_IT/C；P_j=C×Σθ_jm φ_m(q,T,T_d)，θ_jm≥0。", formula)
    table([
        ["响应项", "处理方式"],
        ["容量与热负荷", "常数项、q及q²；分别允许固定开销、随热量变化和部分负荷曲率"],
        ["暖天气与湿度", "q×max(T−温度节点,0)及q×max(T_d−露点节点,0)"],
        ["低温附属负荷", "max(低温节点−T,0)，允许室外伴热和持续设备开销"],
        ["分项与系数", "室外冷却、HVAC、泵、其他分别非负最小二乘拟合；节点取训练数据分位数"],
    ], [.25, .75])
    p("C为容量参考尺度，标定时取ESIF合格IT小时峰值2.861 MW；外推时使用实际安装参考容量。冷却相关功率为室外冷却、HVAC与泵之和，其他配套另列。模型刻画原配置的经验响应，未求解具体制冷机和冷却塔的工程性能。", small)

    page("6　气象输入与逐小时到全年累计")
    fig("04-climate-and-monthly-cooling", "图5　五地点2025年月均气温及GPU参考中心的月冷却电量。各地点使用相同IT路径和设备规模；地点名称仅标识天气情境。")
    table([
        ["参数", "当前处理"],
        ["地点", "芬兰卡亚尼、美国孟菲斯、橡树岭、盖恩斯维尔、意大利博洛尼亚"],
        ["目标气象", "已有ERA5资料的逐小时气温、相对湿度；露点由同小时两者计算"],
        ["标定气象", "ESIF现场气象站；华氏气温转换为摄氏，与功率按同一源时钟配对"],
        ["时间轴", "目标天气采用连续UTC；2023/2025各8760小时，2024年8784小时"],
        ["资源年路径", "连续观测周原值重放；普通年沿用既有8760小时，闰年延长末尾源周24小时"],
    ], [.23, .77])
    p("不同地点在相同年份使用同一资源路径，因此节点IT功率相同，冷却和附属功率随气象变化。2023—2025年也使用同一相对路径；这一设置用于比较天气，不恢复真实任务历年的扩容、节假日或故障。")
    p("E_j,year=ΣP_j(t)×1小时；E_j,month按同一UTC日历分组。<br/>全年PUE=ΣP_total(t)/ΣP_IT(t)。", formula)
    p("室外气温与设备入口温度分别处理。节点功率曲线沿用实验环境条件，假定冷却维持相应入口环境；当前未加入芯片漏电、机内风扇随入口温度变化或高温降频的反馈。", small)

    page("7　冷却标定误差与外推范围")
    fig("05-cooling-holdout-validation", "图6　ESIF最后四周672小时的留出检验。联合模型仅用此前4775小时拟合；图内保留观测波动与模型偏差，未将留出数据加入该次预测拟合。")
    table([
        ["留出模型", "MAE，kW", "RMSE，kW", "RMSE/观测均值", "R²"],
        *[["仅IT热负荷" if row.model == "heat_only" else "IT＋温湿度", f"{row.mae_kw:.2f}", f"{row.rmse_kw:.2f}", f"{row.rmse_percent_mean:.2f}%", f"{row.r_squared:.3f}"] for row in V.itertuples()],
    ], [.30, .17, .17, .22, .14])
    table([
        ["天气地点，2025年", "超出气象单变量范围的小时", "占全年比例"],
        *[[label, f"{int(annual('gpu',site).outside_calibration_weather_hours):,}", f"{annual('gpu',site).outside_calibration_weather_hours/8760:.1%}"] for site, label in LOCATIONS.items()],
    ], [.34, .40, .26])
    p(f"最终计算在检验后用全部{MODEL['calibration_hours']:,}个配对小时重新标定。气温范围为−19.31至38.13°C，露点为−29.42至17.68°C，IT/参考容量为0.2315至1。GPU路径另有58小时低于IT负荷标定范围。")
    p("分项和模型的留出误差不等同于目标地点总负荷误差。超出范围的小时保留数值并逐时标记，不能由此保证预测精度；单变量范围内的全部联合条件也未逐一验证。输出的残差范围来自留出误差分位数，未表示目标地点的置信区间。", small)

    page("8　1、10、100、500 MW的设备与负荷规模")
    table([
        ["参考IT规模K", "CPU节点 / 物理核心", "GPU节点 / H100数量"],
        *[[f"{k} MW", f"{int(hardware('cpu_fast',k).node_count):,} / {int(hardware('cpu_fast',k).physical_cpu_cores):,}",
           f"{int(hardware('gpu',k).node_count):,} / {int(hardware('gpu',k).gpu_count):,}"] for k in [1,10,100,500]],
    ], [.20, .40, .40])
    p("规模以整机实测高负载点为统一参照，CPU为546 W，GPU为8.43 kW。K确定设备数量后，再由每小时资源强度计算运行功率；冷却依据该小时散热、当地温湿度和安装参考容量共同计算。")
    table([
        ["橡树岭2025年", "CPU总电量，GWh", "GPU总电量，GWh", "最高小时总功率：CPU / GPU，MW"],
        *[[f"{k} MW参考规模", f"{annual('cpu_fast',k=k).annual_facility_mwh/1000:,.3f}", f"{annual('gpu',k=k).annual_facility_mwh/1000:,.3f}",
           f"{annual('cpu_fast',k=k).max_facility_mw:.3f} / {annual('gpu',k=k).max_facility_mw:.3f}"] for k in [1,10,100,500]],
    ], [.23, .23, .23, .31])
    h("参考运行尺度与工程额定容量")
    p("500 MW GPU参考规模安装59,311台节点、474,488张H100。若按论文所列10.2 kW厂家额定参照核算，这些节点对应约604.97 MW；再加外部冷却和其他系统，工程供电需求还会改变。CPU节点的800 W电源额定也与546 W基准实测值分别记录。[6,7]")
    p("相同模块复制下，节点、散热需求和配套用电随规模近似线性扩大，整机取整产生小幅差异。500 MW结果未验证接网、冷却容量、高温降额、冗余设计和超大集群互连能力。")
    p("设备规模扩大后采用相同资源比例，表示同步复制的参考中心。任务聚合可能改变波动与峰值，当前数据未识别不同模块之间的实际相关性。", small)

    page("9　全年需求累计与线性成本系数")
    fig("06-cumulative-energy-five-climates", "图7　CPU与GPU在10 MW参考规模下的2025年累计电量。CPU采用fast主样本。两类资源路径与设备不同，电量差异不用于同等计算服务的能效排名。")
    p("每个小时记录IT电功率、设备散热需求、三类冷却相关功率、其他配套、总功率、PUE及累计MWh。CPU另存核心使用代理，GPU另存申请等效数量；这些资源量按各自单位累计，吞吐等价仍需任务标定。")
    table([
        ["成本或累计项", "计算边界"],
        ["计算节点投资", "CPU节点数×同配置单价；GPU节点数×同配置整机单价"],
        ["配套设施投资", "保持ESIF参考配置重复时可按容量倍数给出系数；目标工程设计和报价仍待补充"],
        ["逐小时电费", "Σ总电功率(MW)×1小时×电价(货币/MWh)；需量费按计费粒度另计"],
        ["年度设备散热", "Σ设备散热需求(MW热)×1小时；与IT累计电量数值近似相同"],
    ], [.25, .75])
    p("hardware-scale-parameters.csv给出整机数量、参考满载容量、未分配预算、GPU与CPU核心数量，可直接作为设备报价系数。GPU整机报价已包含宿主和机内组件时，组件价格按同一范围核算。")
    p("绝对价格保持空值。外部共享交换网络、存储、土地、建筑及目标冷却系统工程成本需相应配置与报价；现有小时曲线也未证明大规模单位成本保持不变。", small)

    page("10　主结果、敏感性与可解释范围")
    table([
        ["2025年10 MW参考规模", "总电量，GWh", "冷却电量，GWh", "能量加权PUE"],
        *[[f"CPU｜{label}", f"{annual('cpu_fast',site).annual_facility_mwh/1000:.3f}", f"{annual('cpu_fast',site).annual_cooling_mwh/1000:.3f}", f"{annual('cpu_fast',site).energy_weighted_pue:.3f}"] for site,label in LOCATIONS.items()],
        *[[f"GPU｜{label}", f"{annual('gpu',site).annual_facility_mwh/1000:.3f}", f"{annual('gpu',site).annual_cooling_mwh/1000:.3f}", f"{annual('gpu',site).energy_weighted_pue:.3f}"] for site,label in LOCATIONS.items()],
    ], [.37, .21, .21, .21])
    p("在统一参考配置和需求路径下，各地点IT电量保持相同，年电量差异来自配套系统对天气的响应。较热和较湿条件提高模型中的暖天气冷却项；寒冷时室外伴热及固定开销也可能增加，因此全年关系并非单调随气温降低。")
    h("资源到功率映射的敏感性")
    for profile, label in [("cpu_fast", "CPU fast"), ("cpu_rnd", "CPU rnd"), ("gpu", "GPU")]:
        row = U.loc[U.profile.eq(profile) & U.site_id.eq(OAK) & U.comparison.str.startswith("同资源份额")].iloc[0]
        change = row.alternative_facility_mwh/row.main_facility_mwh-1
        p(f"橡树岭10 MW情境：{label}采用相同平均资源份额，在“各节点同强度”与“部分满载、其余空闲”的分布之间变化时，后者年电量变化为{change:+.1%}。两者均使用相同实测端点，说明节点负载分布会影响电量。", small)
    p("CPU rnd是同一CPU类型的样本敏感性，共60组。GPU的7.97与8.43 kW满负载端点敏感性也已计算；当前资源路径未进入93%以上区间，因此更换该端点对本次路径电量没有影响。", small)
    p("冷却留出检验支持ESIF参考配置内的条件响应；跨设备资源映射、湿热气候、热回收运行及目标冷却接口尚未验证。PUE和地区差异均为该组条件下的模型结果，不能作为对应真实场站的测量结论。", small)

    page("10（续）　数据、来源与复现")
    table([
        ["交付文件", "用途"],
        ["hourly/资源样本/地点/年份/规模.parquet", "180组完整小时表；2025年10 MW另附15份CSV"],
        ["annual-load-summary.csv；monthly-load-summary.csv", "年度与月度分项电量、峰值、PUE与外推小时数"],
        ["cpu/gpu-measured-power-anchors.csv；hardware-scale-parameters.csv", "实测节点功率点和四档设备规模系数"],
        ["esif-paired-power-weather-calibration-hours；cooling-calibration.json", "配对标定小时、模型系数、节点与适用范围"],
        ["cooling-holdout-validation；power-mapping-sensitivity.csv", "时间留出误差及资源分布、GPU功率端点敏感性"],
        ["coupled-model-manifest.json；verification-results.json", "输入SHA-256、假设、版本与计算验证"],
    ], [.53, .47])
    references = [
        ("[1] Alibaba Cluster Trace GPU v2020：任务申请、实例及机器规格。", "https://github.com/alibaba/clusterdata/tree/master/cluster-trace-gpu-v2020"),
        ("[2] Grid Workloads Archive，Bitbrains：VM CPU使用与容量记录。", "https://atlarge-research.com/gwa-traces/gwa_t_12_fastStorage.zip"),
        ("[3] NLR HPC Facility PUE Data，DOI 10.7799/3015212：ESIF功率与现场天气。", "https://data.nlr.gov/submissions/300"),
        ("[4] Zeus NSDI23：单GPU实验；保留原数据层标定用途。", "https://github.com/ml-energy/zeus/tree/master/examples/research_reproducibility/zeus_nsdi23/trace"),
        ("[5] Frontier HPC & Facility Data，v4，DOI 10.6084/m9.figshare.24391240.v4：独立系统参照。", "https://figshare.com/articles/dataset/Dataset_of_Frontier_supercomputer/24391240"),
        ("[6] HPE DL385 Gen10 Plus，SPECpower_ssj2008，2021-03-15；测试2021-02-18。", "https://ftp.spec.org/power_ssj2008/results/res2021q1/power_ssj2008-20210221-01063.html"),
        ("[7] Latif等，Empirical Measurements of AI Training Power Demand on a GPU-Accelerated Node，2024，Table I。", "https://arxiv.org/html/2412.08602v1"),
        ("[8] ASHRAE Handbook 2023，Chapter 20：IT电热、冷却与气象边界。", "https://handbook.ashrae.org/Handbooks/A23/SI/A23_Ch20/a23_ch20_si.aspx"),
        ("[9] PsychroLib 2.5.0：由气温与相对湿度计算露点，采用SI单位。", "https://github.com/psychrometrics/psychrolib"),
        ("[10] Open-Meteo Historical Weather API，ERA5：已有2023—2025年地点天气归档。", "https://open-meteo.com/en/docs/historical-weather-api"),
    ]
    for text, url in references:
        p(f'{escape(text)} <link href="{escape(url)}" color="#245B76">来源</link>', small)
    p("复现顺序：couple_compute_power_weather.py生成标定与180组结果；plot_coupled_power_weather.py生成图件；build_coupled_power_weather_report.py生成报告；verify_coupled_power_weather.py核对来源、规模、逐时守恒及月年累计。脚本均位于analysis/，输入路径和校验值见清单。", small)

    def decorations(canvas, doc):
        canvas.saveState()
        canvas.setFont("YaHei", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(18*mm, A4[1]-12*mm, "数据中心研究 | IT、散热与气象耦合负荷")
        number = doc.page if doc.page == 1 else doc.page+1
        canvas.drawRightString(A4[0]-18*mm, 11*mm, f"2026-10-25  ·  {number}")
        canvas.restoreState()

    sections = TEMP / "report-sections.pdf"
    doc = SimpleDocTemplate(str(sections), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=20*mm, bottomMargin=18*mm,
                            title="CPU、GPU算力中心IT散热与温湿度耦合负荷报告", author="数据中心研究工作区")
    doc.build(story, onFirstPage=decorations, onLaterPages=decorations)
    with fitz.open(sections) as report, fitz.open(OLD) as original:
        assert len(report) == 11, f"正文分页异常：{len(report)}"
        report.insert_pdf(original, from_page=1, to_page=1, start_at=1)
        report.set_metadata({"title": "CPU、GPU算力中心IT散热与温湿度耦合负荷报告", "author": "数据中心研究工作区"})
        report.save(PDF, garbage=4, deflate=True)
    with fitz.open(PDF) as report:
        assert len(report) == 12
        (OUT / "报告可检索文本.txt").write_text("\n\n".join(page.get_text() for page in report), encoding="utf-8")
    pd.DataFrame(MODEL["coefficients"], index=MODEL["feature_names"], columns=["outdoor_cooling", "hvac", "pump", "other"]).to_csv(OUT / "cooling-fitted-coefficients.csv", encoding="utf-8-sig", index_label="feature")
    print(json.dumps({"pdf": str(PDF), "pages": 12}, ensure_ascii=False))


if __name__ == "__main__":
    main()
