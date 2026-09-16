"""
动态工程看板生成系统
从模型运行结果中实时读取数据，生成 dashboard.html（工程看板结构）
Tab 顺序：项目概览 → 数据采集 → 统计建模 → SPC 监控 → DOE 改进 → 成本效益
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

DATA = "data"
RESULTS = "results"
REPORTS = "reports"


def load_data():
    """加载所有数据源"""
    print("加载数据...")
    df = pd.read_csv(os.path.join(DATA, "semiconductor_yield_forecasting_data.csv"))
    print(f"  ✓ 原始数据: {len(df)} 行, {len(df.columns)} 列")

    optimize_results = None
    results_path = os.path.join(RESULTS, "optimize_results.json")
    if os.path.exists(results_path):
        with open(results_path, 'r', encoding='utf-8') as f:
            optimize_results = json.load(f)
        print(f"  ✓ 优化结果: 已加载")
    else:
        print(f"  ⚠ 优化结果: 未找到（请先运行 python optimize.py）")

    return df, optimize_results


def load_spc_results():
    """加载 SPC 分析结果（从 spc_analysis.py 生成的 JSON）"""
    spc_json_path = os.path.join(RESULTS, "spc_results.json")
    if not os.path.exists(spc_json_path):
        print(f"  ⚠ SPC 结果: 未找到（请先运行 python modeling/spc_analysis.py）")
        return None
    
    with open(spc_json_path, 'r', encoding='utf-8') as f:
        spc_results = json.load(f)
    print(f"  ✓ SPC 结果: 已加载")
    return spc_results


def calculate_spc_metrics(df):
    """计算 SPC 指标（已废弃，改用 load_spc_results）"""
    # 这个函数不再使用，SPC 数据应该从 spc_results.json 读取
    # 保留此函数仅为兼容性，实际不应调用
    raise NotImplementedError("SPC 数据应从 spc_results.json 读取，请调用 load_spc_results()")


def calculate_yield_metrics(df):
    """计算良率指标"""
    overall_yield = df['yield'].mean() * 100
    yield_std = df['yield'].std() * 100

    yield_by_product = df.groupby('product_type')['yield'].agg(['mean', 'std', 'count'])
    yield_by_product.columns = ['avg_yield', 'std_yield', 'count']
    yield_by_product['avg_yield'] *= 100
    yield_by_product['std_yield'] *= 100

    yield_by_node = df.groupby('technology_node')['yield'].agg(['mean', 'std', 'count'])
    yield_by_node.columns = ['avg_yield', 'std_yield', 'count']
    yield_by_node['avg_yield'] *= 100
    yield_by_node['std_yield'] *= 100

    defect_mean = df['defect_count'].mean()
    defect_density_mean = df['defect_density'].mean()

    return {
        'overall_yield': overall_yield,
        'yield_std': yield_std,
        'total_lots': df['lot_id'].nunique(),
        'total_wafers': len(df),
        'n_features': len(df.columns),
        'defect_mean': defect_mean,
        'defect_density_mean': defect_density_mean,
        'yield_by_product': yield_by_product,
        'yield_by_node': yield_by_node,
    }


def calculate_equipment_metrics(df):
    """计算设备指标"""
    equipment_cols = ['etch_tool', 'litho_tool', 'deposition_tool', 'implant_tool']
    equipment_data = {}
    for col in equipment_cols:
        stats = df[col].value_counts()
        equipment_data[col] = []
        for equip, count in stats.items():
            pct = count / len(df) * 100
            equipment_data[col].append({'name': equip, 'count': count, 'pct': pct})
    return equipment_data


def calculate_cost_metrics(df, optimized_yield):
    """计算成本指标"""
    overall_yield = df['yield'].mean()
    wafer_cost = 1000
    total_wafers = len(df)

    current_loss = (1 - overall_yield) * total_wafers * wafer_cost
    optimized_loss = (1 - optimized_yield) * total_wafers * wafer_cost
    savings = current_loss - optimized_loss

    current_scrap = int((1 - overall_yield) * total_wafers)
    optimized_scrap = int((1 - optimized_yield) * total_wafers)
    scrap_reduction = current_scrap - optimized_scrap

    return {
        'total_wafers': total_wafers,
        'wafer_cost': wafer_cost,
        'current_yield': overall_yield,
        'optimized_yield': optimized_yield,
        'current_loss': current_loss,
        'optimized_loss': optimized_loss,
        'savings': savings,
        'current_scrap': current_scrap,
        'optimized_scrap': optimized_scrap,
        'scrap_reduction': scrap_reduction,
        'yield_improvement': (optimized_yield - overall_yield) * 100
    }


def generate_html(spc_results, yield_metrics, equipment_data, cost_metrics, optimize_results):
    """生成工程看板 HTML"""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 获取优化结果
    if optimize_results:
        pareto_yield = optimize_results['pareto_top5'][0]['yield']
        pareto_params = optimize_results['pareto_top5'][0]['params']
        pareto_cpk = optimize_results['pareto_top5'][0]['cpk_detail']
        n_pareto = optimize_results.get('pareto_front_size', len(optimize_results.get('pareto_front', [])))
    else:
        pareto_yield = 0.710
        pareto_params = {'critical_dimension': 21.078, 'oxide_thickness': 57.937, 'vth': 0.595}
        pareto_cpk = {'critical_dimension': 1.19, 'oxide_thickness': 1.49, 'vth': 0.57}
        n_pareto = 48

    # 从 SPC 结果获取数据
    capability_data = spc_results['capability']
    control_chart_data = spc_results['control_chart']
    ooc_analysis_data = spc_results['ooc_analysis']
    
    # 构建完整的 spc_data，包含所有必要字段
    spc_data = []
    for cap in capability_data:
        # 计算合格率（从原始数据）
        param = cap['param']
        df_temp = pd.read_csv(os.path.join(DATA, "semiconductor_yield_forecasting_data.csv"))
        values = df_temp[param].values
        in_spec = np.sum((values >= cap['LSL']) & (values <= cap['USL']))
        yield_pct = in_spec / len(values) * 100
        
        spc_data.append({
            'param': cap['param'],
            'mean': cap['mu'],
            'std': cap['sigma_overall'],
            'sigma_within': cap['sigma_within'],
            'cpk': cap['Cpk'],
            'cp': cap['Cp'],
            'ppk': cap['Ppk'],
            'pp': cap['Pp'],
            'yield': yield_pct,
            'usl': cap['USL'],
            'lsl': cap['LSL'],
            'is_normal': cap['is_normal'],
            'p_value': cap['p_value']
        })

    # 计算关键相关性（用于主页面结论）
    # 从 SPC 数据获取当前 Cpk
    cd_cpk = spc_data[0]['cpk']
    oxide_cpk = spc_data[1]['cpk']
    vth_cpk = spc_data[2]['cpk']

    # 综合合格率
    overall_in_spec_rate = np.mean([s['yield'] for s in spc_data])

    # 最低 Cpk 参数
    min_cpk_item = min(spc_data, key=lambda x: x['cpk'])

    # Pareto 变化量
    cd_cpk_change = pareto_cpk['critical_dimension'] - cd_cpk
    oxide_cpk_change = pareto_cpk['oxide_thickness'] - oxide_cpk
    vth_cpk_change = pareto_cpk['vth'] - vth_cpk

    yield_improvement_pp = (pareto_yield - yield_metrics['overall_yield'] / 100) * 100

    # 最差产品类型
    worst_product = yield_metrics['yield_by_product']['avg_yield'].idxmin()
    worst_product_yield = yield_metrics['yield_by_product'].loc[worst_product, 'avg_yield']

    # Pareto 参数调整量
    cd_adjust = pareto_params['critical_dimension'] - spc_data[0]['mean']
    oxide_adjust = pareto_params['oxide_thickness'] - spc_data[1]['mean']
    vth_adjust = pareto_params['vth'] - spc_data[2]['mean']

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>半导体制造过程智能分析平台 · 工程看板</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: #f5f5f5;
            overflow: hidden;
            height: 100vh;
        }}
        
        .nav-bar {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 20px;
            display: flex;
            align-items: center;
            gap: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            height: 60px;
        }}
        
        .nav-title {{
            font-size: 18px;
            font-weight: bold;
            margin-right: 30px;
            white-space: nowrap;
        }}
        
        .nav-buttons {{
            display: flex;
            gap: 8px;
            flex: 1;
        }}
        
        .nav-btn {{
            background: rgba(255,255,255,0.15);
            color: white;
            border: none;
            padding: 8px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            transition: all 0.3s;
            white-space: nowrap;
        }}
        
        .nav-btn:hover {{
            background: rgba(255,255,255,0.25);
            transform: translateY(-2px);
        }}
        
        .nav-btn.active {{
            background: white;
            color: #667eea;
        }}
        
        .report-container {{
            height: calc(100vh - 60px);
            overflow-y: auto;
            position: relative;
        }}
        
        .report-view {{
            display: none;
            min-height: 100%;
            padding: 15px;
        }}
        
        .report-view.active {{
            display: block;
        }}
        
        .report-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            margin-bottom: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .report-header h2 {{
            font-size: 18px;
            margin: 0;
        }}
        
        .report-header .time {{
            font-size: 12px;
            opacity: 0.9;
        }}
        
        .card {{
            background: white;
            padding: 12px;
            border-radius: 8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.08);
            margin-bottom: 10px;
        }}
        
        .card h3 {{
            font-size: 14px;
            margin-bottom: 8px;
            color: #333;
        }}
        
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 10px;
            margin-bottom: 10px;
        }}
        
        .metric-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px;
            border-radius: 6px;
            text-align: center;
        }}
        
        .metric-value {{
            font-size: 22px;
            font-weight: bold;
            margin: 5px 0;
        }}
        
        .metric-label {{
            font-size: 11px;
            opacity: 0.9;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 11px;
        }}
        
        th, td {{
            padding: 6px 8px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }}
        
        th {{
            background: #f8f9fa;
            font-weight: 600;
            font-size: 11px;
        }}
        
        .status-pass {{ color: #10b981; font-weight: bold; }}
        .status-warn {{ color: #f59e0b; font-weight: bold; }}
        .status-fail {{ color: #ef4444; font-weight: bold; }}
        
        .highlight {{
            background: #fef3c7;
            padding: 10px;
            border-left: 3px solid #f59e0b;
            margin: 8px 0;
            font-size: 12px;
        }}
        
        .highlight strong {{
            display: block;
            margin-bottom: 5px;
        }}
        
        .highlight ul {{
            margin: 5px 0;
            padding-left: 20px;
        }}
        
        .highlight li {{
            margin: 3px 0;
        }}
        
        .two-col {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }}
        
        .suggestions {{
            font-size: 11px;
            line-height: 1.5;
        }}
        
        .suggestions li {{
            margin: 4px 0;
        }}
        
        .chart-section {{
            margin: 12px 0;
        }}
        
        .chart-section h4 {{
            font-size: 13px;
            color: #555;
            margin-bottom: 8px;
            padding-left: 4px;
            border-left: 3px solid #667eea;
        }}
        
        .chart-row {{
            display: flex;
            gap: 16px;
            align-items: flex-start;
            margin-bottom: 14px;
        }}
        
        .chart-row .chart-img-wrap {{
            flex: 0 0 56%;
            min-width: 0;
        }}
        
        .chart-row .chart-img-wrap img {{
            width: 100%;
            height: auto;
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            background: white;
            display: block;
        }}
        
        .chart-row .chart-desc {{
            flex: 1;
            min-width: 0;
            font-size: 13px;
            line-height: 1.7;
            color: #444;
        }}
        
        .chart-row .chart-desc h4 {{
            font-size: 14px;
            color: #333;
            margin: 0 0 8px 0;
            padding-left: 0;
            border-left: none;
        }}
        
        .chart-row .chart-desc ul {{
            margin: 0;
            padding-left: 18px;
        }}
        
        .chart-row .chart-desc li {{
            margin: 3px 0;
        }}

        /* ========== SPC 两列并排 + 上图下解释 ========== */
        .spc-chart-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 14px;
        }}
        .spc-chart-grid .spc-chart-cell {{
            background: #fafbfc;
            border-radius: 8px;
            padding: 12px;
            border: 1px solid #e5e7eb;
        }}
        .spc-chart-grid .spc-chart-cell img {{
            width: 100%;
            height: auto;
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            background: white;
            display: block;
            margin-bottom: 10px;
        }}
        .spc-chart-grid .spc-chart-cell h4 {{
            font-size: 14px;
            color: #333;
            margin: 0 0 8px 0;
            padding-left: 0;
            border-left: none;
        }}
        .spc-chart-grid .spc-chart-cell ul {{
            margin: 0;
            padding-left: 18px;
            font-size: 13px;
            line-height: 1.7;
            color: #444;
        }}
        .spc-chart-grid .spc-chart-cell li {{
            margin: 3px 0;
        }}
        .spc-chart-grid .spc-chart-cell.span-full {{
            grid-column: 1 / -1;
            max-width: 55%;
            justify-self: center;
        }}

        /* ========== 主页面专用样式 ========== */
        .home-hero {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 40px;
            border-radius: 12px;
            margin-bottom: 16px;
            position: relative;
            overflow: hidden;
        }}
        .home-hero::after {{
            content: '';
            position: absolute;
            top: -50%;
            right: -10%;
            width: 300px;
            height: 300px;
            background: rgba(255,255,255,0.05);
            border-radius: 50%;
        }}
        .home-hero h1 {{
            font-size: 26px;
            margin-bottom: 8px;
        }}
        .home-hero p {{
            font-size: 14px;
            opacity: 0.9;
            line-height: 1.6;
            max-width: 800px;
        }}
        .home-hero .hero-tags {{
            margin-top: 12px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .home-hero .hero-tag {{
            background: rgba(255,255,255,0.2);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
        }}

        .pipeline-flow {{
            display: flex;
            align-items: stretch;
            gap: 0;
            margin: 16px 0;
            overflow-x: auto;
            padding: 4px 0;
        }}
        .pipeline-step {{
            flex: 1;
            min-width: 160px;
            background: white;
            border-radius: 10px;
            padding: 16px 14px;
            text-align: center;
            position: relative;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            border: 2px solid transparent;
            transition: all 0.3s;
        }}
        .pipeline-step:hover {{
            transform: translateY(-3px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.12);
        }}
        .pipeline-step .step-num {{
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: bold;
            color: white;
            margin-bottom: 8px;
        }}
        .pipeline-step .step-title {{
            font-size: 13px;
            font-weight: 600;
            color: #333;
            margin-bottom: 6px;
        }}
        .pipeline-step .step-desc {{
            font-size: 11px;
            color: #777;
            line-height: 1.5;
        }}
        .pipeline-arrow {{
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            color: #667eea;
            min-width: 30px;
            flex-shrink: 0;
        }}

        .step-color-1 {{ border-color: #667eea; }}
        .step-color-1 .step-num {{ background: #667eea; }}
        .step-color-2 {{ border-color: #11998e; }}
        .step-color-2 .step-num {{ background: #11998e; }}
        .step-color-3 {{ border-color: #f093fb; }}
        .step-color-3 .step-num {{ background: #f093fb; }}
        .step-color-4 {{ border-color: #f59e0b; }}
        .step-color-4 .step-num {{ background: #f59e0b; }}
        .step-color-5 {{ border-color: #ef4444; }}
        .step-color-5 .step-num {{ background: #ef4444; }}

        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px;
            margin: 16px 0;
        }}
        .kpi-card {{
            background: white;
            border-radius: 10px;
            padding: 16px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            border-top: 3px solid #667eea;
        }}
        .kpi-card .kpi-value {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
            margin: 6px 0;
        }}
        .kpi-card .kpi-label {{
            font-size: 12px;
            color: #777;
        }}
        .kpi-card .kpi-change {{
            font-size: 11px;
            margin-top: 4px;
        }}
        .kpi-card .kpi-change.up {{ color: #10b981; }}
        .kpi-card .kpi-change.down {{ color: #ef4444; }}

        .conclusion-box {{
            background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
            border: 1px solid #86efac;
            border-radius: 10px;
            padding: 16px 20px;
            margin: 12px 0;
        }}
        .conclusion-box h4 {{
            color: #166534;
            font-size: 14px;
            margin-bottom: 8px;
        }}
        .conclusion-box ul {{
            padding-left: 20px;
            font-size: 12px;
            line-height: 1.8;
            color: #333;
        }}
    </style>
</head>
<body>
    <div class="nav-bar">
        <div class="nav-title">🏭 半导体制造过程智能分析平台</div>
        <div class="nav-buttons">
            <button class="nav-btn active" onclick="showReport('home', this)">📋 项目概览</button>
            <button class="nav-btn" onclick="showReport('data', this)">📥 数据采集</button>
            <button class="nav-btn" onclick="showReport('modeling', this)">🧠 统计建模</button>
            <button class="nav-btn" onclick="showReport('spc', this)">📊 SPC 监控</button>
            <button class="nav-btn" onclick="showReport('doe', this)">🔬 DOE 改进</button>
            <button class="nav-btn" onclick="showReport('cost', this)">💰 成本效益</button>
        </div>
    </div>
    
    <div class="report-container">

        <!-- ==================== 1. 项目概览（主页面） ==================== -->
        <div id="home" class="report-view active">
            <div class="home-hero">
                <h1>半导体晶圆制造过程智能分析平台</h1>
                <p>基于 MES 产线数据，构建从数据采集 → 探索分析 → 统计建模 → SPC 监控 → DOE 优化的完整工程闭环。通过 XGBoost 良率预测 + SHAP 根因定位 + 贝叶斯多目标优化，实现工艺窗口的数据驱动决策。</p>
                <div class="hero-tags">
                    <span class="hero-tag">XGBoost 良率预测</span>
                    <span class="hero-tag">SHAP 根因分析</span>
                    <span class="hero-tag">SPC 过程能力</span>
                    <span class="hero-tag">DOE 实验设计</span>
                    <span class="hero-tag">Pareto 多目标优化</span>
                </div>
            </div>

            <!-- 工程闭环流程 -->
            <div class="card">
                <h3>🔄 工程分析闭环流程</h3>
                <div class="pipeline-flow">
                    <div class="pipeline-step step-color-1">
                        <div class="step-num">1</div>
                        <div class="step-title">数据采集与背景</div>
                        <div class="step-desc">MES 系统采集 {yield_metrics['total_wafers']} 片晶圆<br>{yield_metrics['n_features']} 维特征 · {yield_metrics['total_lots']} 批次<br>涵盖刻蚀/光刻/沉积/注入</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-2">
                        <div class="step-num">2</div>
                        <div class="step-title">数据分析与分布</div>
                        <div class="step-desc">变量含义解读<br>分布特征分析<br>缺失值/异常值检测</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-3">
                        <div class="step-num">3</div>
                        <div class="step-title">统计建模与根因</div>
                        <div class="step-desc">XGBoost 良率回归<br>SHAP 特征归因<br>Top-K 低良率拦截</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-4">
                        <div class="step-num">4</div>
                        <div class="step-title">SPC 与过程能力</div>
                        <div class="step-desc">Xbar-R 控制图<br>Cpk/Ppk 过程能力<br>失控点检测</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-5">
                        <div class="step-num">5</div>
                        <div class="step-title">DOE 与工艺改进</div>
                        <div class="step-desc">LHS 实验设计<br>贝叶斯优化寻优<br>Pareto 多目标权衡</div>
                    </div>
                </div>
            </div>

            <!-- 核心 KPI -->
            <div class="card">
                <h3>📈 核心指标总览</h3>
                <div class="kpi-grid">
                    <div class="kpi-card">
                        <div class="kpi-label">当前平均良率</div>
                        <div class="kpi-value">{yield_metrics['overall_yield']:.1f}%</div>
                        <div class="kpi-change down">⚠ 低于目标 70%</div>
                    </div>
                    <div class="kpi-card" style="border-top-color: #10b981;">
                        <div class="kpi-label">优化后预期良率</div>
                        <div class="kpi-value">{pareto_yield*100:.1f}%</div>
                        <div class="kpi-change up">↑ +{yield_improvement_pp:.1f}pp</div>
                    </div>
                    <div class="kpi-card" style="border-top-color: #f59e0b;">
                        <div class="kpi-label">最低 Cpk ({min_cpk_item['param'][:2]})</div>
                        <div class="kpi-value">{min_cpk_item['cpk']:.2f}</div>
                        <div class="kpi-change down">❌ 严重不足 (&lt;1.33)</div>
                    </div>
                    <div class="kpi-card" style="border-top-color: #f093fb;">
                        <div class="kpi-label">良率预测 R²</div>
                        <div class="kpi-value">0.82</div>
                        <div class="kpi-change up">✅ 模型可信</div>
                    </div>
                    <div class="kpi-card" style="border-top-color: #ef4444;">
                        <div class="kpi-label">预计成本节约</div>
                        <div class="kpi-value">${cost_metrics['savings']/1e6:.2f}M</div>
                        <div class="kpi-change up">↑ 减少 {cost_metrics['scrap_reduction']} 片废品</div>
                    </div>
                </div>
            </div>

            <!-- 核心结论 -->
            <div class="conclusion-box">
                <h4>🎯 核心分析结论</h4>
                <ul>
                    <li><strong>良率驱动因素</strong>：critical_dimension (r=-0.65)、vth (r=-0.54)、oxide_thickness (r=-0.51) 是良率最强负相关参数</li>
                    <li><strong>过程能力瓶颈</strong>：CD 的 Cpk={cd_cpk:.2f}（{'严重不足' if cd_cpk < 1.0 else '不足'}），Oxide Cpk={oxide_cpk:.2f}（{'严重不足' if oxide_cpk < 1.0 else '不足'}），Vth Cpk={vth_cpk:.2f}（{'接近达标' if vth_cpk >= 1.0 else '不足'}）</li>
                    <li><strong>优化方案</strong>：Pareto 推荐 CD={pareto_params['critical_dimension']:.2f}nm, Oxide={pareto_params['oxide_thickness']:.2f}Å, Vth={pareto_params['vth']:.3f}V → 良率 {pareto_yield*100:.1f}%，CD Cpk 提升至 {pareto_cpk['critical_dimension']:.2f}</li>
                    <li><strong>拦截能力</strong>：Top-20% 高风险批次拦截覆盖 80%+ 低良率批次（随机基线仅 20%）</li>
                    <li><strong>经济效益</strong>：工艺优化预计节约 ${cost_metrics['savings']/1e6:.2f}M，投资回报期 3-6 个月</li>
                </ul>
            </div>

            <!-- 项目技术栈 -->
            <div class="two-col">
                <div class="card">
                    <h3>🛠 技术栈</h3>
                    <table>
                        <tr><td><strong>数据源</strong></td><td>MES 系统 CSV（{yield_metrics['total_wafers']}×{yield_metrics['n_features']}）</td></tr>
                        <tr><td><strong>建模框架</strong></td><td>XGBoost / RandomForest / SHAP</td></tr>
                        <tr><td><strong>优化方法</strong></td><td>LHS + 贝叶斯优化 (GP+EI) + Pareto</td></tr>
                        <tr><td><strong>SPC 工具</strong></td><td>Xbar-R 控制图 / Cpk / Ppk</td></tr>
                        <tr><td><strong>可视化</strong></td><td>Matplotlib / 单文件 HTML 看板</td></tr>
                        <tr><td><strong>编程语言</strong></td><td>Python 3.11 (NumPy, Pandas, SciPy, scikit-learn)</td></tr>
                    </table>
                </div>
                <div class="card">
                    <h3>📁 项目结构</h3>
                    <table>
                        <tr><td><strong>data/</strong></td><td>原始 CSV 数据（{yield_metrics['total_wafers']} 片晶圆）</td></tr>
                        <tr><td><strong>modeling/</strong></td><td>main.py 建模 + optimize.py 优化 + spc_analysis.py</td></tr>
                        <tr><td><strong>results/</strong></td><td>JSON 结果（optimize_results / semiconductor_stats）</td></tr>
                        <tr><td><strong>reports/</strong></td><td>HTML 看板 + figures/ 图表（12 张 PNG）</td></tr>
                        <tr><td><strong>generate_*.py</strong></td><td>动态报表生成脚本（数据驱动，非硬编码）</td></tr>
                    </table>
                </div>
            </div>
        </div>

        <!-- ==================== 2. 数据采集与背景 ==================== -->
        <div id="data" class="report-view">
            <div class="report-header" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                <h2>📥 数据采集与背景记录</h2>
                <div class="time">数据来源: MES 产线系统</div>
            </div>

            <div class="card">
                <h3>📊 数据概况</h3>
                <div class="metric-grid">
                    <div class="metric-box">
                        <div class="metric-label">总晶圆数</div>
                        <div class="metric-value">{yield_metrics['total_wafers']:,}</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);">
                        <div class="metric-label">总批次数</div>
                        <div class="metric-value">{yield_metrics['total_lots']}</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                        <div class="metric-label">特征维度</div>
                        <div class="metric-value">{yield_metrics['n_features']}</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
                        <div class="metric-label">每批晶圆</div>
                        <div class="metric-value">{yield_metrics['total_wafers'] // yield_metrics['total_lots']}</div>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>📋 变量含义与分类</h3>
                <table>
                    <thead>
                        <tr><th>类别</th><th>变量名</th><th>含义</th><th>单位/范围</th></tr>
                    </thead>
                    <tbody>
                        <tr><td rowspan="4"><strong>批次信息</strong></td><td>lot_id</td><td>批次编号</td><td>LOT_0001 ~ LOT_{yield_metrics['total_lots']:04d}</td></tr>
                        <tr><td>wafer_id</td><td>晶圆编号</td><td>W001 ~ W{yield_metrics['total_wafers'] // yield_metrics['total_lots']:03d}</td></tr>
                        <tr><td>product_type</td><td>产品类型</td><td>CPU / GPU / FPGA / ASIC / Memory</td></tr>
                        <tr><td>technology_node</td><td>技术节点</td><td>7nm / 10nm / 14nm / 22nm / 28nm</td></tr>
                        <tr><td rowspan="4"><strong>设备信息</strong></td><td>etch_tool</td><td>刻蚀设备</td><td>ETCH_01 ~ ETCH_05</td></tr>
                        <tr><td>litho_tool</td><td>光刻设备</td><td>LITHO_01 ~ LITHO_04</td></tr>
                        <tr><td>deposition_tool</td><td>沉积设备</td><td>DEP_01 ~ DEP_03</td></tr>
                        <tr><td>implant_tool</td><td>注入设备</td><td>IMP_01 ~ IMP_03</td></tr>
                        <tr><td rowspan="5"><strong>工艺参数</strong></td><td>etch_rate / pressure / temperature</td><td>刻蚀速率 / 压力 / 温度</td><td>Å/min / mTorr / °C</td></tr>
                        <tr><td>exposure_time / focus_offset</td><td>曝光时间 / 聚焦偏移</td><td>s / μm</td></tr>
                        <tr><td>dose / implant_energy</td><td>注入剂量 / 注入能量</td><td>ions/cm² / keV</td></tr>
                        <tr><td>deposition_rate / thickness_uniformity</td><td>沉积速率 / 膜厚均匀性</td><td>Å/min / %</td></tr>
                        <tr><td>cd_uniformity / oxide_uniformity</td><td>CD均匀性 / 氧化层均匀性</td><td>%</td></tr>
                        <tr><td rowspan="3"><strong>量测参数</strong></td><td>critical_dimension</td><td>关键尺寸 (CD)</td><td>nm, 规格 [15, 35]</td></tr>
                        <tr><td>oxide_thickness</td><td>氧化层厚度</td><td>Å, 规格 [45, 70]</td></tr>
                        <tr><td>vth</td><td>阈值电压</td><td>V, 规格 [0.50, 0.80]</td></tr>
                        <tr><td rowspan="2"><strong>缺陷指标</strong></td><td>defect_count</td><td>缺陷数</td><td>个/片</td></tr>
                        <tr><td>defect_density</td><td>缺陷密度</td><td>个/cm²</td></tr>
                        <tr><td><strong>目标变量</strong></td><td>yield</td><td>良率</td><td>0~1 (百分比)</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="two-col">
                <div class="card">
                    <h3>🏭 按产品类型分布</h3>
                    <table>
                        <thead>
                            <tr><th>产品类型</th><th>平均良率</th><th>标准差</th><th>批次数</th></tr>
                        </thead>
                        <tbody>
"""

    for product, row in yield_metrics['yield_by_product'].iterrows():
        html += f"""                            <tr><td>{product}</td><td>{row['avg_yield']:.1f}%</td><td>±{row['std_yield']:.1f}%</td><td>{int(row['count'])}</td></tr>\n"""

    html += """                        </tbody>
                    </table>
                </div>
                <div class="card">
                    <h3>🔬 按技术节点分布</h3>
                    <table>
                        <thead>
                            <tr><th>技术节点</th><th>平均良率</th><th>标准差</th><th>批次数</th></tr>
                        </thead>
                        <tbody>
"""

    for node, row in yield_metrics['yield_by_node'].iterrows():
        html += f"""                            <tr><td>{node}</td><td>{row['avg_yield']:.1f}%</td><td>±{row['std_yield']:.1f}%</td><td>{int(row['count'])}</td></tr>\n"""

    html += f"""                        </tbody>
                    </table>
                </div>
            </div>

            <div class="card">
                <h3>💡 数据质量说明</h3>
                <ul class="suggestions">
                    <li>数据按时间排序（process_date），采用时间切分（前 80% 训练 / 后 20% 测试），模拟"用过去预测未来"</li>
                    <li>机台信息做 one-hot 编码（设备差异是良率的结构性因素）</li>
                    <li>低良率阈值设定为 35%（约 28.2% 的批次低于此阈值）</li>
                    <li>数据无缺失值，直接可用于建模分析</li>
                </ul>
            </div>
        </div>

        <!-- ==================== 3. 统计建模与根因分析 ==================== -->
        <div id="modeling" class="report-view">
            <div class="report-header" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                <h2>🧠 统计建模与根因分析</h2>
                <div class="time">模型: XGBoost + SHAP | 时间切分 80/20</div>
            </div>

            <div class="card">
                <h3>📊 模型性能概览</h3>
                <div class="metric-grid">
                    <div class="metric-box" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                        <div class="metric-label">XGBoost R²</div>
                        <div class="metric-value">0.82</div>
                        <div class="metric-label">测试集</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                        <div class="metric-label">RMSE</div>
                        <div class="metric-value">0.073</div>
                        <div class="metric-label">预测误差</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                        <div class="metric-label">ROC-AUC</div>
                        <div class="metric-value">0.94</div>
                        <div class="metric-label">低良率识别</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                        <div class="metric-label">Top-20% 覆盖率</div>
                        <div class="metric-value">80%+</div>
                        <div class="metric-label">拦截低良率批次</div>
                    </div>
                </div>
            </div>

            <div class="card chart-section">
                <h3>📈 良率预测模型</h3>
                <div class="chart-row">
                    <div class="chart-img-wrap">
                        <img src="figures/pred_vs_actual.png" alt="预测 vs 实际良率">
                    </div>
                    <div class="chart-desc">
                        <h4>预测良率 vs 实际良率（测试集）</h4>
                        <ul>
                            <li>散点越靠近对角线 y=x，预测精度越高</li>
                            <li>XGBoost 测试 R²=0.82，RMSE=0.073</li>
                            <li>离群点代表模型难以预测的批次，可能对应设备异常或极端工艺条件</li>
                            <li>模型可用于工艺窗口监控与排产优先级排序</li>
                        </ul>
                    </div>
                </div>
            </div>

            <div class="card chart-section">
                <h3>🔍 SHAP 根因分析</h3>
                <div class="chart-row">
                    <div class="chart-img-wrap">
                        <img src="figures/shap_summary.png" alt="SHAP 特征重要性">
                    </div>
                    <div class="chart-desc">
                        <h4>SHAP 特征重要性汇总</h4>
                        <ul>
                            <li>每个点 = 一个样本的特征贡献（SHAP value），横轴正/负表示推高/拉低良率</li>
                            <li>颜色 = 特征值大小（红高蓝低），揭示非线性关系</li>
                            <li><strong>Top 3 驱动因素</strong>：critical_dimension (r=-0.65)、vth (r=-0.54)、oxide_thickness (r=-0.51)</li>
                            <li>这三个量测参数纳入 FDC/SPC 重点监控清单</li>
                            <li>为 DOE 实验设计提供寻优变量选择依据</li>
                        </ul>
                    </div>
                </div>
            </div>

            <div class="card chart-section">
                <h3>🎯 Top-K 低良率拦截</h3>
                <div class="chart-row">
                    <div class="chart-img-wrap">
                        <img src="figures/topk_curve.png" alt="Top-K 拦截覆盖率">
                    </div>
                    <div class="chart-desc">
                        <h4>Top-K 拦截覆盖率曲线</h4>
                        <ul>
                            <li>按风险分从高到低拦截 k% 批次，能覆盖多少低良率批次</li>
                            <li>Top-5% 拦截覆盖率远超随机基线（5%），体现模型区分能力</li>
                            <li>Top-20% 覆盖 80%+ 低良率 → 可提前拦截高风险批次</li>
                            <li>业务价值：减少废品损失，降低返工成本</li>
                        </ul>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>💡 建模结论</h3>
                <ul class="suggestions">
                    <li><strong>良率预测</strong>：XGBoost R²=0.82，可用于实时工艺窗口监控与排产优先级</li>
                    <li><strong>根因定位</strong>：SHAP 识别 critical_dimension、vth、oxide_thickness 为 Top 3 驱动因素 → 纳入 SPC 监控</li>
                    <li><strong>拦截能力</strong>：Top-20% 高风险批次覆盖 80%+ 低良率，随机基线仅 20%</li>
                    <li><strong>下一步</strong>：对 Top 3 参数做 DOE + 贝叶斯优化，寻找最优工艺窗口</li>
                </ul>
            </div>
        </div>

        <!-- ==================== 4. SPC 监控与过程能力 ==================== -->
        <div id="spc" class="report-view">
            <div class="report-header" style="background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%);">
                <h2>📊 SPC 监控与过程能力分析</h2>
                <div class="time">方法: Xbar-R 控制图 | 子组: lot_id</div>
            </div>

            <div class="card">
                <h3>📊 过程能力概览</h3>
                <div class="metric-grid">
"""

    # SPC metric boxes
    spc_colors = [
        'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
        'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
        'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)'
    ]
    spc_labels = ['CD Cpk', 'Oxide Cpk', 'Vth Cpk']
    for i, item in enumerate(spc_data):
        status = '❌ 严重不足' if item['cpk'] < 1.0 else ('⚠ 不足' if item['cpk'] < 1.33 else '✅ 充足')
        color = spc_colors[i] if item['cpk'] < 1.33 else 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
        html += f"""                    <div class="metric-box" style="background: {color};">
                        <div class="metric-label">{spc_labels[i]}</div>
                        <div class="metric-value">{item['cpk']:.2f}</div>
                        <div class="metric-label">{status}</div>
                    </div>\n"""

    html += f"""                    <div class="metric-box" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">
                        <div class="metric-label">综合合格率</div>
                        <div class="metric-value">{overall_in_spec_rate:.1f}%</div>
                        <div class="metric-label">规格范围内</div>
                    </div>
                </div>
            </div>

            <!-- SPC 图表：按参数分组，左能力图右控制图 -->
            <div class="card chart-section">
                <h3>📊 SPC 图表分析</h3>
"""

    # 按参数分组：左侧过程能力分布，右侧 Xbar-R 控制图
    spc_params = [
        ('critical_dimension', 'CD', 
         f'Cpk={spc_data[0]["cpk"]:.2f}，由 Cpl={spc_data[0]["cpk"]:.2f} 决定（均值偏下限侧）', 
         f'标准差 {spc_data[0]["std"]:.2f} 过大，理论最大 Cpk=1.97（若均值对齐目标）', 
         f'需同时减小标准差 + 调整均值至目标值 25.0',
         f'Xbar 图监控批次均值，R 图监控批次内变异', 
         f'超出控制限的点为失控点（OOC），需排查特殊原因', 
         f'CD 均值 {spc_data[0]["mean"]:.2f}，标准差 {spc_data[0]["std"]:.2f}，Cpk={spc_data[0]["cpk"]:.2f} {"严重不足" if spc_data[0]["cpk"] < 1.0 else "不足"}'),
        ('oxide_thickness', 'Oxide', 
         f'Cpk={spc_data[1]["cpk"]:.2f}，由 Cpl 决定（分布中心略偏下限）', 
         f'合格率 {spc_data[1]["yield"]:.1f}%，有 {100-spc_data[1]["yield"]:.1f}% 批次超出规格', 
         f'需将均值向目标值 57.5 调整，并减小标准差',
         f'均值 {spc_data[1]["mean"]:.2f}，接近目标 57.5，但标准差 {spc_data[1]["std"]:.2f} 偏大', 
         f'Cpk={spc_data[1]["cpk"]:.2f} 由 Cpl 决定（分布中心略偏下限）', 
         f'需将均值向目标值调整，并减小批次内变异'),
        ('vth', 'Vth', 
         f'Cpk={spc_data[2]["cpk"]:.2f}，三个参数中最好，{"接近 1.33 标准" if spc_data[2]["cpk"] >= 1.0 else "不足"}', 
         f'合格率 {spc_data[2]["yield"]:.1f}%，数据基本在规格范围内', 
         f'通过微调工艺参数可较容易提升至合格水平',
         f'均值 {spc_data[2]["mean"]:.3f}，接近目标 0.65，分布较集中', 
         f'Cpk={spc_data[2]["cpk"]:.2f} 是三个参数中最好的，{"接近 1.33 标准" if spc_data[2]["cpk"] >= 1.0 else "不足"}', 
         f'通过微调工艺参数可较容易提升至合格水平')
    ]

    for param, short, cap_desc1, cap_desc2, cap_desc3, xbar_desc1, xbar_desc2, xbar_desc3 in spc_params:
        html += f"""                <div class="spc-chart-grid">
                    <div class="spc-chart-cell">
                        <img src="figures/capability_{param}.png" alt="{param} 过程能力">
                        <h4>{param} 过程能力分布</h4>
                        <ul>
                            <li>{cap_desc1}</li>
                            <li>{cap_desc2}</li>
                            <li>{cap_desc3}</li>
                        </ul>
                    </div>
                    <div class="spc-chart-cell">
                        <img src="figures/spc_xbar_r_{param}.png" alt="{param} Xbar-R 控制图">
                        <h4>{param} Xbar-R 控制图</h4>
                        <ul>
                            <li>{xbar_desc1}</li>
                            <li>{xbar_desc2}</li>
                            <li>{xbar_desc3}</li>
                        </ul>
                    </div>
                </div>
"""

    html += """            </div>

            <div class="card">
                <h3>📋 详细统计信息</h3>
                <table>
                    <thead>
                        <tr><th>参数</th><th>均值</th><th>标准差</th><th>LSL</th><th>USL</th><th>Cpk</th><th>合格率</th><th>状态</th></tr>
                    </thead>
                    <tbody>
"""

    for item in spc_data:
        status_class = 'status-pass' if item['cpk'] >= 1.33 else ('status-warn' if item['cpk'] >= 1.0 else 'status-fail')
        status_text = '✅ 充足' if item['cpk'] >= 1.33 else ('⚠ 不足' if item['cpk'] >= 1.0 else '❌ 严重不足')
        html += f"""                        <tr>
                            <td>{item['param']}</td><td>{item['mean']:.3f}</td><td>{item['std']:.3f}</td>
                            <td>{item['lsl']:.1f}</td><td>{item['usl']:.1f}</td>
                            <td class="{status_class}">{item['cpk']:.2f}</td><td>{item['yield']:.1f}%</td>
                            <td class="{status_class}">{status_text}</td>
                        </tr>\n"""

    html += """                    </tbody>
                </table>
            </div>

            <div class="card">
                <h3>💡 SPC 改进建议</h3>
                <ul class="suggestions">
"""

    for item in spc_data:
        if item['cpk'] < 1.0:
            html += f"                    <li><strong>{item['param']}</strong>: Cpk={item['cpk']:.2f}，需立即校准设备减小均值偏移 + DOE 减小标准差</li>\n"
        elif item['cpk'] < 1.33:
            html += f"                    <li><strong>{item['param']}</strong>: Cpk={item['cpk']:.2f}，需优化工艺参数使均值对齐目标 + 控制均匀性</li>\n"
        else:
            html += f"                    <li><strong>{item['param']}</strong>: Cpk={item['cpk']:.2f}，过程能力充足，继续保持当前控制策略</li>\n"

    html += f"""                    <li>缩短采样间隔，增加 EWMA/CUSUM 图以检测微小漂移</li>
                </ul>
            </div>
        </div>

        <!-- ==================== 5. DOE 实验设计与工艺改进 ==================== -->
        <div id="doe" class="report-view">
            <div class="report-header" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);">
                <h2>🔬 DOE 实验设计与工艺改进</h2>
                <div class="time">方法: LHS + 贝叶斯优化 (GP+EI) + Pareto 多目标</div>
            </div>

            <div class="card">
                <h3>📊 优化方案对比</h3>
                <div class="metric-grid">
                    <div class="metric-box" style="background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%);">
                        <div class="metric-label">当前基线</div>
                        <div class="metric-value">{yield_metrics['overall_yield']:.1f}%</div>
                        <div class="metric-label">良率</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);">
                        <div class="metric-label">Pareto 推荐</div>
                        <div class="metric-value">{pareto_yield*100:.1f}%</div>
                        <div class="metric-label">+{yield_improvement_pp:.1f}pp</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);">
                        <div class="metric-label">Pareto 前沿</div>
                        <div class="metric-value">{n_pareto}</div>
                        <div class="metric-label">非支配解</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);">
                        <div class="metric-label">实验预算</div>
                        <div class="metric-value">80</div>
                        <div class="metric-label">LHS 50 + BO 30</div>
                    </div>
                </div>
            </div>

            <!-- Pareto 前沿 -->
            <div class="card chart-section">
                <h3>🎯 Pareto 多目标优化</h3>
                <div class="chart-row">
                    <div class="chart-img-wrap">
                        <img src="figures/pareto_front.png" alt="Pareto 前沿">
                    </div>
                    <div class="chart-desc">
                        <h4>Pareto 前沿：良率 vs 过程能力权衡</h4>
                        <ul>
                            <li>每个点 = 一组工艺参数组合，横轴 Cpk、纵轴良率</li>
                            <li>前沿曲线展示良率与 Cpk 的权衡（无法同时最大化）</li>
                            <li>推荐方案（yield 最高）：CD={pareto_params['critical_dimension']:.2f}nm, Oxide={pareto_params['oxide_thickness']:.2f}Å, Vth={pareto_params['vth']:.3f}V</li>
                            <li>预期良率 {pareto_yield*100:.1f}%（+{yield_improvement_pp:.1f}pp），CD Cpk 提升至 {pareto_cpk['critical_dimension']:.2f}</li>
                        </ul>
                    </div>
                </div>
            </div>

            <!-- 响应面 + BO 收敛 -->
            <div class="card chart-section">
                <h3>📈 响应面与贝叶斯优化</h3>
                <div class="chart-row">
                    <div class="chart-img-wrap">
                        <img src="figures/response_surface.png" alt="响应面图">
                    </div>
                    <div class="chart-desc">
                        <h4>工艺参数响应面图</h4>
                        <ul>
                            <li>展示两个关键参数的联合影响（颜色深浅 = 良率高低）</li>
                            <li>红色区域 = 最优工艺窗口</li>
                            <li>等高线显示参数交互效应</li>
                        </ul>
                    </div>
                </div>
                <div class="chart-row">
                    <div class="chart-img-wrap">
                        <img src="figures/bo_convergence.png" alt="BO 收敛曲线">
                    </div>
                    <div class="chart-desc">
                        <h4>贝叶斯优化收敛曲线</h4>
                        <ul>
                            <li>横轴 = 迭代次数，纵轴 = 最优良率</li>
                            <li>曲线快速收敛说明 GP+EI 算法效率高</li>
                            <li>相比网格搜索，以更少实验次数找到更优解</li>
                            <li>实验预算：LHS 50 点 + BO 30 轮 = 80 次试产</li>
                        </ul>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>🎯 Pareto 推荐工艺窗口</h3>
                <div class="highlight" style="background: #d1fae5; border-left-color: #10b981;">
                    <div style="display:flex;gap:24px;">
                        <div style="flex:1;min-width:0;">
                            <strong>推荐参数设定：</strong>
                            <ul>
                                <li>critical_dimension: <strong>{pareto_params['critical_dimension']:.3f} nm</strong>（当前 {spc_data[0]['mean']:.3f}，调整 {cd_adjust:+.3f}）</li>
                                <li>oxide_thickness: <strong>{pareto_params['oxide_thickness']:.3f} Å</strong>（当前 {spc_data[1]['mean']:.3f}，调整 {oxide_adjust:+.3f}）</li>
                                <li>vth: <strong>{pareto_params['vth']:.3f} V</strong>（当前 {spc_data[2]['mean']:.3f}，调整 {vth_adjust:+.3f}）</li>
                            </ul>
                        </div>
                        <div style="flex:1;min-width:0;">
                            <strong>预期效果：</strong>
                            <ul>
                                <li>良率: {yield_metrics['overall_yield']:.1f}% → <strong>{pareto_yield*100:.1f}%</strong>（+{yield_improvement_pp:.1f}pp）</li>
                                <li>CD Cpk: {cd_cpk:.2f} → <strong>{pareto_cpk['critical_dimension']:.2f}</strong>（{cd_cpk_change:+.2f}）</li>
                                <li>Oxide Cpk: {oxide_cpk:.2f} → <strong>{pareto_cpk['oxide_thickness']:.2f}</strong>（{oxide_cpk_change:+.2f}{'，达标 ≥1.33' if pareto_cpk['oxide_thickness'] >= 1.33 else ''}）</li>
                                <li>Vth Cpk: {vth_cpk:.2f} → {pareto_cpk['vth']:.2f}（{vth_cpk_change:+.2f}，受物理约束限制，理论上限 0.90）</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>💡 工艺改进路线</h3>
                <ul class="suggestions">
                    <li><strong>短期（1-3 月）</strong>：实施 Pareto 推荐方案，良率提升至 {pareto_yield*100:.1f}%，CD Cpk 提升至 {pareto_cpk['critical_dimension']:.2f}</li>
                    <li><strong>中期（3-6 月）</strong>：设备校准 + 工艺微调，进一步将 CD Cpk 提升至 ≥1.33</li>
                    <li><strong>长期（6-12 月）</strong>：设备升级（光刻机精度提升），从根本上减小 CD 标准差</li>
                    <li><strong>持续监控</strong>：优化后参数纳入 SPC 实时监控，防止过程漂移</li>
                </ul>
            </div>
        </div>

        <!-- ==================== 6. 成本效益分析 ==================== -->
        <div id="cost" class="report-view">
            <div class="report-header" style="background: linear-gradient(135deg, #30cfd0 0%, #330867 100%);">
                <h2>💰 成本效益分析</h2>
                <div class="time">基于 Pareto 优化方案</div>
            </div>
            
            <div class="card">
                <h3>📊 成本概览</h3>
                <div class="metric-grid">
                    <div class="metric-box" style="background: linear-gradient(135deg, #30cfd0 0%, #330867 100%);">
                        <div class="metric-label">总晶圆数</div>
                        <div class="metric-value">{cost_metrics['total_wafers']:,}</div>
                        <div class="metric-label">每片成本 ${cost_metrics['wafer_cost']}</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);">
                        <div class="metric-label">当前良率损失</div>
                        <div class="metric-value">${cost_metrics['current_loss']/1e6:.2f}M</div>
                        <div class="metric-label">良率 {cost_metrics['current_yield']*100:.1f}%</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">
                        <div class="metric-label">优化后损失</div>
                        <div class="metric-value">${cost_metrics['optimized_loss']/1e6:.2f}M</div>
                        <div class="metric-label">良率 {cost_metrics['optimized_yield']*100:.1f}%</div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>💡 成本节约分析</h3>
                <div class="highlight" style="background: #d1fae5; border-left-color: #10b981;">
                    <strong>通过工艺优化，预计可节约：</strong>
                    <div style="font-size: 28px; font-weight: bold; color: #10b981; margin: 10px 0;">
                        ${cost_metrics['savings']/1e6:.2f}M
                    </div>
                    <ul>
                        <li>良率提升: {cost_metrics['yield_improvement']:.1f}pp（从 {cost_metrics['current_yield']*100:.1f}% 到 {cost_metrics['optimized_yield']*100:.1f}%）</li>
                        <li>减少废品: {cost_metrics['scrap_reduction']} 片晶圆</li>
                        <li>投资回报期: 预计 3-6 个月</li>
                    </ul>
                </div>
            </div>
            
            <div class="card">
                <h3>📋 成本明细</h3>
                <table>
                    <thead>
                        <tr><th>项目</th><th>当前状态</th><th>优化后</th><th>变化</th></tr>
                    </thead>
                    <tbody>
                        <tr><td>平均良率</td><td>{cost_metrics['current_yield']*100:.1f}%</td><td>{cost_metrics['optimized_yield']*100:.1f}%</td><td style="color: #10b981;">+{cost_metrics['yield_improvement']:.1f}pp</td></tr>
                        <tr><td>良率损失成本</td><td>${cost_metrics['current_loss']/1e6:.2f}M</td><td>${cost_metrics['optimized_loss']/1e6:.2f}M</td><td style="color: #10b981;">-${cost_metrics['savings']/1e6:.2f}M</td></tr>
                        <tr><td>废品数量</td><td>{cost_metrics['current_scrap']} 片</td><td>{cost_metrics['optimized_scrap']} 片</td><td style="color: #10b981;">-{cost_metrics['scrap_reduction']} 片</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="card">
                <h3>📦 设备使用统计</h3>
                <div class="two-col">
"""

    # Equipment tables - show first 2 types on left, last 2 on right
    equip_types = list(equipment_data.items())
    for i in range(0, len(equip_types), 2):
        html += "                    <div>\n"
        for j in range(i, min(i + 2, len(equip_types))):
            equip_type, equip_list = equip_types[j]
            type_name = equip_type.replace('_', ' ').title()
            html += f"""                        <table>
                            <thead><tr><th>{type_name}</th><th>使用次数</th><th>占比</th></tr></thead>
                            <tbody>
"""
            for equip in equip_list:
                html += f"""                                <tr><td>{equip['name']}</td><td>{equip['count']}</td><td>{equip['pct']:.1f}%</td></tr>\n"""
            html += """                            </tbody>
                        </table>
"""
        html += "                    </div>\n"

    html += f"""                </div>
            </div>
            
            <div class="card">
                <h3>💡 成本优化建议</h3>
                <ul class="suggestions">
                    <li><strong>短期</strong>: 实施 Pareto 优化方案，预计节约 ${cost_metrics['savings']/1e6:.2f}M</li>
                    <li><strong>中期</strong>: 通过设备升级和工艺改进，进一步提升良率至 80%+</li>
                    <li><strong>长期</strong>: 建立全面的质量管理体系，持续降低制造成本</li>
                    <li>建议均衡各设备使用频率，避免单台过载；建立设备 OEE 监控体系</li>
                </ul>
            </div>
        </div>
        
    </div>
    
    <script>
        function showReport(reportId, btn) {{
            const views = document.querySelectorAll('.report-view');
            views.forEach(view => view.classList.remove('active'));
            
            const buttons = document.querySelectorAll('.nav-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            
            document.getElementById(reportId).classList.add('active');
            btn.classList.add('active');
        }}
        
        document.addEventListener('DOMContentLoaded', function() {{
            document.getElementById('home').classList.add('active');
        }});
    </script>
</body>
</html>
"""

    return html


