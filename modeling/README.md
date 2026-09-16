# 建模代码目录

本目录包含所有建模相关的 Python 代码。

## 文件说明

### main.py
**半导体晶圆良率建模分析**
- 良率回归：XGBoost / RandomForest 预测 yield
- 低良率识别：二分类模型 + Top-k 拦截覆盖率
- 根因分析：SHAP 特征重要性
- 输出图片保存到 `../reports/figures/`

### optimize.py
**DOE + 贝叶斯优化 · 最优工艺窗口寻优**
- 代理模型：RandomForest 作为产线仿真器
- DOE：Latin Hypercube Sampling 实验设计
- 贝叶斯优化：高斯过程 + EI 采集函数
- 多目标优化：yield + Cpk Pareto 前沿
- 输出图片保存到 `../reports/figures/`

### spc_analysis.py
**SPC 统计过程控制 + 过程能力分析**
- Xbar-R 控制图：监控过程稳定性
- Cpk/Ppk 计算：过程能力评估
- 失控点识别：OOC 预警
- 输出图片保存到 `../reports/figures/`

## 运行方式

```bash
# 1. 良率建模
python modeling/main.py

# 2. SPC 分析
python modeling/spc_analysis.py

# 3. 工艺优化
python modeling/optimize.py
```

## 路径配置

所有脚本都配置了正确的路径：
- `BASE`：项目根目录（`modeling/` 的父目录）
- `DATA`：数据目录（`data/`）
- `RESULT`：结果目录（`results/`，存放 JSON 等）
- `FIGURES`：图片目录（`reports/figures/`）
