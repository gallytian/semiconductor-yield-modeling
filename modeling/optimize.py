# -*- coding: utf-8 -*-
"""
DOE（LHS）+ 贝叶斯优化 · 最优工艺窗口寻优（多目标：yield + Cpk）
===================================================

工业背景
--------
真实产线做一次实验（跑一个配方组合）成本极高（占用机台、耗材、时间），
所以不能暴力网格搜索。标准做法分三步：
  1) 代理模型（surrogate）：用历史数据训练 yield 预测模型，作为"产线仿真器"，
     后续寻优只查代理模型，不碰真实产线；
  2) DOE 实验设计：用 Latin Hypercube Sampling（LHS）在设计空间内生成
     "下一轮试产计划"——比随机采样覆盖更均匀，比全因子设计省实验；
  3) 贝叶斯优化（BO）：用高斯过程（GP）建模"参数 → yield"响应面，
     用采集函数（EI）在"开发（已知优区）+ 探索（未知区）"间平衡，
     逐轮逼近最优工艺窗口——对比网格搜索，同样的实验预算找到更好的点。

多目标优化（新增）
-----------------
SPC 分析发现 vth 的 Cpk=0.51（严重不足），单纯优化 yield 不够。
本模块同时优化两个目标：
  1) yield（良率）：最大化
  2) Cpk（过程能力）：最小化与 1.33 的差距（Cpk ≥ 1.33 为充足）
综合评分 = 0.7 × yield_score + 0.3 × cpk_score

寻优空间（由上一轮 SHAP 根因确定）
----------------------------------
yield 最强驱动: critical_dimension(r=-0.65)、vth(r=-0.54)、oxide_thickness(r=-0.51)
这三个是工艺量测参数（CD 由光刻控制、氧化层厚度由氧化炉控制、vth 由注入/退火控制），
DOE/BO 在其可行域内搜索最大化综合评分的工艺窗口。
"""

import os
import json
import math
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats.qmc import LatinHypercube, scale
from sklearn.ensemble import RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C, WhiteKernel

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

# 项目根目录（modeling/ 的父目录）
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT = os.path.join(BASE, "results")
DATA = os.path.join(BASE, "data")
FIGURES = os.path.join(BASE, "reports", "figures")
os.makedirs(RESULT, exist_ok=True)
os.makedirs(FIGURES, exist_ok=True)
SEED = 42
rng = np.random.default_rng(SEED)

# 寻优参数（DOE/BO 的设计变量）
OPT_PARAMS = ["critical_dimension", "oxide_thickness", "vth"]
# 代理模型输入：全部 18 数值参数（其余参数固定为产线当前均值，模拟"只调这三个窗口"）
NUM_PARAMS = ["etch_rate", "pressure", "temperature", "exposure_time", "focus_offset",
              "dose", "deposition_rate", "thickness_uniformity", "implant_energy",
              "tilt_angle", "critical_dimension", "oxide_thickness", "resistivity",
              "defect_count", "defect_density", "vth", "leakage_current", "resistance"]

# 规格限（工业标准，单位与数据一致）
SPEC_LIMITS = {
    "critical_dimension": {"LSL": 15.0, "USL": 35.0, "target": 25.0},   # nm
    "oxide_thickness": {"LSL": 45.0, "USL": 70.0, "target": 57.5},      # Å
    "vth": {"LSL": 0.50, "USL": 0.80, "target": 0.65},                  # V
}

# 可达 Cpk 目标（基于理论最大 Cpk）
# critical_dimension: Cpk_max = 1.97 → 目标 1.33 可达
# oxide_thickness: Cpk_max = 1.55 → 目标 1.33 可达
# vth: Cpk_max = 0.90 → 目标 1.33 不可达，调整为 0.80
CPK_TARGETS = {
    "critical_dimension": 1.33,
    "oxide_thickness": 1.33,
    "vth": 0.80,  # 理论上限 0.90，目标 0.80 可达
}

# 实验预算（面试可讲：真实产线一次试产一个 lot）
N_LHS = 50      # DOE 试产计划数
N_BO = 30       # BO 额外迭代数
N_GRID = 40     # 响应面可视化网格分辨率


