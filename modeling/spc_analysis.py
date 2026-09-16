# -*- coding: utf-8 -*-

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

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from scipy import stats

# ============================================================
# 全局配置：matplotlib 中文字体
# ============================================================
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ============================================================
# 全局配置：路径常量
# ============================================================
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
RESULT = os.path.join(BASE, "results")
FIGURES = os.path.join(BASE, "reports", "figures")
os.makedirs(RESULT, exist_ok=True)
os.makedirs(FIGURES, exist_ok=True)

# ============================================================
# 全局配置：关键参数列表
# ============================================================
KEY_PARAMS = ["critical_dimension", "oxide_thickness", "vth"]

# ============================================================
# 全局配置：工程规格限
# ============================================================
SPEC_LIMITS = {
    "critical_dimension": {"LSL": 15.0, "USL": 35.0},
    "oxide_thickness": {"LSL": 45.0, "USL": 70.0},
    "vth": {"LSL": 0.50, "USL": 0.80},
}

# ============================================================
# SPC 控制图常数表
# ============================================================
SPC_CONSTANTS = {
    2:  {"A2": 1.880, "D3": 0,    "D4": 3.267, "d2": 1.128},
    3:  {"A2": 1.023, "D3": 0,    "D4": 2.575, "d2": 1.693},
    4:  {"A2": 0.729, "D3": 0,    "D4": 2.282, "d2": 2.059},
    5:  {"A2": 0.577, "D3": 0,    "D4": 2.114, "d2": 2.326},
    6:  {"A2": 0.483, "D3": 0.076,"D4": 2.004, "d2": 2.534},
    7:  {"A2": 0.419, "D3": 0.136,"D4": 1.924, "d2": 2.704},
    8:  {"A2": 0.373, "D3": 0.185,"D4": 1.864, "d2": 2.847},
    9:  {"A2": 0.337, "D3": 0.223,"D4": 1.816, "d2": 2.970},
    10: {"A2": 0.308, "D3": 0.284,"D4": 1.777, "d2": 3.078},
    25: {"A2": 0.153, "D3": 0.451,"D4": 1.548, "d2": 3.931},
}

# ============================================================
# 颜色方案（Minitab 风格）
# ============================================================
COLORS = {
    "data_line": "#1F77B4",       # 数据折线（蓝色）
    "center_line": "#2CA02C",     # 中心线（绿色）
    "control_limit": "#D62728",   # 控制限（红色）
    "spec_limit": "#FF7F0E",      # 规格限（橙色）
    "ooc_point": "#D62728",       # 失控点（红色）
    "zone_1sigma": "#C8E6C9",     # ±1σ 区域（浅绿）
    "zone_2sigma": "#FFF9C4",     # ±2σ 区域（浅黄）
    "zone_3sigma": "#FFCDD2",     # ±3σ 区域（浅红）
    "histogram": "#1F77B4",       # 直方图（蓝色）
    "normal_curve": "#D62728",    # 正态曲线（红色）
    "mean_line": "#2CA02C",       # 均值线（绿色）
    "bg": "#FAFAFA",              # 背景色
}


# ============================================================
# 函数 1：数据准备 —— 按批次分组
# ============================================================
def prepare_subgroups():
    """按 lot_id 分组，每个 lot 包含多片 wafer。"""
    print("===== 1. 数据准备（按批次分组）=====")
    df = pd.read_csv(os.path.join(DATA, "semiconductor_yield_forecasting_data.csv"))
    print(f"  总数据: {len(df)} 行（晶圆级）")
    
    grouped = df.groupby("lot_id")
    n_lots = grouped.ngroups
    avg_wafers = len(df) / n_lots
    print(f"  批次数: {n_lots}，每批平均 {avg_wafers:.1f} 片晶圆")
    
    subgroups = {}
    for param in KEY_PARAMS:
        subgroups[param] = grouped[param].apply(list).to_dict()
    
    return subgroups, n_lots


