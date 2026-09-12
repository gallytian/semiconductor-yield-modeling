# 半导体晶圆良率分析与工艺优化系统

> 基于机器学习的半导体制造良率预测、根因分析与工艺参数优化平台

## 项目概述

### 业务背景

半导体制造过程中，良率损失是影响成本与产能的核心因素。工艺参数漂移、机台差异、环境波动等因素会导致良率波动，需要提前识别低良率风险批次并定位根因参数，进而通过工艺优化提升良率。

### 项目目标

1. **良率预测**：基于工艺参数与机台信息，构建良率回归模型，预测晶圆良率
2. **风险识别**：构建低良率风险识别模型，提前拦截高风险批次
3. **根因分析**：通过 SHAP 定位影响良率的关键工艺参数
4. **过程监控**：对关键参数实施 SPC 统计过程控制，监控过程稳定性与能力
5. **工艺优化**：通过 DOE 实验设计与贝叶斯优化，寻找最优工艺窗口

### 数据规模

- **数据来源**：产线 MES 系统采集（晶圆级量测数据）
- **数据量**：1250 片晶圆 × 28 列特征
- **特征构成**：18 个工艺/电测参数 + 4 个机台标识 + 5 个工艺节点 + 批次信息
- **时间跨度**：50 个批次（按时间顺序排列）

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      数据输入层                              │
│  semiconductor_yield_forecasting_data.csv (1250×28)         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   模块 1：良率建模 (main.py)                 │
│  • 特征工程：机台 one-hot 编码、时间切分（防数据泄漏）        │
│  • 回归模型：RandomForest (R²=0.624) / XGBoost (R²=0.591)  │
│  • 分类模型：低良率风险识别 (ROC-AUC=0.887)                 │
│  • 根因分析：SHAP 特征重要性（CD 重要性 64%）               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              模块 2：过程控制 (spc_analysis.py)              │
│  • Xbar-R 控制图：监控关键参数稳定性（失控点识别）           │
│  • 过程能力分析：Cp/Cpk/Pp/Ppk 计算与判标                  │
│  • 失控批次分析：FDC 自动 Hold 逻辑模拟                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              模块 3：工艺优化 (optimize.py)                  │
│  • 代理模型：RandomForest 作为"产线仿真器"                  │
│  • DOE 实验设计：Latin Hypercube Sampling (50 点)           │
│  • 贝叶斯优化：高斯过程 + Expected Improvement (38 次迭代)  │
│  • 最优窗口：CD=17.8nm / oxide=63.7 / vth=0.45             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      输出层                                  │
│  • 可视化报告：HTML 交互式报告、PNG 图表                    │
│  • 结构化数据：JSON 统计指标、CSV 实验设计                  │
│  • 业务指标：良率提升 +24.5pp、试产成本 -24%                │
└─────────────────────────────────────────────────────────────┘
```

## 项目结构

```
semiconductor-yield-modeling/
├── main.py                 # 良率建模主程序（回归 + 分类 + SHAP 根因）
├── spc_analysis.py         # SPC 过程控制（Xbar-R 控制图 + Cpk/Ppk）
├── optimize.py             # DOE + 贝叶斯优化（工艺参数寻优）
├── requirements.txt        # Python 依赖清单
├── README.md               # 项目文档
├── data/
│   └── semiconductor_yield_forecasting_data.csv   # 原始数据（1250×28）
└── results/
    ├── semiconductor_yield_analysis.html  # 数据分析报告（EDA）
    ├── semiconductor_stats.json           # 统计指标汇总
    ├── pred_vs_actual.png                 # 良率预测 vs 实际散点图
    ├── topk_curve.png                     # Top-k 拦截覆盖率曲线
    ├── shap_summary.png                   # SHAP 特征重要性图
    ├── spc_xbar_r_critical_dimension.png  # CD 的 Xbar-R 控制图
    ├── spc_xbar_r_oxide_thickness.png     # oxide 的 Xbar-R 控制图
    ├── spc_xbar_r_vth.png                 # vth 的 Xbar-R 控制图
    ├── capability_critical_dimension.png  # CD 过程能力直方图
    ├── capability_oxide_thickness.png     # oxide 过程能力直方图
    ├── capability_vth.png                 # vth 过程能力直方图
    ├── spc_analysis.html                  # SPC 交互式分析报告
    ├── bo_convergence.png                 # 贝叶斯优化收敛曲线
    ├── response_surface.png               # 响应面图（CD × oxide）
    └── optimize_results.json              # 优化结果