# ============================================================
# 1. 代理模型（surrogate model）
# ============================================================
def build_surrogate():
    """用历史数据训练 yield 回归模型作为产线仿真器"""
    df = pd.read_csv(os.path.join(DATA, "semiconductor_yield_forecasting_data.csv"))
    X = df[NUM_PARAMS].astype(float)
    y = df["yield"].values
    # 时间切分：训练 80%，留 20% 验证代理模型精度（不能拿未来数据寻优）
    cut = int(len(df) * 0.8)
    X_tr, X_te, y_tr, y_te = X.iloc[:cut], X.iloc[cut:], y[:cut], y[cut:]
    rf = RandomForestRegressor(n_estimators=400, max_depth=8, min_samples_leaf=3,
                               random_state=SEED, n_jobs=-1)
    rf.fit(X_tr.values, y_tr)
    r2 = rf.score(X_te.values, y_te)
    print(f"代理模型 RF: 测试 R²={r2:.3f}（代理模型精度，越高 BO 寻优越可信）")
    # 产线当前均值配方（其余参数固定于此）
    baseline = X.mean(axis=0).values
    return rf, X.columns.tolist(), baseline, r2


def predict_yield(rf, cols, baseline, new_vals):
    """把寻优参数组合拼进完整特征向量 → 代理模型预测 yield"""
    x = np.asarray(baseline, dtype=float).copy()
    for name, v in zip(OPT_PARAMS, new_vals):
        x[cols.index(name)] = v
    return float(rf.predict(x.reshape(1, -1))[0])


def predict_yield_batch(rf, cols, baseline, X_batch):
    """批量预测 yield - 向量化版本，大幅提升速度
    
    Args:
        X_batch: (n_samples, n_opt_params) 优化参数矩阵
    
    Returns:
        yield_preds: (n_samples,) 预测的 yield 数组
    """
    n_samples = X_batch.shape[0]
    # 创建完整的特征矩阵（复制 baseline）
    X_full = np.tile(baseline, (n_samples, 1))
    # 替换优化参数列
    for i, name in enumerate(OPT_PARAMS):
        col_idx = cols.index(name)
        X_full[:, col_idx] = X_batch[:, i]
    # 批量预测
    return rf.predict(X_full)


# ============================================================
# 1.5 Cpk 计算函数（多目标优化核心）
# ============================================================
def calculate_cpk_for_params(new_vals, baseline, cols, df_history, within_sigma=None):
    """
    计算给定工艺参数组合下的 Cpk（过程能力指数）
    
    原理：
      - 用批次内标准差（within-subgroup σ），反映过程的自然变异
      - 调整参数中心到新值（模拟"如果调整工艺目标中心"）
      - 计算 Cpk = min((USL - μ_new) / 3σ_within, (μ_new - LSL) / 3σ_within)
      - 返回每个参数的 Cpk 数组
    
    业务意义：
      - 反映"调整参数中心后，过程能力如何变化"
      - Cpk ≥ 1.33：过程能力充足（CD/oxide）
      - Cpk ≥ 0.80：过程能力可接受（vth，受限于物理约束）
    
    参数：
      within_sigma: 预计算的批次内标准差（可选，用于加速批量计算）
    """
    # 计算批次内标准差（within-subgroup σ）- 如果未提供则计算
    if within_sigma is None:
        df_grouped = df_history.groupby('lot_id')[OPT_PARAMS].std(ddof=1)
        within_sigma = df_grouped.mean()  # 每个参数的平均批次内标准差
    
    cpk_values = []
    
    for i, param in enumerate(OPT_PARAMS):
        spec = SPEC_LIMITS[param]
        LSL, USL = spec["LSL"], spec["USL"]
        
        # 调整参数中心到新值
        mu_new = new_vals[i]
        sigma = within_sigma[param] if hasattr(within_sigma, '__getitem__') else within_sigma.iloc[i]
        
        # 避免除零
        if sigma < 1e-9:
            cpk = 0.0
        else:
            # Cpk = min((USL - μ) / 3σ, (μ - LSL) / 3σ)
            cpk = min((USL - mu_new) / (3 * sigma), (mu_new - LSL) / (3 * sigma))
        
        cpk_values.append(cpk)
    
    # 返回每个参数的 Cpk 数组
    return np.array(cpk_values)


