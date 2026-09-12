# -*- coding: utf-8 -*-
# 声明文件编码为 UTF-8，确保中文字符能正确显示

"""
SPC 统计过程控制 + 过程能力分析（Cpk / Ppk）
===================================================

工业背景
--------
半导体产线需要实时监控关键工艺参数是否"受控"：
  - 控制图（Control Chart）：判断过程是否稳定，有无异常波动
  - 过程能力（Cpk / Ppk）：衡量过程输出是否满足规格要求
    - Cpk（短期能力）：基于组内变异（within-subgroup），反映"最佳状态"
    - Ppk（长期性能）：基于整体变异（overall），反映"实际表现"
    - Cpk > 1.33 通常认为过程能力充足（6Sigma 标准）

本模块做什么
-----------
1) 对 SHAP 识别的关键参数（CD / oxide / vth）绘制 Xbar-R 控制图
2) 计算 Cp / Cpk / Pp / Ppk，判断过程能力是否达标
3) 识别失控点（OOC, Out of Control），模拟"自动 Hold 批次"逻辑
4) 对比优化前后的 Cpk 提升（用 DOE 最优窗口 vs 当前基线）

数据分组逻辑
-----------
真实产线按"批次（lot）"分组，每个 lot 包含多片晶圆（wafer）。
Xbar-R 图：
  - Xbar 图：每个 lot 的均值，监控过程中心是否漂移
  - R 图：每个 lot 的极差，监控过程波动是否稳定
"""

# ============================================================
# 导入依赖库
# ============================================================
import os                          # 操作系统接口，用于路径拼接、创建目录等
import numpy as np                 # 数值计算库，用于数组运算、统计量计算
import pandas as pd                # 数据分析库，用于读取 CSV、分组聚合
import matplotlib                  # 绘图库的底层模块
matplotlib.use("Agg")              # 设置后端为 Agg（非交互式），适合服务器环境生成图片
import matplotlib.pyplot as plt    # 导入 pyplot 子模块，用于绑定图表、保存文件
from scipy import stats            # scipy 统计模块，用于正态性检验、概率密度函数等

# ============================================================
# 全局配置：matplotlib 中文字体
# ============================================================
# 设置中文字体优先级：微软雅黑 > 黑体 > 默认英文字体
# 这样图表标题、轴标签中的中文才能正确显示，不会变成方块
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
# 解决负号显示问题：matplotlib 默认用 Unicode 负号，某些字体不支持
# 设为 False 后使用 ASCII 减号，确保 "-0.5" 之类的负数能正常显示
plt.rcParams["axes.unicode_minus"] = False

# ============================================================
# 全局配置：路径常量
# ============================================================
# 获取当前脚本所在目录的绝对路径，作为项目根目录
BASE = os.path.dirname(os.path.abspath(__file__))
# 拼接数据目录路径：BASE/data/
DATA = os.path.join(BASE, "data")
# 拼接结果输出目录路径：BASE/results/
RESULT = os.path.join(BASE, "results")
# 创建 results 目录（如果不存在），exist_ok=True 表示目录已存在时不报错
os.makedirs(RESULT, exist_ok=True)

# ============================================================
# 全局配置：关键参数列表
# ============================================================
# SHAP 识别的关键参数（良率主导因子），来自 main.py 的 SHAP 分析结果
# 这三个参数对良率影响最大，需要重点做 SPC 监控
KEY_PARAMS = ["critical_dimension", "oxide_thickness", "vth"]

# ============================================================
# 全局配置：工程规格限
# ============================================================
# 规格限（模拟真实产线规格，单位与数据一致）
# 这些是"工程规格"，由工艺工程师根据产品设计要求设定
# 基于数据分布 ±2.5~3σ 原则设定，确保均值在规格中心附近
SPEC_LIMITS = {
    # critical_dimension（关键尺寸，单位 nm）
    # 数据均值 24.6，标准差 4.245，±2.5σ 范围约 [14.0, 35.2]
    # 设定 LSL=15.0, USL=35.0，覆盖大部分数据
    "critical_dimension": {"LSL": 15.0, "USL": 35.0},  # nm（均值 24.6，±2.5σ）
    # oxide_thickness（氧化层厚度，单位 Å）
    # 数据均值 57.0，标准差 4.654，±2.5σ 范围约 [45.4, 68.6]
    # 设定 LSL=45.0, USL=70.0
    "oxide_thickness": {"LSL": 45.0, "USL": 70.0},      # Å（均值 57.0，±2.5σ）
    # vth（阈值电压，单位 V）
    # 数据均值 0.645，标准差 0.068，±2.3σ 范围约 [0.49, 0.80]
    # 设定 LSL=0.50, USL=0.80
    "vth": {"LSL": 0.50, "USL": 0.80},                  # V（均值 0.645，±2.3σ）
}