```

## 环境配置

### 依赖安装

```bash
pip install -r requirements.txt
```

### 依赖清单

```
numpy>=1.26
pandas>=2.0
scipy>=1.11
scikit-learn>=1.3
xgboost>=2.0
shap>=0.44
matplotlib>=3.7
seaborn>=0.13
imbalanced-learn>=0.11
```

### 运行环境

- Python 3.10+
- 操作系统：Windows / Linux / macOS
- 内存：≥8GB（SHAP 计算需要较大内存）

## 运行流程

### 步骤 1：良率建模与根因分析

```bash
python main.py
```

**功能**：
- 数据预处理：时间切分（80/20）、机台 one-hot 编码
- 回归建模：RandomForest / XGBoost，评估 R²、RMSE
- 分类建模：低良率风险识别（yield < 0.35），评估 ROC-AUC、PR-AUC
- 拦截分析：Top-k 覆盖率（Top 5%/10%/20%/30%）
- 根因分析：SHAP 特征重要性，定位良率主导参数

**输出**：
- `results/pred_vs_actual.png`：良率预测 vs 实际散点图
- `results/topk_curve.png`：Top-k 拦截覆盖率曲线
- `results/shap_summary.png`：SHAP 特征重要性图
- `results/semiconductor_stats.json`：统计指标汇总

### 步骤 2：SPC 过程控制

```bash
python spc_analysis.py
```

**功能**：
- 数据分组：按批次（lot_id）分组，每组 25 片晶圆
- Xbar-R 控制图：监控关键参数（CD/oxide/vth）的稳定性
- 过程能力分析：计算 Cp/Cpk/Pp/Ppk，判断过程能力是否达标
- 失控点识别：识别超出控制限的批次，模拟 FDC 自动 Hold 逻辑
- 良率对比：对比失控批次与正常批次的良率差异

**输出**：
- `results/spc_xbar_r_*.png`：3 个参数的 Xbar-R 控制图（6 张）
- `results/capability_*.png`：3 个参数的过程能力直方图（3 张）
- `results/spc_analysis.html`：SPC 交互式分析报告

### 步骤 3：工艺参数优化

```bash
python optimize.py
```

**功能**：
- 代理模型：训练 RandomForest 作为"产线仿真器"（R²=0.623）
- DOE 实验设计：Latin Hypercube Sampling 生成 50 个初始实验点
- 贝叶斯优化：高斯过程回归 + Expected Improvement 采集函数，迭代 38 次
- 最优窗口：寻找使良率最大化的工艺参数组合

**输出**：
- `results/bo_convergence.png`：贝叶斯优化收敛曲线
- `results/response_surface.png`：响应面图（CD × oxide）
- `results/optimize_results.json`：优化结果（最优参数、良率提升）

## 技术指标

### 良率建模

| 指标 | 数值 | 说明 |
|------|------|------|
| 回归 R² | 0.624 | RandomForest 测试集决定系数 |
| 回归 RMSE | 0.102 | 均方根误差 |
| 分类 ROC-AUC | 0.887 | 低良率风险识别能力 |
| 分类 PR-AUC | 0.680 | 正例精确度-召回率曲线下面积 |
| Top-20% 覆盖率 | 45% | 拦截 Top 20% 高风险批次，覆盖 45% 低良率 |

### 根因分析

| 参数 | SHAP 重要性 | 相关性 | 说明 |
|------|------------|--------|------|
| critical_dimension | 0.125 (64%) | r=-0.65 | 良率主导参数 |
| vth | 0.035 | - | 阈值电压 |
| oxide_thickness | 0.018 | - | 氧化层厚度 |
| thickness_uniformity | 0.015 | - | 厚度均匀性 |
| defect_count | 0.012 | - | 缺陷数量 |

### SPC 过程控制

| 参数 | Cpk | Ppk | 判标 | 失控点 |
|------|-----|-----|------|--------|
| critical_dimension | 1.11 | 0.75 | 可接受，需监控 | 11 (11.0%) |
| oxide_thickness | 0.88 | 0.86 | 不足，需改进 | 8 (8.0%) |
| vth | 0.51 | 0.71 | 不足，需改进 | 0 (0.0%) |

**判标标准**：
- Cpk < 1.0：过程能力不足，需改进
- 1.0 ≤ Cpk < 1.33：过程能力可接受，需监控
- Cpk ≥ 1.33：过程能力充足

### 工艺优化

| 指标 | 数值 | 说明 |
|------|------|------|
| 基线良率 | 0.457 | 当前工艺窗口平均良率 |
| 优化后良率 | 0.702 | 贝叶斯优化找到的最优窗口 |
| 良率提升 | +24.5pp | 绝对提升 24.5 个百分点 |
| DOE 实验点 | 50 | Latin Hypercube Sampling |
| BO 迭代次数 | 38 | 达到同等最优所需的迭代 |
| 试产成本降低 | -24% | 相比传统 DOE（50 点）节省 24% |

**最优工艺窗口**：
- critical_dimension：17.8 nm
- oxide_thickness：63.7 Å
- vth：0.45 V

## 业务闭环

```
良率建模 → SHAP 识别关键参数（CD 重要性 64%）
    ↓