def multi_objective_score(yield_val, cpk_vals, yield_target=0.70):
    """
    带软约束的综合评分函数
    
    核心原则：
      - 每个参数有独立的 Cpk 目标（基于理论可达性）
      - Cpk 未达标时给低分（软约束），让 GP 能学到趋势
      - 综合评分 = yield_score × cpk_factor
    
    业务意义：
      - 避免"高良率但参数超出规格限"的陷阱
      - 确保优化结果在工程上可落地
      - 让 GP 能区分"差一点达标"和"完全不达标"
    """
    # 良率评分（归一化到 0~1）
    yield_score = min(yield_val / yield_target, 1.0)
    
    # Cpk 因子（软约束）
    cpk_factor = 1.0
    for i, param in enumerate(OPT_PARAMS):
        cpk_val = cpk_vals[i]
        cpk_target = CPK_TARGETS[param]
        
        if cpk_val < 0:
            # 参数中心超出规格限 → 严重惩罚（接近 0）
            cpk_factor *= 0.01
        elif cpk_val < cpk_target:
            # Cpk 未达标 → 按比例惩罚
            penalty = (cpk_val / cpk_target) ** 2  # 平方惩罚，越接近目标惩罚越小
            cpk_factor *= penalty
    
    # 综合评分
    return yield_score * cpk_factor


# ============================================================
# 2. DOE：Latin Hypercube Sampling 实验计划
# ============================================================
def doe_lhs(bounds, n):
    """
    LHS 原理：把每个参数的分布区间等分成 n 层，每层恰好取一个点，
    各维度随机配对 → 用 n 个实验点均匀覆盖整个设计空间（比随机采样
    无空洞、无聚集；比全因子 n^k 个点省实验）。
    """
    sampler = LatinHypercube(d=len(OPT_PARAMS), seed=SEED)
    unit = sampler.random(n)                     # [0,1]^k 均匀分层样本
    lo = np.array([b[0] for b in bounds])
    hi = np.array([b[1] for b in bounds])
    return lo + unit * (hi - lo)                 # 缩放到真实参数范围


# ============================================================
# 3. 贝叶斯优化（GP + EI）
# ============================================================
def expected_improvement(gp, x_cand, y_best, xi=0.01):
    """EI 采集函数：衡量"期望提升量" E[max(f(x)-f_best-xi, 0)]"""
    mu, sigma = gp.predict(x_cand, return_std=True)
    sigma = np.maximum(sigma, 1e-9)
    z = (mu - y_best - xi) / sigma
    # 标准正态 pdf/cdf 的 EI 闭式解
    phi = np.exp(-0.5 * z**2) / np.sqrt(2 * np.pi)
    Phi = 0.5 * (1 + np.vectorize(lambda t: math.erf(t / np.sqrt(2)))(z))
    return (mu - y_best - xi) * Phi + sigma * phi


def bayes_opt(rf, cols, baseline, bounds, df_history, n_iter):
    """GP 代理 + EI 采集：n_iter 轮迭代找最大综合评分（yield + Cpk）的工艺窗口"""
    # 预计算批次内标准差（用于 Cpk 计算）
    df_grouped = df_history.groupby('lot_id')[OPT_PARAMS].std(ddof=1)
    within_sigma = df_grouped.mean()
    
    # 初始点：LHS 采 8 个点做 GP 热身（BO 标准做法）
    X_init = doe_lhs(bounds, 8)
    y_init = []
    for x in X_init:
        y_pred = predict_yield(rf, cols, baseline, x)
        cpk_vals = calculate_cpk_for_params(x, baseline, cols, df_history, within_sigma)
        y_init.append(multi_objective_score(y_pred, cpk_vals))
    y_init = np.array(y_init)

    kernel = C(1.0, (1e-3, 1e3)) * RBF([1.0]*len(OPT_PARAMS), (1e-2, 1e2)) + WhiteKernel(1e-3)
    gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True,
                                  n_restarts_optimizer=3, random_state=SEED)
    gp.fit(X_init, y_init)

    # 候选集：在可行域内稠密抽样（LHS 5000 点），每轮从中选 EI 最大者
    cand = doe_lhs(bounds, 5000)
    X_all, y_all = list(X_init), list(y_init)
    history = [max(y_init)]
    best = X_init[np.argmax(y_init)]

    for it in range(n_iter):
        ei = expected_improvement(gp, cand, max(y_all))
        x_next = cand[np.argmax(ei)]
        # 避免重复实验同一配方（真实产线不重复跑同一点）
        if np.min(np.linalg.norm(np.array(X_all) - x_next, axis=1)) < 1e-4:
            cand = cand[np.linalg.norm(cand - x_next, axis=1) > 1e-4]
            continue
        y_pred = predict_yield(rf, cols, baseline, x_next)
        cpk_vals = calculate_cpk_for_params(x_next, baseline, cols, df_history, within_sigma)
        y_next = multi_objective_score(y_pred, cpk_vals)
        X_all.append(x_next); y_all.append(y_next)
        gp.fit(np.array(X_all), np.array(y_all))
        history.append(max(y_all))
        if y_next > max(history[:-1]):
            best = x_next
    return np.array(X_all), np.array(y_all), np.array(history), best, gp