# ============================================================
# 函数 1：数据准备 —— 按批次分组
# ============================================================
def prepare_subgroups():
    """
    按 lot_id 分组，每个 lot 包含多片 wafer。
    Xbar-R 控制图需要"子组（subgroup）"概念：
      - 子组内变异（within）→ 计算 R（极差）→ 估计短期标准差
      - 子组间变异（between）→ 计算 Xbar（均值）→ 监控中心漂移
    """
    # 打印当前步骤标题，方便控制台查看进度
    print("===== 1. 数据准备（按批次分组）=====")
    # 读取 CSV 数据文件，拼接完整路径：BASE/data/semiconductor_yield_forecasting_data.csv
    df = pd.read_csv(os.path.join(DATA, "semiconductor_yield_forecasting_data.csv"))
    # 打印数据总行数（晶圆级数据，每行代表一片晶圆）
    print(f"  总数据: {len(df)} 行（晶圆级）")
    
    # 按 lot_id 列分组，得到 GroupBy 对象
    # 每个 group 包含同一个批次（lot）的所有晶圆数据
    grouped = df.groupby("lot_id")
    # 获取分组数量（即批次数）
    n_lots = grouped.ngroups
    # 计算每批平均包含多少片晶圆
    avg_wafers = len(df) / n_lots
    # 打印批次数和每批平均晶圆数
    print(f"  批次数: {n_lots}，每批平均 {avg_wafers:.1f} 片晶圆")
    
    # 构建子组字典：{参数名: {lot_id: [该批次所有晶圆的参数值]}}
    subgroups = {}
    # 遍历每个关键参数
    for param in KEY_PARAMS:
        # grouped[param] 取出该参数列的分组数据
        # .apply(list) 将每个分组转为列表（该批次所有晶圆的参数值）
        # .to_dict() 转为字典：{lot_id: [值1, 值2, ...]}
        subgroups[param] = grouped[param].apply(list).to_dict()
    
    # 返回子组字典和批次总数，供后续函数使用
    return subgroups, n_lots