# ============================================================
# 函数 2：Xbar-R 控制图（Minitab 工业标准格式）
# ============================================================
def xbar_r_chart(subgroups, param):
    """
    Xbar-R 控制图（Minitab 风格）：
    - 上下两张子图：Xbar 图 + R 图
    - 控制限区域着色（±1σ/±2σ/±3σ）
    - 失控点用红色 × 标记
    - 右侧统计摘要面板
    """
    lots = sorted(subgroups[param].keys())
    X_subgroups = [subgroups[param][lot] for lot in lots]
    
    Xbar = np.array([np.mean(x) for x in X_subgroups])
    R = np.array([np.max(x) - np.min(x) for x in X_subgroups])
    n = np.array([len(x) for x in X_subgroups])
    n_subgroup = int(np.median(n))
    
    # 查找 SPC 常数
    consts = SPC_CONSTANTS.get(n_subgroup, SPC_CONSTANTS[5])
    A2, D3, D4, d2 = consts["A2"], consts["D3"], consts["D4"], consts["d2"]
    
    # 中心线
    Xbar_bar = np.mean(Xbar)
    R_bar = np.mean(R)
    
    # 控制限
    UCL_Xbar = Xbar_bar + A2 * R_bar
    LCL_Xbar = Xbar_bar - A2 * R_bar
    UCL_R = D4 * R_bar
    LCL_R = D3 * R_bar
    
    # 标准差估计（用于区域着色）
    sigma_within = R_bar / d2
    
    # 失控点识别
    ooc_xbar = (Xbar > UCL_Xbar) | (Xbar < LCL_Xbar)
    ooc_r = (R > UCL_R) | (R < LCL_R)
    n_ooc = int(ooc_xbar.sum()) + int(ooc_r.sum())
    
    # ============================================================
    # 绘图：Minitab 风格 Xbar-R 控制图
    # ============================================================
    fig = plt.figure(figsize=(14, 10))
    
    # 主绘图区域（左侧 75%）
    ax_xbar = fig.add_axes([0.08, 0.55, 0.65, 0.38])
    ax_r = fig.add_axes([0.08, 0.12, 0.65, 0.38])
    
    # 右侧统计面板（右侧 20%）
    ax_stats = fig.add_axes([0.78, 0.12, 0.20, 0.81])
    ax_stats.axis("off")
    
    x_indices = range(len(Xbar))
    
    # ---------- Xbar 图 ----------
    # 区域着色
    for i in range(len(Xbar) - 1):
        # ±1σ 区域（绿色）
        ax_xbar.axhspan(Xbar_bar - sigma_within, Xbar_bar + sigma_within,
                        alpha=0.15, color=COLORS["zone_1sigma"], zorder=0)
        # ±2σ 区域（黄色）
        ax_xbar.axhspan(Xbar_bar - 2*sigma_within, Xbar_bar - sigma_within,
                        alpha=0.15, color=COLORS["zone_2sigma"], zorder=0)
        ax_xbar.axhspan(Xbar_bar + sigma_within, Xbar_bar + 2*sigma_within,
                        alpha=0.15, color=COLORS["zone_2sigma"], zorder=0)
        # ±3σ 区域（红色）
        ax_xbar.axhspan(Xbar_bar - 3*sigma_within, Xbar_bar - 2*sigma_within,
                        alpha=0.15, color=COLORS["zone_3sigma"], zorder=0)
        ax_xbar.axhspan(Xbar_bar + 2*sigma_within, Xbar_bar + 3*sigma_within,
                        alpha=0.15, color=COLORS["zone_3sigma"], zorder=0)
    
    # 数据折线
    ax_xbar.plot(x_indices, Xbar, "-o", ms=4, mfc="white", mec=COLORS["data_line"],
                 mew=1.5, color=COLORS["data_line"], lw=1.2, zorder=3)
    
    # 控制限线
    ax_xbar.axhline(UCL_Xbar, color=COLORS["control_limit"], ls="-", lw=1.5, zorder=2)
    ax_xbar.axhline(LCL_Xbar, color=COLORS["control_limit"], ls="-", lw=1.5, zorder=2)
    ax_xbar.axhline(Xbar_bar, color=COLORS["center_line"], ls="--", lw=1.5, zorder=2)
    
    # 失控点标记
    if ooc_xbar.any():
        ooc_idx = np.where(ooc_xbar)[0]
        ax_xbar.scatter(ooc_idx, Xbar[ooc_xbar], c=COLORS["ooc_point"], s=80,
                       marker="x", zorder=5, lw=2)
    
    # 标注控制限值
    ax_xbar.text(len(Xbar) * 0.02, UCL_Xbar, f" UCL={UCL_Xbar:.3f}",
                va="bottom", fontsize=8, color=COLORS["control_limit"])
    ax_xbar.text(len(Xbar) * 0.02, LCL_Xbar, f" LCL={LCL_Xbar:.3f}",
                va="top", fontsize=8, color=COLORS["control_limit"])
    ax_xbar.text(len(Xbar) * 0.02, Xbar_bar, f" CL={Xbar_bar:.3f}",
                va="bottom", fontsize=8, color=COLORS["center_line"])
    
    ax_xbar.set_ylabel("Xbar（批次均值）", fontsize=10)
    ax_xbar.set_title(f"{param} Xbar-R 控制图（n={n_subgroup}）", fontsize=12, fontweight="bold")
    ax_xbar.grid(True, alpha=0.3, zorder=1)
    ax_xbar.set_xlim(-1, len(Xbar))
    
    # ---------- R 图 ----------
    # 区域着色
    sigma_r = R_bar * np.sqrt(1 - (d2**2 / n_subgroup)) if n_subgroup > 1 else R_bar
    for i in range(len(R) - 1):
        ax_r.axhspan(0, R_bar, alpha=0.1, color=COLORS["zone_1sigma"], zorder=0)
    
    # 数据折线
    ax_r.plot(x_indices, R, "-o", ms=4, mfc="white", mec="#FF8C00",
              mew=1.5, color="#FF8C00", lw=1.2, zorder=3)
    
    # 控制限线
    ax_r.axhline(UCL_R, color=COLORS["control_limit"], ls="-", lw=1.5, zorder=2)
    ax_r.axhline(LCL_R, color=COLORS["control_limit"], ls="-", lw=1.5, zorder=2)
    ax_r.axhline(R_bar, color=COLORS["center_line"], ls="--", lw=1.5, zorder=2)
    
    # 失控点标记
    if ooc_r.any():
        ooc_idx = np.where(ooc_r)[0]
        ax_r.scatter(ooc_idx, R[ooc_r], c=COLORS["ooc_point"], s=80,
                    marker="x", zorder=5, lw=2)
    
    # 标注控制限值
    ax_r.text(len(R) * 0.02, UCL_R, f" UCL={UCL_R:.3f}",
             va="bottom", fontsize=8, color=COLORS["control_limit"])
    ax_r.text(len(R) * 0.02, LCL_R, f" LCL={LCL_R:.3f}",
             va="top", fontsize=8, color=COLORS["control_limit"])
    ax_r.text(len(R) * 0.02, R_bar, f" CL={R_bar:.3f}",
             va="bottom", fontsize=8, color=COLORS["center_line"])
    
    ax_r.set_xlabel("批次序号（Lot Sequence）", fontsize=10)
    ax_r.set_ylabel("R（批次极差）", fontsize=10)
    ax_r.grid(True, alpha=0.3, zorder=1)
    ax_r.set_xlim(-1, len(R))
    
    # ---------- 右侧统计面板 ----------
    stats_text = (
        f"Xbar 图统计\n"
        f"{'─' * 20}\n"
        f"CL  = {Xbar_bar:.4f}\n"
        f"UCL = {UCL_Xbar:.4f}\n"
        f"LCL = {LCL_Xbar:.4f}\n"
        f"σ_w = {sigma_within:.4f}\n"
        f"\n"
        f"R 图统计\n"
        f"{'─' * 20}\n"
        f"CL  = {R_bar:.4f}\n"
        f"UCL = {UCL_R:.4f}\n"
        f"LCL = {LCL_R:.4f}\n"
        f"\n"
        f"失控点统计\n"
        f"{'─' * 20}\n"
        f"Xbar: {int(ooc_xbar.sum())} 点\n"
        f"R:    {int(ooc_r.sum())} 点\n"
        f"合计: {n_ooc} 点\n"
        f"失控率: {n_ooc/(2*len(Xbar))*100:.1f}%\n"
        f"\n"
        f"子组大小 n = {n_subgroup}\n"
        f"批次数 = {len(Xbar)}"
    )
    ax_stats.text(0.05, 0.95, stats_text, fontsize=8, family="Microsoft YaHei",
                 verticalalignment="top", bbox=dict(boxstyle="round", facecolor="#F0F0F0", alpha=0.8))
    
    fig.savefig(os.path.join(FIGURES, f"spc_xbar_r_{param}.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
    
    return {
        "param": param,
        "Xbar_bar": Xbar_bar,
        "R_bar": R_bar,
        "UCL_Xbar": UCL_Xbar,
        "LCL_Xbar": LCL_Xbar,
        "UCL_R": UCL_R,
        "LCL_R": LCL_R,
        "n_ooc": n_ooc,
        "ooc_rate": n_ooc / (2 * len(Xbar)),
    }


# ============================================================
# 函数 3：过程能力分析（Minitab 风格）
# ============================================================
def capability_analysis(df, param):
    """
    过程能力分析（Minitab 风格）：
    - 左侧：直方图 + 正态拟合曲线 + 规格限
    - 右侧：统计摘要面板（Cp, Cpk, Pp, Ppk 等）
    """
    spec = SPEC_LIMITS[param]
    LSL, USL = spec["LSL"], spec["USL"]
    
    data = df[param].values
    n = len(data)
    
    mu = np.mean(data)
    sigma_overall = np.std(data, ddof=1)
    
    # 短期标准差
    grouped = df.groupby("lot_id")[param].apply(list)
    R_values = [np.max(x) - np.min(x) for x in grouped]
    R_bar = np.mean(R_values)
    n_subgroup = int(np.median([len(x) for x in grouped]))
    consts = SPC_CONSTANTS.get(n_subgroup, SPC_CONSTANTS[5])
    d2 = consts["d2"]
    sigma_within = R_bar / d2
    
    # 过程能力指数
    Cp = (USL - LSL) / (6 * sigma_within)
    Cpk = min((USL - mu) / (3 * sigma_within), (mu - LSL) / (3 * sigma_within))
    Pp = (USL - LSL) / (6 * sigma_overall)
    Ppk = min((USL - mu) / (3 * sigma_overall), (mu - LSL) / (3 * sigma_overall))
    
    # 正态性检验
    if n > 5000:
        stat, p_value = stats.normaltest(data)
        test_name = "D'Agostino-Pearson"
    else:
        stat, p_value = stats.shapiro(data)
        test_name = "Shapiro-Wilk"
    is_normal = p_value > 0.05
    
    # ============================================================
    # 绘图：Minitab 风格过程能力图
    # ============================================================
    fig = plt.figure(figsize=(14, 8))
    
    # 主绘图区域（左侧 70%）
    ax_hist = fig.add_axes([0.08, 0.12, 0.62, 0.80])
    
    # 右侧统计面板（右侧 25%）
    ax_stats = fig.add_axes([0.74, 0.12, 0.24, 0.80])
    ax_stats.axis("off")
    
    # ---------- 直方图 ----------
    # 计算合适的 bin 数量（Sturges 公式）
    n_bins = max(20, int(np.ceil(1 + 3.322 * np.log10(n))))
    counts, bins, patches = ax_hist.hist(data, bins=n_bins, density=True, alpha=0.7,
                                          color=COLORS["histogram"], edgecolor="white", lw=0.5)
    
    # 正态拟合曲线（Within）
    x_range = np.linspace(data.min() - 0.5*(data.max()-data.min())*0.1,
                          data.max() + 0.5*(data.max()-data.min())*0.1, 300)
    pdf_within = stats.norm.pdf(x_range, mu, sigma_within)
    ax_hist.plot(x_range, pdf_within, "-", color=COLORS["normal_curve"], lw=2,
                label=f"Within (σ={sigma_within:.3f})")
    
    # 正态拟合曲线（Overall）
    pdf_overall = stats.norm.pdf(x_range, mu, sigma_overall)
    ax_hist.plot(x_range, pdf_overall, "--", color="#8B0000", lw=1.5,
                label=f"Overall (σ={sigma_overall:.3f})")
    
    # 规格限
    ax_hist.axvline(LSL, color=COLORS["spec_limit"], ls="-", lw=2, zorder=5)
    ax_hist.axvline(USL, color=COLORS["spec_limit"], ls="-", lw=2, zorder=5)
    
    # 均值线
    ax_hist.axvline(mu, color=COLORS["mean_line"], ls="--", lw=1.5, zorder=4)
    
    # 标注
    ax_hist.text(LSL, ax_hist.get_ylim()[1] * 0.9, f" LSL\n {LSL}",
                ha="center", fontsize=9, color=COLORS["spec_limit"], fontweight="bold")
    ax_hist.text(USL, ax_hist.get_ylim()[1] * 0.9, f" USL\n {USL}",
                ha="center", fontsize=9, color=COLORS["spec_limit"], fontweight="bold")
    ax_hist.text(mu, ax_hist.get_ylim()[1] * 0.85, f" μ={mu:.2f}",
                ha="center", fontsize=8, color=COLORS["mean_line"])
    
    ax_hist.set_xlabel(param, fontsize=11)
    ax_hist.set_ylabel("密度（Density）", fontsize=11)
    ax_hist.set_title(f"{param} 过程能力分析", fontsize=13, fontweight="bold")
    ax_hist.legend(loc="upper right", fontsize=9)
    ax_hist.grid(True, alpha=0.3, axis="y")
    
    # ---------- 右侧统计面板 ----------
    # Cpk 判标
    if Cpk < 1.0:
        cpk_status = "⚠ 不足"
        cpk_color = "#D62728"
    elif Cpk < 1.33:
        cpk_status = "⚡ 可接受"
        cpk_color = "#FF8C00"
    elif Cpk < 1.67:
        cpk_status = "✓ 充足"
        cpk_color = "#2CA02C"
    else:
        cpk_status = "✓✓ 优秀"
        cpk_color = "#1F77B4"
    
    stats_text = (
        f"过程能力统计\n"
        f"{'═' * 22}\n"
        f"\n"
        f"规格限\n"
        f"{'─' * 22}\n"
        f"LSL   = {LSL:.4f}\n"
        f"USL   = {USL:.4f}\n"
        f"Target = —\n"
        f"\n"
        f"过程统计\n"
        f"{'─' * 22}\n"
        f"均值 μ = {mu:.4f}\n"
        f"N     = {n}\n"
        f"\n"
        f"短期能力（Within）\n"
        f"{'─' * 22}\n"
        f"σ_w   = {sigma_within:.4f}\n"
        f"Cp    = {Cp:.2f}\n"
        f"Cpk   = {Cpk:.2f}  {cpk_status}\n"
        f"\n"
        f"长期性能（Overall）\n"
        f"{'─' * 22}\n"
        f"σ_o   = {sigma_overall:.4f}\n"
        f"Pp    = {Pp:.2f}\n"
        f"Ppk   = {Ppk:.2f}\n"
        f"\n"
        f"正态性检验\n"
        f"{'─' * 22}\n"
        f"方法: {test_name}\n"
        f"p值:  {p_value:.4f}\n"
        f"结论: {'✓ 正态' if is_normal else ' 非正态'}"
    )
    ax_stats.text(0.05, 0.98, stats_text, fontsize=9, family="Microsoft YaHei",
                 verticalalignment="top",
                 bbox=dict(boxstyle="round", facecolor="#F8F9FA", edgecolor="#DEE2E6", alpha=0.9))
    
    fig.savefig(os.path.join(FIGURES, f"capability_{param}.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
    
    return {
        "param": param,
        "LSL": LSL,
        "USL": USL,
        "mu": mu,
        "sigma_within": sigma_within,
        "sigma_overall": sigma_overall,
        "Cp": Cp,
        "Cpk": Cpk,
        "Pp": Pp,
        "Ppk": Ppk,
        "normality_test": test_name,
        "p_value": p_value,
        "is_normal": is_normal,
    }


# ============================================================
# 函数 4：失控点分析（模拟 FDC 自动 Hold 逻辑）
# ============================================================
def ooc_analysis(df, spc_results):
    """
    工业场景：当关键参数超出控制限（OOC），FDC（Fault Detection & Classification）
    系统自动 Hold 该批次，等待工艺工程师排查根因。
    """
    print("\n===== 4. 失控点分析（FDC 自动 Hold 模拟）=====")
    
    ooc_lots = set()
    ooc_details = []
    for res in spc_results:
        param = res["param"]
        UCL, LCL = res["UCL_Xbar"], res["LCL_Xbar"]
        
        lot_means = df.groupby("lot_id")[param].mean()
        ooc_high = lot_means > UCL
        ooc_low = lot_means < LCL
        ooc_lots.update(lot_means[ooc_high].index.tolist())
        ooc_lots.update(lot_means[ooc_low].index.tolist())
        
        for lot in lot_means[ooc_high].index:
            ooc_details.append({"lot": lot, "param": param, "direction": "high"})
        for lot in lot_means[ooc_low].index:
            ooc_details.append({"lot": lot, "param": param, "direction": "low"})
    
    n_ooc_lots = len(ooc_lots)
    n_total_lots = df["lot_id"].nunique()
    ooc_rate = n_ooc_lots / n_total_lots
    
    df_ooc = df[df["lot_id"].isin(ooc_lots)]
    df_normal = df[~df["lot_id"].isin(ooc_lots)]
    
    yield_ooc = df_ooc["yield"].mean()
    yield_normal = df_normal["yield"].mean() if len(df_normal) > 0 else None
    yield_gap = (yield_normal - yield_ooc) if yield_normal is not None else None
    
    ooc_high_lots = set(d["lot"] for d in ooc_details if d["direction"] == "high")
    ooc_low_lots = set(d["lot"] for d in ooc_details if d["direction"] == "low")
    
    yield_ooc_high = df[df["lot_id"].isin(ooc_high_lots)]["yield"].mean() if ooc_high_lots else 0
    yield_ooc_low = df[df["lot_id"].isin(ooc_low_lots)]["yield"].mean() if ooc_low_lots else 0
    
    print(f"  失控批次数: {n_ooc_lots} / {n_total_lots} ({ooc_rate*100:.1f}%)")
    print(f"    - 偏高失控: {len(ooc_high_lots)} 批次，平均良率 {yield_ooc_high:.3f}")
    print(f"    - 偏低失控: {len(ooc_low_lots)} 批次，平均良率 {yield_ooc_low:.3f}")
    print(f"  失控批次整体平均良率: {yield_ooc:.3f}")
    if yield_normal is not None:
        print(f"  正常批次平均良率: {yield_normal:.3f}")
        print(f"  良率差异: {yield_gap:.3f}（{yield_gap*100:.1f}pp）")
    else:
        print(f"  正常批次: 0（所有批次均失控，无法对比）")
    
    print(f"\n   关键洞察:")
    if yield_gap is not None:
        print(f"    失控批次良率反而更高（+{abs(yield_gap)*100:.1f}pp），说明参数-良率关系非单调。")
    else:
        print(f"    所有批次均失控，说明过程变异过大，需要 DOE 优化工艺窗口。")
    print(f"    传统 SPC（死守均值）不是最优策略，需要 DOE 找到更优工艺窗口。")
    print(f"    这正是 optimize.py 贝叶斯优化的价值：不追求'稳定在均值'，而是'找到最优'。")
    
    return {
        "n_ooc_lots": n_ooc_lots,
        "n_total_lots": n_total_lots,
        "ooc_rate": ooc_rate,
        "yield_ooc": yield_ooc,
        "yield_normal": yield_normal,
        "yield_gap": yield_gap,
        "n_ooc_high": len(ooc_high_lots),
        "n_ooc_low": len(ooc_low_lots),
    }


# ============================================================
# 函数 5：主流程
# ============================================================
def main():
    print("=" * 70)
    print("SPC 统计过程控制 + 过程能力分析")
    print("=" * 70)
    
    subgroups, n_lots = prepare_subgroups()
    
    print("\n===== 2. Xbar-R 控制图 =====")
    spc_results = []
    for param in KEY_PARAMS:
        res = xbar_r_chart(subgroups, param)
        spc_results.append(res)
        print(f"  {param}: Xbar_bar={res['Xbar_bar']:.3f}, "
              f"失控点={res['n_ooc']} ({res['ooc_rate']*100:.1f}%)")
    
    print("\n===== 3. 过程能力分析（Cp / Cpk / Pp / Ppk）=====")
    df = pd.read_csv(os.path.join(DATA, "semiconductor_yield_forecasting_data.csv"))
    cap_results = []
    for param in KEY_PARAMS:
        res = capability_analysis(df, param)
        cap_results.append(res)
        print(f"  {param}:")
        print(f"    Cp={res['Cp']:.2f} | Cpk={res['Cpk']:.2f} | Pp={res['Pp']:.2f} | Ppk={res['Ppk']:.2f}")
        print(f"    正态性检验: {res['normality_test']} p={res['p_value']:.3f} {'✓ 正态' if res['is_normal'] else '✗ 非正态'}")
        
        if res["Cpk"] < 1.0:
            status = "⚠ 过程能力不足，需改进"
        elif res["Cpk"] < 1.33:
            status = "⚡ 过程能力可接受，需监控"
        elif res["Cpk"] < 1.67:
            status = "✓ 过程能力充足"
        else:
            status = "✓✓ 过程能力优秀"
        print(f"    判标: {status}")
    
    ooc_res = ooc_analysis(df, spc_results)
    
    print("\n===== 业务闭环总结 =====")
    print(f"  1) SPC 控制图: {len(KEY_PARAMS)} 个关键参数已绘制 Xbar-R 图")
    print(f"  2) 过程能力: Cpk 范围 [{min(r['Cpk'] for r in cap_results):.2f}, "
          f"{max(r['Cpk'] for r in cap_results):.2f}]")
    yg = ooc_res['yield_gap']
    yg_str = f"可避免 {yg*100:.1f}pp 良率损失" if yg is not None else "所有批次均失控，需DOE优化"
    print(f"  3) 失控拦截: 提前 Hold {ooc_res['n_ooc_lots']} 批次，{yg_str}")
    print(f"  4) 与 DOE 闭环: 对 Cpk < 1.33 的参数做 DOE 寻优（optimize.py），"
          f"提升过程能力至 1.33 以上")
    
    print(f"\n  图表已保存至: {FIGURES}/")
    print(f"    spc_xbar_r_*.png（控制图）")
    print(f"    capability_*.png（过程能力图）")
    
    # 保存 SPC 分析结果到 JSON
    import json
    
    # 辅助函数：将 numpy 类型转换为 Python 原生类型
    def convert_numpy_types(obj):
        if isinstance(obj, dict):
            return {k: convert_numpy_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy_types(item) for item in obj]
        elif isinstance(obj, (np.bool_, np.bool)):
            return bool(obj)
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        else:
            return obj
    
    spc_summary = {
        "capability": [
            {
                "param": res["param"],
                "Cp": res["Cp"],
                "Cpk": res["Cpk"],
                "Pp": res["Pp"],
                "Ppk": res["Ppk"],
                "mu": res["mu"],
                "sigma_within": res["sigma_within"],
                "sigma_overall": res["sigma_overall"],
                "is_normal": res["is_normal"],
                "p_value": res["p_value"],
                "LSL": res["LSL"],
                "USL": res["USL"],
            }
            for res in cap_results
        ],
        "control_chart": [
            {
                "param": res["param"],
                "Xbar_bar": res["Xbar_bar"],
                "R_bar": res["R_bar"],
                "n_ooc": res["n_ooc"],
                "ooc_rate": res["ooc_rate"],
            }
            for res in spc_results
        ],
        "ooc_analysis": {
            "n_ooc_lots": ooc_res["n_ooc_lots"],
            "n_total_lots": ooc_res["n_total_lots"],
            "ooc_rate": ooc_res["ooc_rate"],
            "yield_ooc": ooc_res["yield_ooc"],
            "yield_normal": ooc_res["yield_normal"],
            "yield_gap": ooc_res["yield_gap"],
        }
    }
    
    # 转换 numpy 类型
    spc_summary = convert_numpy_types(spc_summary)
    
    spc_json_path = os.path.join(RESULT, "spc_results.json")
    with open(spc_json_path, "w", encoding="utf-8") as f:
        json.dump(spc_summary, f, indent=2, ensure_ascii=False)
    print(f"\n  SPC 结果已保存至: {spc_json_path}")


if __name__ == "__main__":
    main()