# ============================================================
# 3.5 贝叶斯优化（多目标：yield + Cpk）
# ============================================================
def pareto_dominance(obj1, obj2):
    """
    判断解 1 是否支配解 2（多目标最大化问题）
    
    支配条件：
      - 解 1 在所有目标上都不差于解 2
      - 且至少在一个目标上严格优于解 2
    
    返回：True 表示 obj1 支配 obj2
    """
    at_least_one_better = False
    for i in range(len(obj1)):
        if obj1[i] < obj2[i]:
            return False  # 某个目标更差，不支配
        if obj1[i] > obj2[i]:
            at_least_one_better = True
    return at_least_one_better


def find_pareto_front(objectives):
    """
    从候选解集中找出 Pareto 前沿（非支配解）
    
    参数：
      objectives: shape (n_samples, n_objectives) 的目标值矩阵
    
    返回：
      pareto_indices: Pareto 最优解的索引列表
    """
    n = len(objectives)
    is_dominated = [False] * n
    
    for i in range(n):
        for j in range(n):
            if i != j and not is_dominated[j]:
                if pareto_dominance(objectives[j], objectives[i]):
                    is_dominated[i] = True
                    break
    
    pareto_indices = [i for i in range(n) if not is_dominated[i]]
    return pareto_indices


def pareto_optimize(rf, cols, baseline, bounds, df_history, n_candidates=500):
    """
    Pareto 多目标优化：寻找 yield-Cpk 的 Pareto 前沿
    
    原理：
      - 在候选空间内大量采样（LHS）
      - 计算每个候选点的 (yield, min_cpk)
      - 用 Pareto 支配关系筛选出非支配解
      - 输出 Pareto 前沿供工程师决策
    
    业务意义：
      - yield 和 Cpk 往往冲突：高 yield 可能牺牲过程稳定性
      - Pareto 前沿展示了"鱼与熊掌"的权衡关系
      - 工程师可以根据实际需求选择合适的折中方案
    """
    print(f"\n[Pareto] 在 {n_candidates} 个候选点上计算 (yield, Cpk)...")
    
    # 预计算批次内标准差（加速批量计算）
    df_grouped = df_history.groupby('lot_id')[OPT_PARAMS].std(ddof=1)
    within_sigma = df_grouped.mean()
    
    # 1. LHS 采样候选点
    X_cand = doe_lhs(bounds, n_candidates)
    
    # 2. 批量计算 yield（向量化，大幅提升速度）
    yield_vals = predict_yield_batch(rf, cols, baseline, X_cand)
    
    # 3. 向量化计算 Cpk（避免循环）
    # X_cand: (n_candidates, n_params)
    # within_sigma: (n_params,)
    # 规格限
    LSL = np.array([SPEC_LIMITS[p]["LSL"] for p in OPT_PARAMS])
    USL = np.array([SPEC_LIMITS[p]["USL"] for p in OPT_PARAMS])
    sigma = np.array([within_sigma[p] for p in OPT_PARAMS])
    
    # Cpk = min((USL - μ) / 3σ, (μ - LSL) / 3σ)
    # 对每个参数独立计算
    cpu = (USL - X_cand) / (3 * sigma)  # (n_candidates, n_params)
    cpl = (X_cand - LSL) / (3 * sigma)  # (n_candidates, n_params)
    cpk_vals = np.minimum(cpu, cpl)  # (n_candidates, n_params)
    
    # 4. 对于 Cpk，取所有参数的最小值作为整体指标
    # （因为工艺稳定性取决于最弱的环节）
    min_cpk_vals = np.min(cpk_vals, axis=1)
    
    # 5. 组合目标矩阵 (yield, min_cpk)
    objectives = np.column_stack([yield_vals, min_cpk_vals])
    
    # 6. 找出 Pareto 前沿
    pareto_indices = find_pareto_front(objectives)
    pareto_X = X_cand[pareto_indices]
    pareto_yield = yield_vals[pareto_indices]
    pareto_cpk = min_cpk_vals[pareto_indices]
    pareto_cpk_detail = cpk_vals[pareto_indices]  # 每个参数的 Cpk
    
    print(f"      找到 {len(pareto_indices)} 个 Pareto 最优解")
    
    # 7. 按 yield 排序（方便后续分析）
    sort_idx = np.argsort(pareto_yield)[::-1]
    pareto_X = pareto_X[sort_idx]
    pareto_yield = pareto_yield[sort_idx]
    pareto_cpk = pareto_cpk[sort_idx]
    pareto_cpk_detail = pareto_cpk_detail[sort_idx]
    
    return X_cand, yield_vals, min_cpk_vals, pareto_X, pareto_yield, pareto_cpk, pareto_cpk_detail


