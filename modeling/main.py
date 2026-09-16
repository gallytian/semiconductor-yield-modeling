# -*- coding: utf-8 -*-
"""
半导体晶圆良率建模分析（主项目）
===================================================
数据: data/semiconductor_yield_forecasting_data.csv（1250×28，产线 MES 系统采集）
任务:
  1) 良率回归：用工艺参数 + 机台信息预测 yield（R²/RMSE）
  2) 低良率识别：识别 yield<35% 的高风险批次（Top-k 拦截覆盖率）
  3) 根因分析：SHAP 定位驱动良率的关键工艺参数

设计要点:
  - 时间切分（前 80% → 后 20%），模拟"用过去预测未来"
  - 机台 one-hot：设备差异是良率的结构性因素（对应 MES/机台维度）
  - 回归 + 分类双任务：回归看精度，分类看业务拦截效果
  - SHAP 根因 → 输出"工艺语言"的监控清单
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (r2_score, mean_absolute_error, mean_squared_error,
                             roc_auc_score, average_precision_score)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 项目根目录（modeling/ 的父目录）
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
RESULT = os.path.join(BASE, "results")
FIGURES = os.path.join(BASE, "reports", "figures")
os.makedirs(RESULT, exist_ok=True)
os.makedirs(FIGURES, exist_ok=True)
SEED = 42
np.random.seed(SEED)

NUM_PARAMS = ["etch_rate", "pressure", "temperature", "exposure_time", "focus_offset",
              "dose", "deposition_rate", "thickness_uniformity", "implant_energy",
              "tilt_angle", "critical_dimension", "oxide_thickness", "resistivity",
              "defect_count", "defect_density", "vth", "leakage_current", "resistance"]
TOOLS = ["etch_tool", "litho_tool", "deposition_tool", "implant_tool"]
LOW_CUT = 0.35  # 低良率阈值


# ============================================================
# 1. 数据准备与特征工程
# ============================================================
def prepare():
    print("===== 1. 数据准备 =====")
    df = pd.read_csv(os.path.join(DATA, "semiconductor_yield_forecasting_data.csv"))
    # 按时间排序（时间切分的前提）
    df = df.sort_values("process_date").reset_index(drop=True)

    # 数值工艺参数
    X_num = df[NUM_PARAMS].astype(float)
    # 机台 one-hot（设备差异作为结构性特征）
    X_tool = pd.get_dummies(df[TOOLS], prefix="T")
    X = pd.concat([X_num, X_tool], axis=1)

    y_reg = df["yield"].values                      # 回归目标：良率
    y_cls = (df["yield"] < LOW_CUT).astype(int).values  # 分类目标：低良率
    n = len(df)
    cut = int(n * 0.8)
    print(f"  特征: {X.shape[1]}（18 数值参数 + {X_tool.shape[1]} 机台 dummy）")
    print(f"  切分: 训练 {cut} / 测试 {n-cut}（按时间 80/20）")
    print(f"  低良率(<{LOW_CUT}): {y_cls.sum()} 片 ({y_cls.mean()*100:.1f}%)")
    return X, y_reg, y_cls, cut


# ============================================================
# 2. 良率回归（XGBoost vs RandomForest）
# ============================================================
def regress(X, y, cut):
    print("\n===== 2. 良率回归 =====")
    X_tr, X_te = X.iloc[:cut], X.iloc[cut:]
    y_tr, y_te = y[:cut], y[cut:]

    from xgboost import XGBRegressor
    from sklearn.ensemble import RandomForestRegressor

    models = {
        "XGBoost": XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.05,
                                subsample=0.8, colsample_bytree=0.8,
                                random_state=SEED, verbosity=0),
        "RandomForest": RandomForestRegressor(n_estimators=400, max_depth=8,
                                              min_samples_leaf=3, random_state=SEED, n_jobs=-1),
    }
    results = {}
    for name, m in models.items():
        m.fit(X_tr, y_tr)
        p = m.predict(X_te)
        results[name] = {"model": m, "pred": p}
        r2 = r2_score(y_te, p)
        rmse = float(np.sqrt(mean_squared_error(y_te, p)))
        mae = mean_absolute_error(y_te, p)
        print(f"  {name:14s} R²={r2:.3f} | RMSE={rmse:.3f} | MAE={mae:.3f}")

    # 预测 vs 实际散点（用效果最好的模型）
    best = max(results, key=lambda k: r2_score(y_te, results[k]["pred"]))
    p = results[best]["pred"]
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(y_te, p, s=12, alpha=0.5, color="#3B6EA5")
    lim = [min(y_te.min(), p.min()), max(y_te.max(), p.max())]
    ax.plot(lim, lim, "--", color="#B23A48", lw=1.2, label="理想线 y=x")
    ax.set_xlabel("实际良率"); ax.set_ylabel("预测良率")
    ax.set_title(f"{best} 良率预测 vs 实际（测试集 R²={r2_score(y_te, p):.3f}）")
    ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(FIGURES, "pred_vs_actual.png"), dpi=150)
    plt.close(fig)
    return results, best


# ============================================================
# 3. 低良率识别（Top-k 拦截覆盖率，业务导向）
# ============================================================
def classify(X, y, cut):
    print("\n===== 3. 低良率识别（Top-k 拦截） =====")
    X_tr, X_te = X.iloc[:cut], X.iloc[cut:]
    y_tr, y_te = y[:cut], y[cut:]

    from xgboost import XGBClassifier
    neg, pos = int((y_tr == 0).sum()), max(1, int((y_tr == 1).sum()))
    clf = XGBClassifier(scale_pos_weight=neg / pos, eval_metric="aucpr",
                        n_estimators=400, max_depth=4, learning_rate=0.05,
                        subsample=0.8, colsample_bytree=0.8,
                        random_state=SEED, verbosity=0)
    clf.fit(X_tr, y_tr)
    prob = clf.predict_proba(X_te)[:, 1]

    roc = roc_auc_score(y_te, prob)
    pr = average_precision_score(y_te, prob)
    print(f"  XGBoost 低良率识别: ROC-AUC={roc:.3f} | PR-AUC={pr:.3f}")

    # Top-k 覆盖率：按风险分拦截 k% 批次能覆盖多少低良率
    yt = np.asarray(y_te)
    n_fail = max(1, int(yt.sum()))
    ks = [0.05, 0.10, 0.20, 0.30]
    covs = []
    for k in ks:
        cutk = max(1, int(len(yt) * k))
        top = np.argsort(prob)[::-1][:cutk]
        cov = yt[top].sum() / n_fail
        covs.append(cov)
        print(f"    Top{int(k*100)}% 拦截覆盖率 = {cov:.2f}（随机基线 {k:.2f}）")

    # Top-k 覆盖率曲线图
    ks_fine = [i / 100 for i in range(5, 101, 5)]
    cov_fine = []
    for k in ks_fine:
        cutk = max(1, int(len(yt) * k))
        top = np.argsort(prob)[::-1][:cutk]
        cov_fine.append(yt[top].sum() / n_fail)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([k * 100 for k in ks_fine], cov_fine, "-o", ms=3, color="#3B6EA5", label="模型")
    ax.plot([k * 100 for k in ks_fine], ks_fine, "--", color="#6B7280", label="随机基线")
    ax.axhline(1.0, color="#B23A48", lw=0.8, ls=":")
    ax.set_xlabel("拦截批次比例 %"); ax.set_ylabel("低良率覆盖率")
    ax.set_title("Top-k 拦截覆盖率曲线"); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(FIGURES, "topk_curve.png"), dpi=150)
    plt.close(fig)
    return clf, prob, yt


# ============================================================
# 4. SHAP 根因分析（用回归模型解释）
# ============================================================
def root_cause(best_model, X, cut):
    print("\n===== 4. SHAP 根因分析 =====")
    X_tr = X.iloc[:cut]
    X_sample = X_tr.iloc[:300]  # 用训练集前 300 行（省时且稳定）
    try:
        import shap
        explainer = shap.TreeExplainer(best_model)
        sv = explainer.shap_values(X_sample)
        if isinstance(sv, list):
            sv = sv[-1]
        if hasattr(sv, "ndim") and sv.ndim == 3:
            sv = sv[:, :, 0] if sv.shape[2] == 1 else sv.mean(axis=2)

        fig, ax = plt.subplots(figsize=(9, 7))
        shap.summary_plot(sv, X_sample, show=False, max_display=15)
        plt.title("SHAP 特征重要性（良率回归）")
        fig.savefig(os.path.join(FIGURES, "shap_summary.png"), dpi=150, bbox_inches="tight")
        plt.close(fig)

        mean_abs = np.abs(sv).mean(axis=0)
        top = np.argsort(mean_abs)[::-1][:10]
        print("  Top 特征（SHAP 平均绝对贡献）:")
        top_feats = []
        for i, idx in enumerate(top):
            feat = X_sample.columns[idx]
            top_feats.append(feat)
            print(f"    {i+1:2d}. {feat}  ({mean_abs[idx]:.4f})")
        return top_feats
    except Exception as e:
        print(f"  SHAP 失败（{type(e).__name__}: {e}），改用内置重要性")
        imp = best_model.feature_importances_
        top = np.argsort(imp)[::-1][:10]
        top_feats = [X_sample.columns[i] for i in top]
        print("  Top 特征（内置重要性）:", ", ".join(top_feats))
        return top_feats


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 64)
    print("半导体晶圆良率建模分析")
    print("=" * 64)
    X, y_reg, y_cls, cut = prepare()
    reg_results, best = regress(X, y_reg, cut)
    clf, prob, y_te = classify(X, y_cls, cut)
    top_feats = root_cause(reg_results[best]["model"], X, cut)

    print("\n===== 业务闭环 =====")
    print(f"  1) 良率预测：{best} 测试 R²={r2_score(y_reg[cut:], reg_results[best]['pred']):.3f}"
          f"，可用于工艺窗口监控与排产优先级")
    # 重算 Top20% 拦截覆盖率用于闭环输出
    yt = np.asarray(y_cls[cut:])
    n_fail = max(1, int(yt.sum()))
    cutk = max(1, int(len(yt) * 0.20))
    top = np.argsort(prob)[::-1][:cutk]
    cov20 = yt[top].sum() / n_fail
    print(f"  2) 低良率拦截：按风险分拦截 Top 20% 批次覆盖 {cov20:.2f} 的低良率"
          f"（随机基线 0.20，见 topk_curve.png）")
    print(f"  3) 根因 Top 参数: {', '.join(top_feats[:5])} → 纳入 FDC/SPC 监控")
    print(f"  4) 关键参数做 DOE + 贝叶斯优化（smart-process-optimizer 项目）找最优工艺窗口")
    print(f"\n  图表已保存至: {FIGURES}")


if __name__ == "__main__":
    main()