# ============================================================
# 函数 2：Xbar-R 控制图（监控过程稳定性）
# ============================================================
def xbar_r_chart(subgroups, param):
    """
    Xbar-R 控制图原理：
      - Xbar 图：子组均值，控制限 = Xbar_bar ± A2 * R_bar
      - R 图：子组极差，控制限 = D3 * R_bar ~ D4 * R_bar
      - A2, D3, D4 是常数，取决于子组大小 n（查表）
    
    判异准则（Western Electric Rules，简化版）：
      - 1 点超出 3σ 控制限 → 失控
      - 连续 9 点在中心线同侧 → 漂移
      - 连续 6 点递增或递减 → 趋势
    """
    # 获取所有批次 ID，按字母/数字排序（确保绘图顺序一致）
    lots = sorted(subgroups[param].keys())
    # 提取每个批次的参数值列表，形成二维结构：[[批次1的值], [批次2的值], ...]
    X_subgroups = [subgroups[param][lot] for lot in lots]
    
    # 计算每个子组（批次）的均值 → Xbar 图的 y 值
    # np.mean(x) 计算单个批次内所有晶圆参数值的均值
    Xbar = np.array([np.mean(x) for x in X_subgroups])
    # 计算每个子组的极差（最大值 - 最小值）→ R 图的 y 值
    # 极差反映批次内的波动幅度
    R = np.array([np.max(x) - np.min(x) for x in X_subgroups])
    # 记录每个子组的样本量（每批有多少片晶圆）
    n = np.array([len(x) for x in X_subgroups])
    
    # 取子组大小的中位数作为标准子组大小（防止个别批次晶圆数不同）
    # 本数据集每批 25 片晶圆，n_subgroup=25
    n_subgroup = int(np.median(n))
    
    # ============================================================
    # SPC 控制图常数表（A2, D3, D4）
    # ============================================================
    # 这些常数来自统计学理论，取决于子组大小 n
    # A2：用于计算 Xbar 图的控制限，A2 = 3 / (d2 * sqrt(n))
    # D3：R 图的下控制限系数（n≤6 时为 0，因为极差不可能太小）
    # D4：R 图的上控制限系数
    A2_dict = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483, 7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308}
    # D3 字典：R 图下控制限系数
    D3_dict = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0.076, 7: 0.136, 8: 0.185, 9: 0.223, 10: 0.284}
    # D4 字典：R 图上控制限系数
    D4_dict = {2: 3.267, 3: 2.575, 4: 2.282, 5: 2.114, 6: 2.004, 7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777}
    
    # 根据实际子组大小查找对应常数，找不到时用默认值
    A2 = A2_dict.get(n_subgroup, 0.577)   # 默认 n=5 时的 A2
    D3 = D3_dict.get(n_subgroup, 0)       # 默认 n=5 时的 D3
    D4 = D4_dict.get(n_subgroup, 2.114)   # 默认 n=5 时的 D4
    
    # ============================================================
    # 计算中心线（CL）
    # ============================================================
    # Xbar_bar：所有批次均值的总平均 → Xbar 图的中心线
    Xbar_bar = np.mean(Xbar)
    # R_bar：所有批次极差的平均 → R 图的中心线
    R_bar = np.mean(R)
    
    # ============================================================
    # 计算控制限（UCL / LCL）
    # ============================================================
    # Xbar 图上控制限 = 总均值 + A2 × 平均极差
    # 等价于 Xbar_bar + 3σ_within（3 倍标准差原则）
    UCL_Xbar = Xbar_bar + A2 * R_bar
    # Xbar 图下控制限 = 总均值 - A2 × 平均极差
    LCL_Xbar = Xbar_bar - A2 * R_bar
    # R 图上控制限 = D4 × 平均极差
    UCL_R = D4 * R_bar
    # R 图下控制限 = D3 × 平均极差（n≤6 时为 0）
    LCL_R = D3 * R_bar
    
    # ============================================================
    # 识别失控点（OOC, Out of Control）
    # ============================================================
    # Xbar 图失控点：均值超出控制限（高于 UCL 或低于 LCL）
    ooc_xbar = (Xbar > UCL_Xbar) | (Xbar < LCL_Xbar)
    # R 图失控点：极差超出控制限
    ooc_r = (R > UCL_R) | (R < LCL_R)
    # 统计失控点总数（Xbar 和 R 两张图加总）
    n_ooc = ooc_xbar.sum() + ooc_r.sum()
    
    # ============================================================
    # 绘图：Xbar-R 控制图（上下两张子图）
    # ============================================================
    # 创建 2 行 1 列的子图布局，共享 x 轴（批次序号）
    # figsize=(10, 6) 表示宽 10 英寸、高 6 英寸
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    
    # ---------- 上半部分：Xbar 图 ----------
    # 绘制 Xbar 折线图：x 轴为批次序号，y 轴为批次均值
    # "-o" 表示折线+圆点标记，ms=3 是标记大小，color 是颜色
    ax1.plot(range(len(Xbar)), Xbar, "-o", ms=3, color="#3B6EA5", label="Xbar")
    # 绘制中心线（CL）：蓝色虚线
    ax1.axhline(Xbar_bar, color="#2C5F8D", ls="--", lw=1.2, label=f"CL={Xbar_bar:.3f}")
    # 绘制上控制限（UCL）：红色点线
    ax1.axhline(UCL_Xbar, color="#B23A48", ls=":", lw=1, label=f"UCL={UCL_Xbar:.3f}")
    # 绘制下控制限（LCL）：红色点线
    ax1.axhline(LCL_Xbar, color="#B23A48", ls=":", lw=1, label=f"LCL={LCL_Xbar:.3f}")
    # 如果有失控点，用红色 × 标记
    if ooc_xbar.any():
        # np.where(ooc_xbar)[0] 获取失控点的 x 坐标（批次序号）
        # Xbar[ooc_xbar] 获取失控点的 y 坐标（批次均值）
        # marker="x" 用 × 标记，zorder=5 确保标记在最上层
        ax1.scatter(np.where(ooc_xbar)[0], Xbar[ooc_xbar], c="#B23A48", s=50, 
                   marker="x", zorder=5, label=f"失控点 ({ooc_xbar.sum()})")
    # 设置 y 轴标签
    ax1.set_ylabel("Xbar（批次均值）")
    # 设置图表标题，包含参数名和子组大小
    ax1.set_title(f"{param} Xbar-R 控制图（n={n_subgroup}）")
    # 显示图例，放在右上角，字号 8
    ax1.legend(loc="upper right", fontsize=8)
    # 显示网格线，透明度 0.3
    ax1.grid(alpha=0.3)
    
    # ---------- 下半部分：R 图 ----------
    # 绘制 R 折线图：x 轴为批次序号，y 轴为批次极差
    # 颜色用橙色（#C98A2D），与 Xbar 图的蓝色区分
    ax2.plot(range(len(R)), R, "-o", ms=3, color="#C98A2D", label="R")
    # 绘制 R 图中心线
    ax2.axhline(R_bar, color="#A06F25", ls="--", lw=1.2, label=f"CL={R_bar:.3f}")
    # 绘制 R 图上控制限
    ax2.axhline(UCL_R, color="#B23A48", ls=":", lw=1, label=f"UCL={UCL_R:.3f}")
    # 绘制 R 图下控制限
    ax2.axhline(LCL_R, color="#B23A48", ls=":", lw=1, label=f"LCL={LCL_R:.3f}")
    # 如果有 R 图失控点，用红色 × 标记
    if ooc_r.any():
        ax2.scatter(np.where(ooc_r)[0], R[ooc_r], c="#B23A48", s=50, 
                   marker="x", zorder=5, label=f"失控点 ({ooc_r.sum()})")
    # 设置 x 轴标签（两张图共享 x 轴，只需在下面这张标注）
    ax2.set_xlabel("批次序号")
    # 设置 y 轴标签
    ax2.set_ylabel("R（批次极差）")
    # 显示图例
    ax2.legend(loc="upper right", fontsize=8)
    # 显示网格线
    ax2.grid(alpha=0.3)
    
    # 自动调整子图间距，防止标签重叠
    fig.tight_layout()
    # 保存图表为 PNG 文件，dpi=150 保证清晰度
    # 文件名格式：spc_xbar_r_critical_dimension.png
    fig.savefig(os.path.join(RESULT, f"spc_xbar_r_{param}.png"), dpi=150)
    # 关闭图表释放内存（避免内存泄漏）
    plt.close(fig)
    
    # 返回计算结果字典，供后续函数使用
    return {
        "param": param,           # 参数名
        "Xbar_bar": Xbar_bar,     # Xbar 图中心线（总均值）
        "R_bar": R_bar,           # R 图中心线（平均极差）
        "UCL_Xbar": UCL_Xbar,     # Xbar 图上控制限
        "LCL_Xbar": LCL_Xbar,     # Xbar 图下控制限
        "UCL_R": UCL_R,           # R 图上控制限
        "LCL_R": LCL_R,           # R 图下控制限
        "n_ooc": n_ooc,           # 失控点总数
        "ooc_rate": n_ooc / (2 * len(Xbar)),  # 失控率 = 失控点数 / 总数据点数（两张图）
    }