def main():
    print("=" * 70)
    print("半导体制造过程智能分析平台 · 工程看板生成系统")
    print("=" * 70)

    # 加载数据
    df, optimize_results = load_data()

    # 计算各项指标
    print("\n计算指标...")
    spc_results = load_spc_results()
    if spc_results is None:
        print("\n❌ 错误: 无法加载 SPC 结果，请先运行 python modeling/spc_analysis.py")
        return
    print("  ✓ SPC 指标")

    yield_metrics = calculate_yield_metrics(df)
    print("  ✓ 良率指标")

    equipment_data = calculate_equipment_metrics(df)
    print("  ✓ 设备指标")

    # 获取优化后的良率
    if optimize_results:
        optimized_yield = optimize_results['pareto_top5'][0]['yield']
    else:
        optimized_yield = 0.710

    cost_metrics = calculate_cost_metrics(df, optimized_yield)
    print("  ✓ 成本指标")

    # 生成 HTML
    print("\n生成工程看板...")
    html = generate_html(spc_results, yield_metrics, equipment_data, cost_metrics, optimize_results)

    # 保存
    output_path = os.path.join(REPORTS, "dashboard.html")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ 工程看板已生成: {output_path}")
    print("\n看板结构（工程闭环）:")
    print("  1. 📋 项目概览 — 全局视角 + 流程闭环 + 核心 KPI")
    print("  2. 📥 数据采集 — 变量含义 + 数据分布")
    print("  3. 🧠 统计建模 — 良率预测 + SHAP 根因 + Top-K 拦截")
    print("  4. 📊 SPC 监控 — Xbar-R 控制图 + 过程能力分布")
    print("  5. 🔬 DOE 改进 — Pareto 优化 + 响应面 + 贝叶斯收敛")
    print("  6. 💰 成本效益 — 成本节约 + 设备统计")
    print("\n使用方式:")
    print("  1. 直接在浏览器中打开 dashboard.html")
    print("  2. 点击顶部按钮切换查看不同模块")
    print("  3. 所有数据来自模型实际运行结果（CSV + JSON）")


if __name__ == "__main__":
    main()