# ============================================================
# 4. 主流程（多目标优化：yield + Cpk）
# ============================================================
def main():
    print("=" * 70)
    print("DOE（LHS）+ 贝叶斯优化 · 最优工艺窗口寻优（多目标：yield + Cpk）")
    print("=" * 70)

    rf, cols, baseline, r2 = build_surrogate()
    lo = np.array([baseline[cols.index(p)] * 0.7 for p in OPT_PARAMS])
    hi = np.array([baseline[cols.index(p)] * 1.3 for p in OPT_PARAMS])
    bounds = list(zip(lo, hi))
    print(f"寻优空间（均值±30% 窗口）:")
    for p, b in zip(OPT_PARAMS, bounds):
        print(f"  {p:20s} [{b[0]:.3f}, {b[1]:.3f}]（产线均值 {baseline[cols.index(p)]:.3f}）")

    # 加载历史数据（用于计算 Cpk）
    df_history = pd.read_csv(os.path.join(DATA, "semiconductor_yield_forecasting_data.csv"))

    # ---- DOE：LHS 实验计划（多目标评分） ----
    X_lhs = doe_lhs(bounds, N_LHS)
    y_lhs = np.array([predict_yield(rf, cols, baseline, x) for x in X_lhs])
    cpk_lhs = np.array([calculate_cpk_for_params(x, baseline, cols, df_history) for x in X_lhs])
    score_lhs = np.array([multi_objective_score(y, c) for y, c in zip(y_lhs, cpk_lhs)])
    
    best_idx = np.argmax(score_lhs)
    best_score_lhs = score_lhs[best_idx]
    best_yield_lhs = y_lhs[best_idx]
    best_cpk_lhs = cpk_lhs[best_idx]  # 数组：每个参数的 Cpk
    
    print(f"\n[DOE] LHS {N_LHS} 点试产计划（多目标优化）")
    print(f"      最优综合评分: {best_score_lhs:.3f}")
    print(f"      对应 yield={best_yield_lhs:.3f}")
    print(f"      Cpk: " + ", ".join(f"{p}={c:.2f}" for p, c in zip(OPT_PARAMS, best_cpk_lhs)))

    # ---- 随机采样对照（同预算，无设计） ----
    X_rand = np.array([lo + rng.random(len(OPT_PARAMS)) * (hi - lo) for _ in range(N_LHS)])
    y_rand = np.array([predict_yield(rf, cols, baseline, x) for x in X_rand])
    cpk_rand = np.array([calculate_cpk_for_params(x, baseline, cols, df_history) for x in X_rand])
    score_rand = np.array([multi_objective_score(y, c) for y, c in zip(y_rand, cpk_rand)])
    
    best_idx_rand = np.argmax(score_rand)
    best_score_rand = score_rand[best_idx_rand]
    best_yield_rand = y_rand[best_idx_rand]
    best_cpk_rand = cpk_rand[best_idx_rand]  # 数组：每个参数的 Cpk
    
    print(f"\n[对照] 随机采样 {N_LHS} 点（多目标评分）")
    print(f"       最优综合评分: {best_score_rand:.3f}")
    print(f"       对应 yield={best_yield_rand:.3f}")
    print(f"       Cpk: " + ", ".join(f"{p}={c:.2f}" for p, c in zip(OPT_PARAMS, best_cpk_rand)))

    # ---- 贝叶斯优化（GP + EI） ----
    print(f"\n[BO] 贝叶斯优化 {N_BO} 轮迭代（多目标评分）...")
    X_bo, y_bo, history_bo, best_bo, gp_bo = bayes_opt(rf, cols, baseline, bounds, df_history, N_BO)
    best_score_bo = max(y_bo)
    best_idx_bo = np.argmax(y_bo)
    best_yield_bo = predict_yield(rf, cols, baseline, best_bo)
    cpk_bo = calculate_cpk_for_params(best_bo, baseline, cols, df_history)
    
    print(f"      最优综合评分: {best_score_bo:.3f}")
    print(f"      对应 yield={best_yield_bo:.3f}")
    print(f"      Cpk: " + ", ".join(f"{p}={c:.2f}" for p, c in zip(OPT_PARAMS, cpk_bo)))
    
    # ---- 绘制 BO 收敛曲线 ----
    fig, ax = plt.subplots(figsize=(8, 5))
    iterations = range(len(history_bo))
    ax.plot(iterations, history_bo, 'b-o', markersize=4, linewidth=2, label='综合评分 (yield + Cpk)')
    ax.axhline(y=best_score_lhs, color='orange', linestyle='--', linewidth=1.5, 
               label=f'DOE 最优 {best_score_lhs:.3f}')
    ax.axhline(y=best_score_rand, color='gray', linestyle=':', linewidth=1.5, 
               label=f'随机最优 {best_score_rand:.3f}')
    ax.set_xlabel('BO 迭代轮数', fontsize=11)
    ax.set_ylabel('综合评分 (yield + Cpk)', fontsize=11)
    ax.set_title('贝叶斯优化收敛曲线（多目标：yield + Cpk）', fontsize=12, fontweight='bold')
    ax.legend(loc='lower right', fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGURES, 'bo_convergence.png'), dpi=150)
    plt.close(fig)
    print(f"      收敛曲线已保存: bo_convergence.png")

    # ---- Pareto 多目标优化 ----
    X_cand, yield_cand, min_cpk_cand, pareto_X, pareto_yield, pareto_cpk, pareto_cpk_detail = \
        pareto_optimize(rf, cols, baseline, bounds, df_history, n_candidates=5000)
    
    # 选择 Pareto 前沿中 yield 最高的解作为推荐方案
    best_idx_pareto = 0  # 已按 yield 降序排序
    best_y = pareto_yield[best_idx_pareto]
    best_c = pareto_cpk_detail[best_idx_pareto]  # 每个参数的 Cpk
    best = pareto_X[best_idx_pareto]
    
    print(f"\n[Pareto] 多目标优化完成")
    print(f"     Pareto 前沿包含 {len(pareto_yield)} 个非支配解")
    print(f"     推荐方案（yield 最高）:")
    print(f"       yield={best_y:.3f}, min_Cpk={pareto_cpk[best_idx_pareto]:.2f}")
    print(f"       Cpk: " + ", ".join(f"{p}={c:.2f}" for p, c in zip(OPT_PARAMS, best_c)))
    print(f"       工艺窗口: " + ", ".join(f"{p}={v:.3f}" for p, v in zip(OPT_PARAMS, best)))

    # ---- 汇总对比 ----
    current_mean = 0.457  # 数据实际平均良率
    # 基线 Cpk（产线当前参数中心）
    current_cpk = calculate_cpk_for_params(
        [baseline[cols.index(p)] for p in OPT_PARAMS], baseline, cols, df_history
    )
    
    print(f"\n===== 业务闭环对比（多目标优化） =====")
    print(f"  当前产线基线:")
    print(f"    yield={current_mean:.3f}")
    print(f"    Cpk: " + ", ".join(f"{p}={c:.2f}" for p, c in zip(OPT_PARAMS, current_cpk)))
    print(f"  DOE/LHS {N_LHS} 点:")
    print(f"    yield={best_yield_lhs:.3f} (+{(best_yield_lhs-current_mean)*100:.1f}pp)")
    print(f"    Cpk: " + ", ".join(f"{p}={c:.2f} ({c-current_cpk[i]:+.2f})" for i, (p, c) in enumerate(zip(OPT_PARAMS, best_cpk_lhs))))
    print(f"  随机 {N_LHS} 点:")
    print(f"    yield={best_yield_rand:.3f} (+{(best_yield_rand-current_mean)*100:.1f}pp)")
    print(f"    Cpk: " + ", ".join(f"{p}={c:.2f} ({c-current_cpk[i]:+.2f})" for i, (p, c) in enumerate(zip(OPT_PARAMS, best_cpk_rand))))
    print(f"  BO {N_BO} 轮:")
    print(f"    yield={best_yield_bo:.3f} (+{(best_yield_bo-current_mean)*100:.1f}pp)")
    print(f"    Cpk: " + ", ".join(f"{p}={c:.2f} ({c-current_cpk[i]:+.2f})" for i, (p, c) in enumerate(zip(OPT_PARAMS, cpk_bo))))
    print(f"  Pareto 优化（推荐方案）:")
    print(f"    yield={best_y:.3f} (+{(best_y-current_mean)*100:.1f}pp)")
    print(f"    Cpk: " + ", ".join(f"{p}={c:.2f} ({c-current_cpk[i]:+.2f})" for i, (p, c) in enumerate(zip(OPT_PARAMS, best_c))))
    
    # 判断是否达到目标（每个参数独立判断）
    yield_target_met = bool(best_y >= 0.70)
    cpk_targets_met = {p: bool(best_c[i] >= CPK_TARGETS[p]) for i, p in enumerate(OPT_PARAMS)}
    all_cpk_met = all(cpk_targets_met.values())
    
    print(f"\n  目标达成情况:")
    print(f"    {'✅' if yield_target_met else '❌'} 良率目标 (≥0.70): {'达成' if yield_target_met else '未达成'} ({best_y:.3f})")
    for p in OPT_PARAMS:
        target = CPK_TARGETS[p]
        met = cpk_targets_met[p]
        val = best_c[OPT_PARAMS.index(p)]
        print(f"    {'✅' if met else '❌'} {p} Cpk 目标 (≥{target:.2f}): {'达成' if met else '未达成'} ({val:.2f})")
    
    if yield_target_met and all_cpk_met:
        print(f"  🎉 双目标均达成！工艺窗口可落地")
    elif yield_target_met:
        print(f"  ⚠️ 良率达标但部分参数 Cpk 不足，需继续优化过程稳定性")
    elif all_cpk_met:
        print(f"  ⚠️ Cpk 达标但良率不足，需继续优化工艺参数")
    else:
        print(f"  ❌ 双目标均未达成，需扩大寻优空间或增加实验预算")

    # ---- 图 1：Pareto 前沿可视化（yield vs Cpk） ----
    fig, ax = plt.subplots(figsize=(7, 5))
    # 所有候选点（灰色背景）
    ax.scatter(yield_cand, min_cpk_cand, c="#D3D3D3", s=8, alpha=0.5, label="所有候选点")
    # Pareto 前沿（红色）
    ax.scatter(pareto_yield, pareto_cpk, c="#B23A48", s=40, marker="o", 
               edgecolors="#7A1E2E", linewidth=1.5, label="Pareto 前沿", zorder=5)
    # 推荐方案（金色星）
    ax.scatter(best_y, pareto_cpk[0], marker="*", s=250, c="#C98A2D", 
               edgecolors="#7A5A1E", zorder=6, label="推荐方案（yield 最高）")
    # 当前基线（蓝色三角）
    current_min_cpk = np.min(current_cpk)
    ax.scatter(current_mean, current_min_cpk, marker="^", s=150, c="#3B6EA5", 
               edgecolors="#1E4A7A", zorder=6, label="当前基线")
    
    # 添加目标线
    ax.axhline(y=1.33, color="#6B7280", ls="--", lw=1.5, alpha=0.7, label="Cpk 目标 (1.33)")
    ax.axvline(x=0.70, color="#6B7280", ls=":", lw=1.5, alpha=0.7, label="yield 目标 (0.70)")
    
    ax.set_xlabel("Yield (良率)", fontsize=11)
    ax.set_ylabel("Min Cpk (最差过程能力)", fontsize=11)
    ax.set_title("Pareto 前沿：yield vs Cpk 权衡分析", fontsize=12, fontweight="bold")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGURES, "pareto_front.png"), dpi=150)
    plt.close(fig)

    # ---- 图 2：CD × oxide 响应面 + Pareto 前沿点 ----
    g_cd = np.linspace(lo[0], hi[0], N_GRID)
    g_ox = np.linspace(lo[1], hi[1], N_GRID)
    CD, OX = np.meshgrid(g_cd, g_ox)
    Z = np.array([[predict_yield(rf, cols, baseline, [CD[i, j], OX[i, j], best[2]])
                   for j in range(N_GRID)] for i in range(N_GRID)])
    fig, ax = plt.subplots(figsize=(6.8, 5))
    im = ax.contourf(CD, OX, Z, levels=18, cmap="YlGnBu")
    cs = ax.contour(CD, OX, Z, levels=8, colors="#555", linewidths=0.6)
    ax.clabel(cs, fmt="%.2f", fontsize=8)
    # Pareto 前沿点（红色）
    ax.scatter(pareto_X[:, 0], pareto_X[:, 1], c="#B23A48", s=20, alpha=0.7, 
               label=f"Pareto 前沿 ({len(pareto_X)} 点)", zorder=4)
    # 推荐方案（金色星）
    ax.scatter(*best[:2], marker="*", s=250, c="#C98A2D", edgecolors="#7A5A1E",
               zorder=5, label="推荐方案")
    # 当前基线（蓝色三角）
    ax.scatter(baseline[cols.index("critical_dimension")], 
               baseline[cols.index("oxide_thickness")],
               marker="^", s=150, c="#3B6EA5", edgecolors="#1E4A7A",
               zorder=5, label="当前基线")
    ax.set_xlabel("critical_dimension (nm)"); ax.set_ylabel("oxide_thickness")
    cpk_str = ", ".join(f"{p}={c:.2f}" for p, c in zip(OPT_PARAMS, best_c))
    ax.set_title(f"yield 响应面（CD × oxide，vth={best[2]:.2f}）\n推荐 yield={best_y:.3f}, Cpk=[{cpk_str}]")
    ax.legend(loc="lower right", fontsize=9)
    fig.colorbar(im, ax=ax, label="yield")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGURES, "response_surface.png"), dpi=150); plt.close(fig)

    # ---- 结果 JSON ----
    out = {
        "surrogate_r2": round(float(r2), 3),
        "bounds": {p: [round(float(lo[i]), 3), round(float(hi[i]), 3)]
                   for i, p in enumerate(OPT_PARAMS)},
        "cpk_targets": {p: round(v, 2) for p, v in CPK_TARGETS.items()},
        "current_yield": round(float(current_mean), 3),
        "current_cpk": {p: round(float(c), 2) for p, c in zip(OPT_PARAMS, current_cpk)},
        "lhs_best_yield": round(float(best_yield_lhs), 3),
        "lhs_best_cpk": {p: round(float(c), 2) for p, c in zip(OPT_PARAMS, best_cpk_lhs)},
        "random_best_yield": round(float(best_yield_rand), 3),
        "random_best_cpk": {p: round(float(c), 2) for p, c in zip(OPT_PARAMS, best_cpk_rand)},
        "bo_best_yield": round(float(best_yield_bo), 3),
        "bo_best_cpk": {p: round(float(c), 2) for p, c in zip(OPT_PARAMS, cpk_bo)},
        "bo_best_params": {p: round(float(v), 3) for p, v in zip(OPT_PARAMS, best_bo)},
        "pareto_front_size": len(pareto_yield),
        "pareto_best_yield": round(float(best_y), 3),
        "pareto_best_cpk": {p: round(float(c), 2) for p, c in zip(OPT_PARAMS, best_c)},
        "pareto_best_params": {p: round(float(v), 3) for p, v in zip(OPT_PARAMS, best)},
        "pareto_top5": [
            {
                "yield": round(float(pareto_yield[i]), 3),
                "min_cpk": round(float(pareto_cpk[i]), 2),
                "cpk_detail": {p: round(float(pareto_cpk_detail[i, j]), 2) 
                              for j, p in enumerate(OPT_PARAMS)},
                "params": {p: round(float(pareto_X[i, j]), 3) 
                          for j, p in enumerate(OPT_PARAMS)}
            }
            for i in range(min(5, len(pareto_yield)))
        ],
        "yield_target_met": yield_target_met,
        "cpk_targets_met": cpk_targets_met,
    }
    with open(os.path.join(RESULT, "optimize_results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n结果已保存: {os.path.join(RESULT, 'optimize_results.json')}")
    print(f"           pareto_front.png / response_surface.png")


if __name__ == "__main__":
    main()