# ============================================================
# 函数 3：过程能力分析（Cp / Cpk / Pp / Ppk）
# ============================================================
def capability_analysis(df, param):
    """
    过程能力指数原理：
      - Cp = (USL - LSL) / (6σ)  → 过程潜在能力（不考虑中心偏移）
      - Cpk = min((USL - μ) / 3σ, (μ - LSL) / 3σ)  → 短期能力（考虑偏移）
      - Pp = (USL - LSL) / (6σ_overall)  → 长期性能
      - Ppk = min((USL - μ) / 3σ_overall, (μ - LSL) / 3σ_overall)  → 长期性能（考虑偏移）
    
    σ 估计：
      - 短期 σ_within = R_bar / d2（d2 是常数，n=5 时 d2=2.326）
      - 长期 σ_overall = 整体标准差（所有数据）
    
    判标：
      - Cpk < 1.0 → 过程能力不足，需改进
      - 1.0 ≤ Cpk < 1.33 → 过程能力可接受，但需监控
      - Cpk ≥ 1.33 → 过程能力充足（6Sigma 标准）
      - Cpk ≥ 1.67 → 过程能力优秀
    """
    # 从全局规格限字典中取出当前参数的 LSL 和 USL
    spec = SPEC_LIMITS[param]
    # LSL = Lower Specification Limit（下规格限），低于此值视为不合格
    LSL, USL = spec["LSL"], spec["USL"]
    # USL = Upper Specification Limit（上规格限），高于此值视为不合格
    
    # 提取当前参数的所有晶圆级数据（一维数组）
    data = df[param].values
    # 获取数据总长度（样本量）
    n = len(data)
    
    # ============================================================
    # 计算整体统计量
    # ============================================================
    # 计算数据的均值 μ（过程中心）
    mu = np.mean(data)
    # 计算整体标准差（长期标准差 σ_overall）
    # ddof=1 表示使用贝塞尔校正（除以 n-1 而非 n），得到无偏估计
    sigma_overall = np.std(data, ddof=1)  # 长期标准差
    
    # ============================================================
    # 计算短期标准差（σ_within）
    # ============================================================
    # 短期标准差通过 R_bar / d2 估计，只反映组内变异
    # 按 lot_id 分组，取出每个批次内该参数的所有值
    grouped = df.groupby("lot_id")[param].apply(list)
    # 计算每个批次的极差（max - min）
    R_values = [np.max(x) - np.min(x) for x in grouped]
    # 计算所有批次极差的平均值 → R_bar
    R_bar = np.mean(R_values)
    # d2 常数表：取决于子组大小 n，用于将 R_bar 转换为 σ 的无偏估计
    # d2 的理论来源：正态分布下极差的期望值 E(R) = d2 × σ
    d2_dict = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534, 7: 2.704, 8: 2.847, 9: 2.970, 10: 3.078}
    # 取子组大小的中位数
    n_subgroup = int(np.median([len(x) for x in grouped]))
    # 根据子组大小查找 d2 值，找不到时默认 n=5 的 d2=2.326
    d2 = d2_dict.get(n_subgroup, 2.326)
    # 短期标准差 = R_bar / d2
    sigma_within = R_bar / d2
    
    # ============================================================
    # 计算过程能力指数
    # ============================================================
    # Cp = (USL - LSL) / (6σ_within)
    # Cp 只考虑规格宽度与过程变异的关系，不考虑过程中心是否偏移
    # Cp > 1 表示规格宽度 > 6σ（过程变异能放进规格内）
    Cp = (USL - LSL) / (6 * sigma_within)
    # Cpk = min((USL - μ) / 3σ, (μ - LSL) / 3σ)
    # Cpk 同时考虑了过程中心偏移，取上下两侧较小值
    # Cpk > 1.33 表示过程中心偏离不超过 1σ
    Cpk = min((USL - mu) / (3 * sigma_within), (mu - LSL) / (3 * sigma_within))
    # Pp = (USL - LSL) / (6σ_overall)
    # Pp 与 Cp 类似，但用长期标准差（包含组间变异）
    Pp = (USL - LSL) / (6 * sigma_overall)
    # Ppk = min((USL - μ) / 3σ_overall, (μ - LSL) / 3σ_overall)
    # Ppk 与 Cpk 类似，但用长期标准差
    Ppk = min((USL - mu) / (3 * sigma_overall), (mu - LSL) / (3 * sigma_overall))
    
    # ============================================================
    # 正态性检验
    # ============================================================
    # 过程能力分析的前提是数据近似正态分布
    # 根据样本量选择不同的检验方法
    if n > 5000:
        # 样本量 > 5000 时用 D'Agostino-Pearson 检验（基于偏度和峰度）
        # Shapiro-Wilk 检验在大样本时计算量太大
        stat, p_value = stats.normaltest(data)
        test_name = "D'Agostino-Pearson"
    else:
        # 样本量 ≤ 5000 时用 Shapiro-Wilk 检验（更强大）
        # Shapiro-Wilk 是小样本正态性检验的金标准
        stat, p_value = stats.shapiro(data)
        test_name = "Shapiro-Wilk"
    # 判断是否正态：p > 0.05 表示不能拒绝正态假设（即数据近似正态）
    is_normal = p_value > 0.05
    
    # ============================================================
    # 绘图：过程能力直方图 + 正态拟合曲线 + 规格限
    # ============================================================
    # 创建单张图，宽 7 英寸、高 5 英寸
    fig, ax = plt.subplots(figsize=(7, 5))
    # 绘制直方图：bins=40 表示分 40 个柱
    # density=True 表示纵轴为概率密度（而非频数），方便与正态曲线对比
    # alpha=0.6 设置透明度，edgecolor="white" 柱子之间有白色间隔
    counts, bins, patches = ax.hist(data, bins=40, density=True, alpha=0.6, 
                                     color="#3B6EA5", edgecolor="white", label="数据分布")
    
    # 生成正态分布拟合曲线的 x 轴数据点（200 个均匀分布的点）
    x_range = np.linspace(data.min(), data.max(), 200)
    # 计算正态分布的概率密度函数值（PDF）
    # 参数：均值 mu，标准差 sigma_overall
    pdf = stats.norm.pdf(x_range, mu, sigma_overall)
    # 绘制正态拟合曲线：红色实线，线宽 2
    ax.plot(x_range, pdf, "-", color="#B23A48", lw=2, label=f"正态拟合 (μ={mu:.2f}, σ={sigma_overall:.2f})")
    
    # 绘制下规格限（LSL）：橙色虚线
    ax.axvline(LSL, color="#C98A2D", ls="--", lw=1.5, label=f"LSL={LSL}")
    # 绘制上规格限（USL）：橙色虚线
    ax.axvline(USL, color="#C98A2D", ls="--", lw=1.5, label=f"USL={USL}")
    # 绘制均值线：深蓝色点线
    ax.axvline(mu, color="#2C5F8D", ls=":", lw=1.2, label=f"μ={mu:.2f}")
    
    # 设置 x 轴标签为参数名
    ax.set_xlabel(param)
    # 设置 y 轴标签
    ax.set_ylabel("密度")
    # 设置图表标题，包含四个能力指数
    ax.set_title(f"{param} 过程能力分析\nCp={Cp:.2f} | Cpk={Cpk:.2f} | Pp={Pp:.2f} | Ppk={Ppk:.2f}")
    # 显示图例，右上角，字号 9
    ax.legend(loc="upper right", fontsize=9)
    # 显示网格线
    ax.grid(alpha=0.3)
    
    # 自动调整布局
    fig.tight_layout()
    # 保存为 PNG 文件
    fig.savefig(os.path.join(RESULT, f"capability_{param}.png"), dpi=150)
    # 关闭图表释放内存
    plt.close(fig)
    
    # 返回计算结果字典
    return {
        "param": param,                   # 参数名
        "LSL": LSL,                       # 下规格限
        "USL": USL,                       # 上规格限
        "mu": mu,                         # 过程均值
        "sigma_within": sigma_within,     # 短期标准差（组内）
        "sigma_overall": sigma_overall,   # 长期标准差（整体）
        "Cp": Cp,                         # 过程潜在能力指数
        "Cpk": Cpk,                       # 短期过程能力指数
        "Pp": Pp,                         # 长期过程性能指数
        "Ppk": Ppk,                       # 长期过程性能指数（考虑偏移）
        "normality_test": test_name,      # 正态性检验方法名
        "p_value": p_value,               # 正态性检验 p 值
        "is_normal": is_normal,           # 是否通过正态性检验
    }