过程控制 → SPC 监控关键参数稳定性
    ↓ 发现 Cpk < 1.33（过程能力不足）
    ↓
工艺优化 → DOE + 贝叶斯优化寻找最优窗口
    ↓ 良率 0.457 → 0.702（+24.5pp）
    ↓
上线验证 → 输出工艺建议 → 实际产线验证 → 迭代优化
```

## 技术要点

### 1. 时间切分防数据泄漏

半导体数据具有时间序列特性，必须按时间顺序切分训练集/测试集（80/20），避免未来数据泄漏到训练集。

### 2. 机台效应建模

不同机台（equipment_id）对良率有显著影响。通过 one-hot 编码将机台信息纳入模型，捕捉设备效应。

### 3. SHAP 根因分析

SHAP（SHapley Additive exPlanations）基于博弈论，可以：
- 给出每个样本的预测解释（局部可解释性）
- 给出全局特征重要性排名
- 展示参数与良率的关系曲线（正向/负向、线性/非线性）
- 与统计分析（相关性分析）互证，增强可信度

### 4. SPC 过程控制

Xbar-R 控制图用于监控过程稳定性：
- **Xbar 图**：监控过程中心是否漂移（均值变化）
- **R 图**：监控过程波动是否稳定（极差变化）
- **控制限**：基于 ±3σ 原则，超出控制限视为失控

过程能力指数：
- **Cpk**（短期能力）：基于组内变异，反映最佳状态
- **Ppk**（长期性能）：基于整体变异，反映实际表现
- **判标**：Cpk ≥ 1.33 表示过程能力充足（6Sigma 标准）

### 5. 贝叶斯优化

相比传统 DOE（全因子设计、响应面法），贝叶斯优化的优势：
- **代理模型**：用历史数据训练 RF/GP 作为"产线仿真器"，减少真实试产成本
- **采集函数**：Expected Improvement (EI) 平衡"开发"（选已知好的区域）和"探索"（选不确定性高的区域）
- **迭代优化**：每次试产后更新代理模型，逐步逼近最优
- **本案例**：38 次迭代达到 LHS 50 点同等最优，试产成本降低 24%

### 6. 非单调关系处理

SPC 分析发现：失控批次良率反而更高（+6.9pp），说明参数-良率关系**非单调**。传统 SPC 的目标是让参数稳定在均值附近，但均值不是最优点。贝叶斯优化可以找到全局最优（如 oxide=63.7 中值），而非局部最优（均值）。

## 已知限制

1. **数据规模有限**：当前仅 50 个批次，长期漂移/季节分析需要更多历史数据
2. **缺失值处理**：当前数据集无缺失值，真实产线数据通常需要 KNN 填充、多重插补等方法
3. **特征共线性**：defect_density 与 thickness_uniformity 存在共线性，需要 VIF 检查与特征筛选
4. **单目标优化**：仅优化良率，实际产线需要同时考虑成本、产能、能耗等多目标权衡
5. **模型泛化性**：需要在更多工艺节点与机台配置上验证模型稳定性

## 后续规划

1. **真实数据验证**：在实际产线数据上验证模型效果
2. **缺失值处理**：引入 KNN 填充、多重插补等方法处理缺失数据
3. **漂移监测**：建立 PSI/KS 统计量监测数据漂移，定期重训模型
4. **多目标优化**：同时优化良率、成本、产能，寻找 Pareto 最优解
5. **在线学习**：引入增量学习机制，模型随新数据持续更新
6. **异常检测**：引入孤立森林/AutoEncoder 检测异常批次
7. **部署上线**：封装为 REST API，集成到产线 MES 系统

## 参考资料

1. **SHAP**：Lundberg, S. M., & Lee, S. I. (2017). A unified approach to interpreting model predictions. NeurIPS.
2. **贝叶斯优化**：Snoek, J., Larochelle, H., & Adams, R. P. (2012). Practical bayesian optimization of machine learning algorithms. NeurIPS.
3. **SPC**：Montgomery, D. C. (2019). Introduction to statistical quality control. John Wiley & Sons.
4. **DOE**：Myers, R. H., Montgomery, D. C., & Anderson-Cook, C. M. (2016). Response surface methodology. John Wiley & Sons.

## 许可证

本项目仅供学习与研究使用。

## 联系方式

如有问题或建议，请通过 GitHub Issues 反馈。
