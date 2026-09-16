"""生成各变量的分布图：箱线图 + 分布曲线 + 离散点融合"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import stats
from pathlib import Path

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

data_path = Path(__file__).parent / 'data' / 'semiconductor_yield_forecasting_data.csv'
df = pd.read_csv(data_path)
fig_dir = Path(__file__).parent / 'reports' / 'figures'
fig_dir.mkdir(exist_ok=True)

# 需要画分布图的数值变量
numeric_cols = [
    'etch_rate', 'pressure', 'temperature', 'exposure_time', 'focus_offset',
    'dose', 'deposition_rate', 'thickness_uniformity', 'implant_energy',
    'tilt_angle', 'critical_dimension', 'oxide_thickness', 'resistivity',
    'defect_count', 'defect_density', 'vth', 'leakage_current', 'resistance', 'yield'
]

# 变量中文名映射
var_names = {
    'etch_rate': '刻蚀速率', 'pressure': '压力', 'temperature': '温度',
    'exposure_time': '曝光时间', 'focus_offset': '聚焦偏移', 'dose': '注入剂量',
    'deposition_rate': '沉积速率', 'thickness_uniformity': '膜厚均匀性',
    'implant_energy': '注入能量', 'tilt_angle': '倾斜角度',
    'critical_dimension': '关键尺寸(CD)', 'oxide_thickness': '氧化层厚度',
    'resistivity': '电阻率', 'defect_count': '缺陷数', 'defect_density': '缺陷密度',
    'vth': '阈值电压', 'leakage_current': '漏电流', 'resistance': '电阻', 'yield': '良率'
}

for col in numeric_cols:
    fig, axes = plt.subplots(1, 2, figsize=(14, 4), gridspec_kw={'width_ratios': [1, 3]})
    
    data = df[col].values
    
    # --- 左图：箱线图 ---
    bp = axes[0].boxplot(data, vert=True, patch_artist=True, widths=0.5,
                          boxprops=dict(facecolor='#667eea', alpha=0.6, edgecolor='#4f46e5'),
                          medianprops=dict(color='#ef4444', linewidth=2),
                          whiskerprops=dict(color='#4f46e5', linewidth=1.5),
                          capprops=dict(color='#4f46e5', linewidth=1.5))
    
    # 标出离散点（IQR方法）
    Q1, Q3 = np.percentile(data, [25, 75])
    IQR = Q3 - Q1
    lower = Q1 - 1.5 * IQR
    upper = Q3 + 1.5 * IQR
    outliers = data[(data < lower) | (data > upper)]
    
    if len(outliers) > 0:
        # 在箱线图右侧抖动显示离散点
        x_jitter = np.random.normal(1.0, 0.04, len(outliers))
        axes[0].scatter(x_jitter, outliers, c='#ef4444', s=15, alpha=0.6, zorder=5, label=f'离散点({len(outliers)})')
        axes[0].legend(fontsize=8, loc='upper right')
    
    axes[0].set_title(f'{var_names.get(col, col)}\n箱线图', fontsize=11, fontweight='bold')
    axes[0].set_ylabel(col, fontsize=9)
    axes[0].tick_params(labelsize=8)
    
    # --- 右图：分布曲线 + 散点 ---
    # KDE 分布曲线
    kde = stats.gaussian_kde(data)
    x_range = np.linspace(data.min() - (data.max()-data.min())*0.05, 
                          data.max() + (data.max()-data.min())*0.05, 200)
    y_kde = kde(x_range)
    
    axes[1].fill_between(x_range, y_kde, alpha=0.3, color='#667eea', label='分布密度')
    axes[1].plot(x_range, y_kde, color='#4f46e5', linewidth=2, label='KDE')
    
    # 在分布曲线底部画散点（rug plot风格）
    y_rug = np.zeros(len(data))
    # 离散点用红色，正常点用蓝色
    normal_mask = (data >= lower) & (data <= upper)
    axes[1].scatter(data[normal_mask], y_rug[normal_mask], c='#667eea', s=8, alpha=0.3, zorder=3)
    axes[1].scatter(outliers, np.zeros(len(outliers)), c='#ef4444', s=12, alpha=0.7, zorder=4, 
                    marker='x', label=f'离散点({len(outliers)})')
    
    # 均值和中位数线
    axes[1].axvline(np.mean(data), color='#10b981', linestyle='--', linewidth=1.5, label=f'均值={np.mean(data):.2f}')
    axes[1].axvline(np.median(data), color='#f59e0b', linestyle='--', linewidth=1.5, label=f'中位数={np.median(data):.2f}')
    
    axes[1].set_title(f'{var_names.get(col, col)} 分布', fontsize=11, fontweight='bold')
    axes[1].set_xlabel(col, fontsize=9)
    axes[1].set_ylabel('密度', fontsize=9)
    axes[1].legend(fontsize=8, loc='upper right')
    axes[1].tick_params(labelsize=8)
    
    plt.tight_layout()
    fig.savefig(fig_dir / f'distribution_{col}.png', dpi=120, bbox_inches='tight')
    plt.close(fig)
    print(f'✓ {col} ({var_names.get(col, col)}): {len(outliers)} outliers')

print(f'\nAll {len(numeric_cols)} distribution charts saved to {fig_dir}')