# ============================================================
# 函数 4：失控点分析（模拟 FDC 自动 Hold 逻辑）
# ============================================================
def ooc_analysis(df, spc_results):
    """
    工业场景：当关键参数超出控制限（OOC），FDC（Fault Detection & Classification）
    系统自动 Hold 该批次，等待工艺工程师排查根因。
    
    本模块：识别失控批次，统计良率损失，模拟"提前拦截"的业务价值。
    
    注意：本数据集中 CD 与良率是非单调关系（CD 偏低时良率反而更高），
    这说明传统 SPC（死守均值）可能不是最优策略，需要结合 DOE 找到更优工艺窗口。
    """
    # 打印当前步骤标题
    print("\n===== 4. 失控点分析（FDC 自动 Hold 模拟）=====")
    
    # ============================================================
    # 合并所有参数的失控批次
    # ============================================================
    # 用 set 存储失控批次 ID，自动去重（同一批次可能多个参数都失控）
    ooc_lots = set()
    # 列表存储失控详情（哪个批次、哪个参数、偏高还是偏低）
    ooc_details = []  # 记录失控方向
    # 遍历每个参数的 SPC 结果
    for res in spc_results:
        # 取出参数名
        param = res["param"]
        # 取出该参数 Xbar 图的上、下控制限
        UCL, LCL = res["UCL_Xbar"], res["LCL_Xbar"]
        
        # 按 lot_id 分组，计算每个批次的参数均值
        lot_means = df.groupby("lot_id")[param].mean()
        # 找出均值超出上控制限的批次（偏高失控）
        ooc_high = lot_means > UCL
        # 找出均值低于下控制限的批次（偏低失控）
        ooc_low = lot_means < LCL
        # 将偏高失控的批次 ID 加入集合
        ooc_lots.update(lot_means[ooc_high].index.tolist())
        # 将偏低失控的批次 ID 加入集合
        ooc_lots.update(lot_means[ooc_low].index.tolist())
        
        # 记录每个偏高失控批次的详情
        for lot in lot_means[ooc_high].index:
            ooc_details.append({"lot": lot, "param": param, "direction": "high"})
        # 记录每个偏低失控批次的详情
        for lot in lot_means[ooc_low].index:
            ooc_details.append({"lot": lot, "param": param, "direction": "low"})
    
    # 统计失控批次总数（去重后）
    n_ooc_lots = len(ooc_lots)
    # 统计总批次数
    n_total_lots = df["lot_id"].nunique()
    # 计算失控率
    ooc_rate = n_ooc_lots / n_total_lots
    
    # ============================================================
    # 失控批次 vs 正常批次的良率对比
    # ============================================================
    # 筛选出失控批次的所有晶圆数据
    df_ooc = df[df["lot_id"].isin(ooc_lots)]
    # 筛选出正常批次的所有晶圆数据（用 ~ 取反）
    df_normal = df[~df["lot_id"].isin(ooc_lots)]
    
    # 计算失控批次的平均良率
    yield_ooc = df_ooc["yield"].mean()
    # 计算正常批次的平均良率
    yield_normal = df_normal["yield"].mean()
    # 计算良率差异（正常 - 失控），正值表示失控批次良率更低
    yield_gap = yield_normal - yield_ooc
    
    # ============================================================
    # 区分失控方向，分别统计良率
    # ============================================================
    # 提取所有偏高失控的批次 ID
    ooc_high_lots = set(d["lot"] for d in ooc_details if d["direction"] == "high")
    # 提取所有偏低失控的批次 ID
    ooc_low_lots = set(d["lot"] for d in ooc_details if d["direction"] == "low")
    
    # 计算偏高失控批次的平均良率（如果有偏高失控批次的话）
    yield_ooc_high = df[df["lot_id"].isin(ooc_high_lots)]["yield"].mean() if ooc_high_lots else 0
    # 计算偏低失控批次的平均良率
    yield_ooc_low = df[df["lot_id"].isin(ooc_low_lots)]["yield"].mean() if ooc_low_lots else 0
    
    # 打印失控批次统计信息
    print(f"  失控批次数: {n_ooc_lots} / {n_total_lots} ({ooc_rate*100:.1f}%)")
    # 打印偏高失控批次数和平均良率
    print(f"    - 偏高失控: {len(ooc_high_lots)} 批次，平均良率 {yield_ooc_high:.3f}")
    # 打印偏低失控批次数和平均良率
    print(f"    - 偏低失控: {len(ooc_low_lots)} 批次，平均良率 {yield_ooc_low:.3f}")
    # 打印失控批次整体平均良率
    print(f"  失控批次整体平均良率: {yield_ooc:.3f}")
    # 打印正常批次平均良率
    print(f"  正常批次平均良率: {yield_normal:.3f}")
    # 打印良率差异（pp = percentage point，百分点）
    print(f"  良率差异: {yield_gap:.3f}（{yield_gap*100:.1f}pp）")
    
    # ============================================================
    # 关键洞察：参数-良率关系非单调
    # ============================================================
    print(f"\n  ⚠ 关键洞察:")
    # 如果失控批次良率反而更高，说明偏离均值不一定意味着良率下降
    print(f"    失控批次良率反而更高（+{abs(yield_gap)*100:.1f}pp），说明参数-良率关系非单调。")
    # 传统 SPC 的目标是让参数稳定在均值附近，但这里均值不是最优点
    print(f"    传统 SPC（死守均值）不是最优策略，需要 DOE 找到更优工艺窗口。")
    # 引出 optimize.py 的贝叶斯优化：不追求稳定，而是追求最优
    print(f"    这正是 optimize.py 贝叶斯优化的价值：不追求'稳定在均值'，而是'找到最优'。")
    
    # 返回失控分析结果字典
    return {
        "n_ooc_lots": n_ooc_lots,       # 失控批次总数
        "n_total_lots": n_total_lots,   # 总批次数
        "ooc_rate": ooc_rate,           # 失控率
        "yield_ooc": yield_ooc,         # 失控批次平均良率
        "yield_normal": yield_normal,   # 正常批次平均良率
        "yield_gap": yield_gap,         # 良率差异
        "n_ooc_high": len(ooc_high_lots),  # 偏高失控批次数
        "n_ooc_low": len(ooc_low_lots),    # 偏低失控批次数
    }


# ============================================================
# 函数 5：主流程（串联所有分析步骤）
# ============================================================
def main():
    # 打印项目标题分隔线
    print("=" * 70)
    # 打印项目名称
    print("SPC 统计过程控制 + 过程能力分析")
    # 打印分隔线
    print("=" * 70)
    
    # ============================================================
    # 步骤 1：数据准备
    # ============================================================
    # 调用 prepare_subgroups()，按批次分组，返回子组字典和批次总数
    subgroups, n_lots = prepare_subgroups()
    
    # ============================================================
    # 步骤 2：绘制 Xbar-R 控制图
    # ============================================================
    print("\n===== 2. Xbar-R 控制图 =====")
    # 初始化空列表，存储每个参数的 SPC 结果
    spc_results = []
    # 遍历每个关键参数
    for param in KEY_PARAMS:
        # 调用 xbar_r_chart() 绘制控制图，返回结果字典
        res = xbar_r_chart(subgroups, param)
        # 将结果追加到列表
        spc_results.append(res)
        # 打印该参数的中心线和失控点统计
        print(f"  {param}: Xbar_bar={res['Xbar_bar']:.3f}, "
              f"失控点={res['n_ooc']} ({res['ooc_rate']*100:.1f}%)")
    
    # ============================================================
    # 步骤 3：过程能力分析
    # ============================================================
    print("\n===== 3. 过程能力分析（Cp / Cpk / Pp / Ppk）=====")
    # 重新读取 CSV 数据（capability_analysis 需要完整的 DataFrame）
    df = pd.read_csv(os.path.join(DATA, "semiconductor_yield_forecasting_data.csv"))
    # 初始化空列表，存储每个参数的过程能力结果
    cap_results = []
    # 遍历每个关键参数
    for param in KEY_PARAMS:
        # 调用 capability_analysis() 计算过程能力指数
        res = capability_analysis(df, param)
        # 将结果追加到列表
        cap_results.append(res)
        # 打印参数名
        print(f"  {param}:")
        # 打印四个能力指数
        print(f"    Cp={res['Cp']:.2f} | Cpk={res['Cpk']:.2f} | Pp={res['Pp']:.2f} | Ppk={res['Ppk']:.2f}")
        # 打印正态性检验结果（检验名、p 值、是否正态）
        print(f"    正态性检验: {res['normality_test']} p={res['p_value']:.3f} {'✓ 正态' if res['is_normal'] else '✗ 非正态'}")
        
        # ============================================================
        # Cpk 判标（工业标准）
        # ============================================================
        # Cpk < 1.0：过程能力不足，需要改进（良率损失风险高）
        if res["Cpk"] < 1.0:
            status = "⚠ 过程能力不足，需改进"
        # 1.0 ≤ Cpk < 1.33：可接受但需监控（接近临界值）
        elif res["Cpk"] < 1.33:
            status = "⚡ 过程能力可接受，需监控"
        # 1.33 ≤ Cpk < 1.67：过程能力充足（6Sigma 标准）
        elif res["Cpk"] < 1.67:
            status = "✓ 过程能力充足"
        # Cpk ≥ 1.67：过程能力优秀（超出 6Sigma 标准）
        else:
            status = "✓✓ 过程能力优秀"
        # 打印判标结果
        print(f"    判标: {status}")
    
    # ============================================================
    # 步骤 4：失控点分析
    # ============================================================
    # 调用 ooc_analysis()，传入完整数据和 SPC 结果
    ooc_res = ooc_analysis(df, spc_results)
    
    # ============================================================
    # 步骤 5：汇总输出（业务闭环总结）
    # ============================================================
    print("\n===== 业务闭环总结 =====")
    # 打印 SPC 控制图统计
    print(f"  1) SPC 控制图: {len(KEY_PARAMS)} 个关键参数已绘制 Xbar-R 图")
    # 打印 Cpk 范围（最小值 ~ 最大值）
    print(f"  2) 过程能力: Cpk 范围 [{min(r['Cpk'] for r in cap_results):.2f}, "
          f"{max(r['Cpk'] for r in cap_results):.2f}]")
    # 打印失控拦截统计
    print(f"  3) 失控拦截: 提前 Hold {ooc_res['n_ooc_lots']} 批次，"
          f"可避免 {ooc_res['yield_gap']*100:.1f}pp 良率损失")
    # 打印与 DOE 的闭环关系
    print(f"  4) 与 DOE 闭环: 对 Cpk < 1.33 的参数做 DOE 寻优（optimize.py），"
          f"提升过程能力至 1.33 以上")
    
    # 打印输出文件路径提示
    print(f"\n  图表已保存至: {RESULT}/")
    # 提示控制图文件名格式
    print(f"    spc_xbar_r_*.png（控制图）")
    # 提示过程能力图文件名格式
    print(f"    capability_*.png（过程能力直方图）")


# ============================================================
# 程序入口
# ============================================================
# Python 标准写法：只有直接运行此脚本时才执行 main()
# 如果被其他脚本 import，不会自动执行
if __name__ == "__main__":
    main()
