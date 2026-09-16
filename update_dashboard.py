"""修改 dashboard.html: 项目概览+数据分析+数据工程+建模"""
import re
from pathlib import Path

html_path = Path(__file__).parent / 'reports' / 'dashboard.html'
content = html_path.read_text(encoding='utf-8')

# ============================================================
# 1. 项目概览：顶部添加数据来源信息卡片
# ============================================================
# 在 STAR 项目背景之前插入数据来源卡片
data_source_card = '''
            <!-- 数据来源信息 -->
            <div class="card" style="border-left: 4px solid #10b981;">
                <h3>📡 数据来源与记录</h3>
                <div class="two-col">
                    <div>
                        <table>
                            <tr><td><strong>数据来源</strong></td><td>MES（制造执行系统）产线数据库</td></tr>
                            <tr><td><strong>数据时间范围</strong></td><td>2023-01-01 ~ 2023-02-19（50 天）</td></tr>
                            <tr><td><strong>记录内容</strong></td><td>1250 片晶圆的完整制造过程数据</td></tr>
                            <tr><td><strong>涵盖工序</strong></td><td>刻蚀(Etch) → 光刻(Litho) → 沉积(Deposition) → 注入(Implant)</td></tr>
                            <tr><td><strong>产品类型</strong></td><td>CPU / GPU / FPGA / ASIC / Memory</td></tr>
                            <tr><td><strong>技术节点</strong></td><td>7nm / 10nm / 14nm / 22nm / 28nm</td></tr>
                            <tr><td><strong>目标变量</strong></td><td>yield（晶圆良率，0~1）</td></tr>
                        </table>
                    </div>
                    <div>
                        <table>
                            <tr><td><strong>总记录数</strong></td><td>1,250 行 × 28 列</td></tr>
                            <tr><td><strong>批次数</strong></td><td>50 批（每批 25 片晶圆）</td></tr>
                            <tr><td><strong>特征维度</strong></td><td>28 维（9 类别型 + 19 数值型）</td></tr>
                            <tr><td><strong>缺失值</strong></td><td>0（无缺失）</td></tr>
                            <tr><td><strong>重复行</strong></td><td>0（无重复）</td></tr>
                            <tr><td><strong>平均良率</strong></td><td>45.7%（目标 70%）</td></tr>
                            <tr><td><strong>良率标准差</strong></td><td>±17.5%</td></tr>
                        </table>
                    </div>
                </div>
            </div>
'''

# 在 STAR 项目背景之前插入
content = content.replace(
    '            <!-- STAR 项目背景 -->',
    data_source_card + '\n            <!-- STAR 项目背景 -->'
)

# ============================================================
# 2. 导航栏：数据采集 → 数据分析，插入数据工程
# ============================================================
content = content.replace(
    '<button class="nav-btn" onclick="showReport(\'data\', this)">📥 数据采集</button>',
    '<button class="nav-btn" onclick="showReport(\'data\', this)">📊 数据分析</button>'
)

# 在 data 和 modeling 之间插入 data_engineering 导航按钮
content = content.replace(
    '<button class="nav-btn" onclick="showReport(\'modeling\', this)">🧠 统计建模</button>',
    '<button class="nav-btn" onclick="showReport(\'data_eng\', this)">🔧 数据工程</button>\n'
    '            <button class="nav-btn" onclick="showReport(\'modeling\', this)">🧠 统计建模</button>'
)

# ============================================================
# 3. 数据采集 section → 数据分析 section（重命名+内容改造）
# ============================================================

# 3a. 改标题
content = content.replace(
    '<h2>📥 数据采集与背景记录</h2>',
    '<h2>📊 数据分析与分布探索</h2>'
)
content = content.replace(
    '<div class="time">数据来源: MES 产线系统</div>',
    '<div class="time">数据来源: MES 产线系统 | 2023-01-01 ~ 2023-02-19 | 1250行×28列</div>'
)

# 3b. 变量含义表格：添加"数据类型"列
content = content.replace(
    '<tr><th>类别</th><th>变量名</th><th>含义</th><th>单位/范围</th></tr>',
    '<tr><th>类别</th><th>变量名</th><th>数据类型</th><th>含义</th><th>单位/范围</th></tr>'
)

# 给每个变量行添加数据类型列
# 批次信息 - 类别型
content = content.replace(
    '<tr><td rowspan="4"><strong>批次信息</strong></td><td>lot_id</td><td>批次编号</td><td>LOT_0001 ~ LOT_0050</td></tr>',
    '<tr><td rowspan="4"><strong>批次信息</strong></td><td>lot_id</td><td><code>类别型</code></td><td>批次编号</td><td>LOT_0001 ~ LOT_0050</td></tr>'
)
content = content.replace(
    '<tr><td>wafer_id</td><td>晶圆编号</td><td>W001 ~ W025</td></tr>',
    '<tr><td>wafer_id</td><td><code>类别型</code></td><td>晶圆编号</td><td>W001 ~ W025</td></tr>'
)
content = content.replace(
    '<tr><td>product_type</td><td>产品类型</td><td>CPU / GPU / FPGA / ASIC / Memory</td></tr>',
    '<tr><td>product_type</td><td><code>类别型</code></td><td>产品类型</td><td>CPU / GPU / FPGA / ASIC / Memory</td></tr>'
)
content = content.replace(
    '<tr><td>technology_node</td><td>技术节点</td><td>7nm / 10nm / 14nm / 22nm / 28nm</td></tr>',
    '<tr><td>technology_node</td><td><code>类别型</code></td><td>技术节点</td><td>7nm / 10nm / 14nm / 22nm / 28nm</td></tr>'
)

# 设备信息 - 类别型
content = content.replace(
    '<tr><td rowspan="4"><strong>设备信息</strong></td><td>etch_tool</td><td>刻蚀设备</td><td>ETCH_01 ~ ETCH_05</td></tr>',
    '<tr><td rowspan="4"><strong>设备信息</strong></td><td>etch_tool</td><td><code>类别型</code></td><td>刻蚀设备</td><td>ETCH_01 ~ ETCH_05</td></tr>'
)
content = content.replace(
    '<tr><td>litho_tool</td><td>光刻设备</td><td>LITHO_01 ~ LITHO_04</td></tr>',
    '<tr><td>litho_tool</td><td><code>类别型</code></td><td>光刻设备</td><td>LITHO_01 ~ LITHO_04</td></tr>'
)
content = content.replace(
    '<tr><td>deposition_tool</td><td>沉积设备</td><td>DEP_01 ~ DEP_03</td></tr>',
    '<tr><td>deposition_tool</td><td><code>类别型</code></td><td>沉积设备</td><td>DEP_01 ~ DEP_03</td></tr>'
)
content = content.replace(
    '<tr><td>implant_tool</td><td>注入设备</td><td>IMP_01 ~ IMP_03</td></tr>',
    '<tr><td>implant_tool</td><td><code>类别型</code></td><td>注入设备</td><td>IMP_01 ~ IMP_03</td></tr>'
)

# 工艺参数 - 浮点型
content = content.replace(
    '<tr><td rowspan="5"><strong>工艺参数</strong></td><td>etch_rate / pressure / temperature</td><td>刻蚀速率 / 压力 / 温度</td><td>Å/min / mTorr / °C</td></tr>',
    '<tr><td rowspan="5"><strong>工艺参数</strong></td><td>etch_rate / pressure / temperature</td><td><code>浮点型</code></td><td>刻蚀速率 / 压力 / 温度</td><td>Å/min / mTorr / °C</td></tr>'
)
content = content.replace(
    '<tr><td>exposure_time / focus_offset</td><td>曝光时间 / 聚焦偏移</td><td>s / μm</td></tr>',
    '<tr><td>exposure_time / focus_offset</td><td><code>浮点型</code></td><td>曝光时间 / 聚焦偏移</td><td>s / μm</td></tr>'
)
content = content.replace(
    '<tr><td>dose / implant_energy</td><td>注入剂量 / 注入能量</td><td>ions/cm² / keV</td></tr>',
    '<tr><td>dose / implant_energy</td><td><code>浮点型</code></td><td>注入剂量 / 注入能量</td><td>ions/cm² / keV</td></tr>'
)
content = content.replace(
    '<tr><td>deposition_rate / thickness_uniformity</td><td>沉积速率 / 膜厚均匀性</td><td>Å/min / %</td></tr>',
    '<tr><td>deposition_rate / thickness_uniformity</td><td><code>浮点型</code></td><td>沉积速率 / 膜厚均匀性</td><td>Å/min / %</td></tr>'
)
content = content.replace(
    '<tr><td>cd_uniformity / oxide_uniformity</td><td>CD均匀性 / 氧化层均匀性</td><td>%</td></tr>',
    '<tr><td>cd_uniformity / oxide_uniformity</td><td><code>浮点型</code></td><td>CD均匀性 / 氧化层均匀性</td><td>%</td></tr>'
)

# 量测参数 - 浮点型
content = content.replace(
    '<tr><td rowspan="3"><strong>量测参数</strong></td><td>critical_dimension</td><td>关键尺寸 (CD)</td><td>nm, 规格 [15, 35]</td></tr>',
    '<tr><td rowspan="3"><strong>量测参数</strong></td><td>critical_dimension</td><td><code>浮点型</code></td><td>关键尺寸 (CD)</td><td>nm, 规格 [15, 35]</td></tr>'
)
content = content.replace(
    '<tr><td>oxide_thickness</td><td>氧化层厚度</td><td>Å, 规格 [45, 70]</td></tr>',
    '<tr><td>oxide_thickness</td><td><code>浮点型</code></td><td>氧化层厚度</td><td>Å, 规格 [45, 70]</td></tr>'
)
content = content.replace(
    '<tr><td>vth</td><td>阈值电压</td><td>V, 规格 [0.50, 0.80]</td></tr>',
    '<tr><td>vth</td><td><code>浮点型</code></td><td>阈值电压</td><td>V, 规格 [0.50, 0.80]</td></tr>'
)

# 缺陷指标 - 整数型/浮点型
content = content.replace(
    '<tr><td rowspan="2"><strong>缺陷指标</strong></td><td>defect_count</td><td>缺陷数</td><td>个/片</td></tr>',
    '<tr><td rowspan="2"><strong>缺陷指标</strong></td><td>defect_count</td><td><code>整数型</code></td><td>缺陷数</td><td>个/片</td></tr>'
)
content = content.replace(
    '<tr><td>defect_density</td><td>缺陷密度</td><td>个/cm²</td></tr>',
    '<tr><td>defect_density</td><td><code>浮点型</code></td><td>缺陷密度</td><td>个/cm²</td></tr>'
)

# 目标变量
content = content.replace(
    '<tr><td><strong>目标变量</strong></td><td>yield</td><td>良率</td><td>0~1 (百分比)</td></tr>',
    '<tr><td><strong>目标变量</strong></td><td>yield</td><td><code>浮点型</code></td><td>良率</td><td>0~1 (百分比)</td></tr>'
)

# 3c. 在变量含义表格之后、产品类型分布之前，插入"数据前5行"和"分布图"
# 找到数据质量说明的位置，在它之前插入
data_preview_section = '''
            <!-- 数据前5行预览 -->
            <div class="card">
                <h3> 数据前 5 行预览</h3>
                <div style="overflow-x: auto;">
                <table style="font-size: 10px;">
                    <thead>
                        <tr>
                            <th>lot_id</th><th>wafer_id</th><th>product</th><th>node</th>
                            <th>etch_rate</th><th>pressure</th><th>temp</th>
                            <th>exposure</th><th>focus</th><th>dose</th>
                            <th>dep_rate</th><th>thick_uni</th><th>impl_energy</th>
                            <th>tilt</th><th>CD</th><th>oxide</th><th>resist</th>
                            <th>defect_cnt</th><th>defect_dens</th><th>vth</th>
                            <th>leak_curr</th><th>resist_ohm</th><th>yield</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>LOT_0001</td><td>W001</td><td>CPU</td><td>10nm</td>
                            <td>3.560</td><td>149.81</td><td>66.60</td>
                            <td>1.576</td><td>0.020</td><td>1.005e15</td>
                            <td>2.148</td><td>1.673</td><td>49.53</td>
                            <td>6.77</td><td>21.30</td><td>55.60</td><td>1.926</td>
                            <td>664</td><td>0.947</td><td>0.557</td>
                            <td>0.000353</td><td>90.02</td><td>0.679</td>
                        </tr>
                        <tr>
                            <td>LOT_0001</td><td>W002</td><td>CPU</td><td>10nm</td>
                            <td>3.407</td><td>147.35</td><td>66.50</td>
                            <td>1.628</td><td>0.023</td><td>1.003e15</td>
                            <td>1.938</td><td>1.400</td><td>50.95</td>
                            <td>6.68</td><td>20.47</td><td>54.60</td><td>2.340</td>
                            <td>612</td><td>0.811</td><td>0.586</td>
                            <td>0.000122</td><td>103.66</td><td>0.780</td>
                        </tr>
                        <tr>
                            <td>LOT_0001</td><td>W003</td><td>CPU</td><td>10nm</td>
                            <td>3.414</td><td>151.48</td><td>66.78</td>
                            <td>1.509</td><td>0.020</td><td>1.011e15</td>
                            <td>1.842</td><td>1.376</td><td>49.54</td>
                            <td>7.17</td><td>19.36</td><td>55.81</td><td>2.384</td>
                            <td>584</td><td>0.798</td><td>0.625</td>
                            <td>0.000357</td><td>95.05</td><td>0.778</td>
                        </tr>
                        <tr>
                            <td>LOT_0001</td><td>W004</td><td>CPU</td><td>10nm</td>
                            <td>3.495</td><td>142.96</td><td>67.50</td>
                            <td>1.491</td><td>0.019</td><td>9.90e14</td>
                            <td>1.900</td><td>1.687</td><td>50.30</td>
                            <td>6.96</td><td>23.46</td><td>56.99</td><td>2.949</td>
                            <td>673</td><td>0.953</td><td>0.647</td>
                            <td>0.000250</td><td>105.18</td><td>0.405</td>
                        </tr>
                        <tr>
                            <td>LOT_0001</td><td>W005</td><td>CPU</td><td>10nm</td>
                            <td>3.527</td><td>149.00</td><td>65.48</td>
                            <td>1.401</td><td>0.020</td><td>9.95e14</td>
                            <td>2.138</td><td>1.416</td><td>49.19</td>
                            <td>7.46</td><td>22.49</td><td>53.68</td><td>2.654</td>
                            <td>613</td><td>0.818</td><td>0.572</td>
                            <td>0.000198</td><td>98.92</td><td>0.935</td>
                        </tr>
                    </tbody>
                </table>
                </div>
            </div>

            <!-- 变量分布图（箱线图+分布曲线+离散点） -->
            <div class="card chart-section">
                <h3>📈 变量分布探索（箱线图 + 密度曲线 + 离散点）</h3>
                <p style="font-size:12px; color:#666; margin-bottom:12px;">
                    左图为箱线图（红线=中位数，红点=IQR离散点），右图为KDE密度曲线+散点分布（绿虚线=均值，黄虚线=中位数，红×=离散点）
                </p>
                <div class="spc-chart-grid">
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_etch_rate.png" alt="刻蚀速率分布">
                        <h4>刻蚀速率 (etch_rate)</h4>
                        <ul><li>均值 3.62 Å/min，7 个离散点</li><li>分布近似正态，轻微右偏</li></ul>
                    </div>
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_pressure.png" alt="压力分布">
                        <h4>压力 (pressure)</h4>
                        <ul><li>均值 152.7 mTorr，6 个离散点</li><li>分布近似正态</li></ul>
                    </div>
                </div>
                <div class="spc-chart-grid">
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_temperature.png" alt="温度分布">
                        <h4>温度 (temperature)</h4>
                        <ul><li>均值 66.77°C，5 个离散点</li><li>分布近似正态</li></ul>
                    </div>
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_exposure_time.png" alt="曝光时间分布">
                        <h4>曝光时间 (exposure_time)</h4>
                        <ul><li>均值 1.50 s，11 个离散点</li><li>分布近似正态</li></ul>
                    </div>
                </div>
                <div class="spc-chart-grid">
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_focus_offset.png" alt="聚焦偏移分布">
                        <h4>聚焦偏移 (focus_offset)</h4>
                        <ul><li>均值 0.027 μm，6 个离散点</li><li>右偏分布</li></ul>
                    </div>
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_dose.png" alt="注入剂量分布">
                        <h4>注入剂量 (dose)</h4>
                        <ul><li>均值 1.00e15 ions/cm²，8 个离散点</li><li>分布近似正态</li></ul>
                    </div>
                </div>
                <div class="spc-chart-grid">
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_deposition_rate.png" alt="沉积速率分布">
                        <h4>沉积速率 (deposition_rate)</h4>
                        <ul><li>均值 1.90 Å/min，10 个离散点</li><li>分布近似正态</li></ul>
                    </div>
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_thickness_uniformity.png" alt="膜厚均匀性分布">
                        <h4>膜厚均匀性 (thickness_uniformity)</h4>
                        <ul><li>均值 1.70%，8 个离散点</li><li>分布近似正态</li></ul>
                    </div>
                </div>
                <div class="spc-chart-grid">
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_implant_energy.png" alt="注入能量分布">
                        <h4>注入能量 (implant_energy)</h4>
                        <ul><li>均值 49.99 keV，5 个离散点</li><li>分布近似正态</li></ul>
                    </div>
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_tilt_angle.png" alt="倾斜角度分布">
                        <h4>倾斜角度 (tilt_angle)</h4>
                        <ul><li>均值 7.00°，6 个离散点</li><li>分布近似正态</li></ul>
                    </div>
                </div>
                <div class="spc-chart-grid">
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_critical_dimension.png" alt="关键尺寸分布">
                        <h4>关键尺寸 CD (critical_dimension)</h4>
                        <ul><li>均值 24.61 nm，0 个离散点</li><li>分布近似正态，规格[15,35]</li><li><strong>良率最强负相关 (r=-0.65)</strong></li></ul>
                    </div>
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_oxide_thickness.png" alt="氧化层厚度分布">
                        <h4>氧化层厚度 (oxide_thickness)</h4>
                        <ul><li>均值 56.98 Å，1 个离散点</li><li>分布近似正态，规格[45,70]</li><li><strong>良率负相关 (r=-0.51)</strong></li></ul>
                    </div>
                </div>
                <div class="spc-chart-grid">
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_resistivity.png" alt="电阻率分布">
                        <h4>电阻率 (resistivity)</h4>
                        <ul><li>均值 2.50，14 个离散点</li><li>分布近似正态</li></ul>
                    </div>
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_defect_count.png" alt="缺陷数分布">
                        <h4>缺陷数 (defect_count)</h4>
                        <ul><li>均值 682.7 个/片，7 个离散点</li><li>右偏分布</li></ul>
                    </div>
                </div>
                <div class="spc-chart-grid">
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_defect_density.png" alt="缺陷密度分布">
                        <h4>缺陷密度 (defect_density)</h4>
                        <ul><li>均值 0.96 个/cm²，9 个离散点</li><li>右偏分布</li></ul>
                    </div>
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_vth.png" alt="阈值电压分布">
                        <h4>阈值电压 (vth)</h4>
                        <ul><li>均值 0.645 V，3 个离散点</li><li>分布近似正态，规格[0.50,0.80]</li><li><strong>良率负相关 (r=-0.54)</strong></li></ul>
                    </div>
                </div>
                <div class="spc-chart-grid">
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_leakage_current.png" alt="漏电流分布">
                        <h4>漏电流 (leakage_current)</h4>
                        <ul><li>均值 0.000373，<strong>56 个离散点(4.5%)</strong></li><li>严重右偏，长尾分布</li></ul>
                    </div>
                    <div class="spc-chart-cell">
                        <img src="figures/distribution_resistance.png" alt="电阻分布">
                        <h4>电阻 (resistance)</h4>
                        <ul><li>均值 100.72 Ω，2 个离散点</li><li>分布近似正态</li></ul>
                    </div>
                </div>
                <div class="spc-chart-grid">
                    <div class="spc-chart-cell" style="grid-column: 1 / -1; max-width: 600px; margin: 0 auto;">
                        <img src="figures/distribution_yield.png" alt="良率分布">
                        <h4>🎯 目标变量：良率 (yield)</h4>
                        <ul><li>均值 45.7%，标准差 17.5%，5 个离散点</li><li>分布近似正态，范围 [14.8%, 98.2%]</li><li><strong>远低于目标 70%，需工艺优化</strong></li></ul>
                    </div>
                </div>
            </div>
'''

# 在数据质量说明之前插入
content = content.replace(
    '            <div class="card">\n                <h3>💡 数据质量说明</h3>',
    data_preview_section + '\n            <div class="card">\n                <h3> 数据质量说明</h3>'
)

# ============================================================
# 4. 新增"数据工程"section（在 data 和 modeling 之间）
# ============================================================
data_eng_section = '''
        <!-- ==================== 数据工程 ==================== -->
        <div id="data_eng" class="report-view">
            <div class="report-header" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">
                <h2> 数据工程与清洗</h2>
                <div class="time">方法: Pandas + NumPy | 清洗后数据: 1250×28（无删除）</div>
            </div>

            <div class="card">
                <h3> 数据质量检查</h3>
                <div class="metric-grid">
                    <div class="metric-box" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">
                        <div class="metric-label">缺失值</div>
                        <div class="metric-value">0</div>
                        <div class="metric-label">✅ 无需处理</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">
                        <div class="metric-label">重复行</div>
                        <div class="metric-value">0</div>
                        <div class="metric-label">✅ 无需处理</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">
                        <div class="metric-label">IQR 离散点</div>
                        <div class="metric-value">176</div>
                        <div class="metric-label">⚠ 14.1% 记录含离散值</div>
                    </div>
                    <div class="metric-box" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);">
                        <div class="metric-label">类别型变量</div>
                        <div class="metric-value">9</div>
                        <div class="metric-label">需 One-Hot 编码</div>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>🧹 数据清洗步骤</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                    <div style="background: #f0fdf4; border-radius: 8px; padding: 12px; border: 1px solid #bbf7d0;">
                        <h4 style="margin: 0 0 8px 0; color: #166534; font-size: 13px;">✅ Step 1: 缺失值检查</h4>
                        <ul style="margin: 0; padding-left: 16px; font-size: 12px; line-height: 1.8; color: #14532d;">
                            <li>对全部 28 列执行 <code>isnull().sum()</code></li>
                            <li>结果：<strong>0 个缺失值</strong></li>
                            <li>决策：无需插补或删除</li>
                        </ul>
                    </div>
                    <div style="background: #f0fdf4; border-radius: 8px; padding: 12px; border: 1px solid #bbf7d0;">
                        <h4 style="margin: 0 0 8px 0; color: #166534; font-size: 13px;">✅ Step 2: 重复值检查</h4>
                        <ul style="margin: 0; padding-left: 16px; font-size: 12px; line-height: 1.8; color: #14532d;">
                            <li>对全部行执行 <code>duplicated().sum()</code></li>
                            <li>结果：<strong>0 个重复行</strong></li>
                            <li>决策：无需去重</li>
                        </ul>
                    </div>
                    <div style="background: #fefce8; border-radius: 8px; padding: 12px; border: 1px solid #fef08a;">
                        <h4 style="margin: 0 0 8px 0; color: #854d0e; font-size: 13px;">️ Step 3: 异常值检测（IQR 法）</h4>
                        <ul style="margin: 0; padding-left: 16px; font-size: 12px; line-height: 1.8; color: #713f12;">
                            <li>对 19 个数值变量计算 Q1/Q3/IQR</li>
                            <li>判定标准：&lt; Q1-1.5×IQR 或 &gt; Q3+1.5×IQR</li>
                            <li>结果：<strong>176 个离散值</strong>（占 14.1%）</li>
                            <li>最严重：leakage_current（56个，4.5%）</li>
                            <li>决策：<strong>保留</strong>（半导体工艺中离散值可能反映真实工艺波动，非数据错误）</li>
                        </ul>
                    </div>
                    <div style="background: #eff6ff; border-radius: 8px; padding: 12px; border: 1px solid #bfdbfe;">
                        <h4 style="margin: 0 0 8px 0; color: #1e40af; font-size: 13px;">🔄 Step 4: 类别变量编码</h4>
                        <ul style="margin: 0; padding-left: 16px; font-size: 12px; line-height: 1.8; color: #1e3a8a;">
                            <li>9 个类别型变量需编码</li>
                            <li>机台信息（etch_tool/litho_tool/deposition_tool/implant_tool）→ <strong>One-Hot 编码</strong></li>
                            <li>原因：设备差异是良率的<strong>结构性因素</strong></li>
                            <li>product_type / technology_node → One-Hot 编码</li>
                            <li>编码后特征维度：28 → 约 45 维</li>
                        </ul>
                    </div>
                    <div style="background: #eff6ff; border-radius: 8px; padding: 12px; border: 1px solid #bfdbfe;">
                        <h4 style="margin: 0 0 8px 0; color: #1e40af; font-size: 13px;">🔄 Step 5: 数据切分策略</h4>
                        <ul style="margin: 0; padding-left: 16px; font-size: 12px; line-height: 1.8; color: #1e3a8a;">
                            <li>按 <code>process_date</code> 时间排序</li>
                            <li><strong>时间切分</strong>：前 80% 训练 / 后 20% 测试</li>
                            <li>模拟"用过去预测未来"的真实场景</li>
                            <li>避免随机切分导致的数据泄露</li>
                        </ul>
                    </div>
                    <div style="background: #f0fdf4; border-radius: 8px; padding: 12px; border: 1px solid #bbf7d0;">
                        <h4 style="margin: 0 0 8px 0; color: #166534; font-size: 13px;">✅ Step 6: 特征工程</h4>
                        <ul style="margin: 0; padding-left: 16px; font-size: 12px; line-height: 1.8; color: #14532d;">
                            <li>低良率标签：yield &lt; 0.35 → binary=1</li>
                            <li>阈值设定依据：约 28.2% 批次低于此值</li>
                            <li>用于分类模型（ROC-AUC 评估）</li>
                            <li>清洗后数据：1250×28 → 建模输入 ~45 维</li>
                        </ul>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3> 离散点分布汇总</h3>
                <table>
                    <thead>
                        <tr><th>变量</th><th>离散点数</th><th>占比</th><th>处理方式</th></tr>
                    </thead>
                    <tbody>
                        <tr><td>leakage_current</td><td class="status-warn">56</td><td>4.5%</td><td>保留（真实工艺波动）</td></tr>
                        <tr><td>resistivity</td><td class="status-warn">14</td><td>1.1%</td><td>保留</td></tr>
                        <tr><td>exposure_time</td><td>11</td><td>0.9%</td><td>保留</td></tr>
                        <tr><td>deposition_rate</td><td>10</td><td>0.8%</td><td>保留</td></tr>
                        <tr><td>defect_density</td><td>9</td><td>0.7%</td><td>保留</td></tr>
                        <tr><td>dose</td><td>8</td><td>0.6%</td><td>保留</td></tr>
                        <tr><td>thickness_uniformity</td><td>8</td><td>0.6%</td><td>保留</td></tr>
                        <tr><td>etch_rate</td><td>7</td><td>0.6%</td><td>保留</td></tr>
                        <tr><td>defect_count</td><td>7</td><td>0.6%</td><td>保留</td></tr>
                        <tr><td>pressure / focus_offset / tilt_angle</td><td>各6</td><td>各0.5%</td><td>保留</td></tr>
                        <tr><td>temperature / implant_energy</td><td>各5</td><td>各0.4%</td><td>保留</td></tr>
                        <tr><td>yield</td><td>5</td><td>0.4%</td><td>保留</td></tr>
                        <tr><td>vth</td><td>3</td><td>0.2%</td><td>保留</td></tr>
                        <tr><td>resistance</td><td>2</td><td>0.2%</td><td>保留</td></tr>
                        <tr><td>oxide_thickness</td><td>1</td><td>0.1%</td><td>保留</td></tr>
                        <tr><td>critical_dimension</td><td class="status-pass">0</td><td>0%</td><td>无需处理</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
'''

# 在 modeling section 之前插入
content = content.replace(
    '        <!-- ==================== 3. 统计建模与根因分析 ==================== -->',
    data_eng_section + '\n        <!-- ==================== 3. 统计建模与根因分析 ==================== -->'
)

# ============================================================
# 5. 建模 section：增加数学方程和建模过程
# ============================================================

# 在模型性能概览之后、图表之前插入数学方程和建模过程
modeling_math_section = '''
            <!-- 建模数学方程 -->
            <div class="card" style="border-left: 4px solid #f093fb;">
                <h3>📐 建模数学方程</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                    <div style="background: #fdf4ff; border-radius: 8px; padding: 12px; border: 1px solid #e879f9;">
                        <h4 style="margin: 0 0 8px 0; color: #86198f; font-size: 13px;">XGBoost 目标函数</h4>
                        <div style="font-family: 'Cambria Math', 'Times New Roman', serif; font-size: 13px; line-height: 2; color: #4a044e;">
                            <p style="margin: 4px 0;">L(θ) = Σᵢ l(ŷᵢ, yᵢ) + Σₖ Ω(fₖ)</p>
                            <p style="margin: 4px 0; font-size: 12px;">其中：</p>
                            <ul style="margin: 4px 0; padding-left: 16px; font-size: 11px; line-height: 1.8;">
                                <li>l(ŷ, yᵢ)：损失函数（回归用平方损失）</li>
                                <li>Ω(fₖ) = γT + ½λ||w||²：正则化项</li>
                                <li>T：叶子节点数，w：叶子权重</li>
                                <li>γ=1（最小分裂损失），λ=1（L2正则）</li>
                            </ul>
                        </div>
                    </div>
                    <div style="background: #fdf4ff; border-radius: 8px; padding: 12px; border: 1px solid #e879f9;">
                        <h4 style="margin: 0 0 8px 0; color: #86198f; font-size: 13px;">XGBoost 分裂增益</h4>
                        <div style="font-family: 'Cambria Math', 'Times New Roman', serif; font-size: 13px; line-height: 2; color: #4a044e;">
                            <p style="margin: 4px 0;">Gain = ½[G_L²/(H_L+λ) + G_R²/(H_R+λ) - (G_L+G_R)²/(H_L+H_R+λ)] - γ</p>
                            <p style="margin: 4px 0; font-size: 12px;">其中：</p>
                            <ul style="margin: 4px 0; padding-left: 16px; font-size: 11px; line-height: 1.8;">
                                <li>G_L, G_R：左右子树的一阶梯度和</li>
                                <li>H_L, H_R：左右子树的二阶梯度和</li>
                                <li>选择 Gain 最大的特征和分裂点</li>
                            </ul>
                        </div>
                    </div>
                    <div style="background: #f0fdf4; border-radius: 8px; padding: 12px; border: 1px solid #86efac;">
                        <h4 style="margin: 0 0 8px 0; color: #166534; font-size: 13px;">SHAP 值（特征归因）</h4>
                        <div style="font-family: 'Cambria Math', 'Times New Roman', serif; font-size: 13px; line-height: 2; color: #14532d;">
                            <p style="margin: 4px 0;">φᵢ = Σ_{S⊆F\\{i}} |S|!(|F|-|S|-1)!/|F|! × [f(S{i}) - f(S)]</p>
                            <p style="margin: 4px 0; font-size: 12px;">其中：</p>
                            <ul style="margin: 4px 0; padding-left: 16px; font-size: 11px; line-height: 1.8;">
                                <li>φᵢ：特征 i 的 SHAP 值（贡献度）</li>
                                <li>F：全部特征集合</li>
                                <li>S：不含 i 的特征子集</li>
                                <li>f(S)：子集 S 的模型预测值</li>
                            </ul>
                        </div>
                    </div>
                    <div style="background: #eff6ff; border-radius: 8px; padding: 12px; border: 1px solid #bfdbfe;">
                        <h4 style="margin: 0 0 8px 0; color: #1e40af; font-size: 13px;">评估指标</h4>
                        <div style="font-family: 'Cambria Math', 'Times New Roman', serif; font-size: 13px; line-height: 2; color: #1e3a8a;">
                            <p style="margin: 4px 0;"><strong>R²</strong> = 1 - Σ(yᵢ-ŷᵢ)²/Σ(y-ȳ)²</p>
                            <p style="margin: 4px 0;"><strong>RMSE</strong> = √(1/n × Σ(yᵢ-ŷᵢ)²)</p>
                            <p style="margin: 4px 0;"><strong>ROC-AUC</strong> = ∫₀¹ TPR(FPR⁻¹(t))dt</p>
                            <p style="margin: 4px 0; font-size: 12px;">本模型：R²=0.82, RMSE=0.073, AUC=0.94</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 建模过程 -->
            <div class="card" style="border-left: 4px solid #f093fb;">
                <h3>🔄 建模流程</h3>
                <div class="pipeline-flow">
                    <div class="pipeline-step step-color-1">
                        <div class="step-num">1</div>
                        <div class="step-title">数据准备</div>
                        <div class="step-desc">One-Hot 编码<br>9个类别变量<br>时间切分 80/20</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-2">
                        <div class="step-num">2</div>
                        <div class="step-title">模型训练</div>
                        <div class="step-desc">XGBoost Regressor<br>100棵树, max_depth=5<br>learning_rate=0.1</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-3">
                        <div class="step-num">3</div>
                        <div class="step-title">模型评估</div>
                        <div class="step-desc">R² / RMSE / MAE<br>ROC-AUC (分类)<br>残差分析</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-4">
                        <div class="step-num">4</div>
                        <div class="step-title">SHAP 归因</div>
                        <div class="step-desc">TreeExplainer<br>特征重要性排序<br>正/负向贡献分析</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-5">
                        <div class="step-num">5</div>
                        <div class="step-title">低良率拦截</div>
                        <div class="step-desc">风险分排序<br>Top-K 覆盖率<br>业务决策支持</div>
                    </div>
                </div>
            </div>
'''

# 在模型性能概览卡片之后、图表 section 之前插入
content = content.replace(
    '            <div class="card chart-section">\n                <h3>📈 统计建模分析</h3>',
    modeling_math_section + '\n            <div class="card chart-section">\n                <h3>📈 统计建模分析</h3>'
)

# ============================================================
# 6. 更新工程闭环流程中的步骤名称
# ============================================================
content = content.replace(
    '<div class="step-title">数据采集与背景</div>',
    '<div class="step-title">数据来源与记录</div>'
)
content = content.replace(
    '<div class="step-title">数据分析与分布</div>',
    '<div class="step-title">数据分析与分布探索</div>'
)

# 在流程中插入数据工程步骤
content = content.replace(
    '''                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-3">
                        <div class="step-num">3</div>
                        <div class="step-title">统计建模与根因</div>''',
    '''                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-3">
                        <div class="step-num">3</div>
                        <div class="step-title">数据工程与清洗</div>
                        <div class="step-desc">缺失值/重复值检查<br>IQR异常值检测<br>One-Hot编码 + 时间切分</div>
                    </div>
                    <div class="pipeline-arrow">→</div>
                    <div class="pipeline-step step-color-4">
                        <div class="step-num">4</div>
                        <div class="step-title">统计建模与根因</div>'''
)
# 更新后续步骤编号
content = content.replace(
    '''                    <div class="pipeline-step step-color-4">
                        <div class="step-num">4</div>
                        <div class="step-title">SPC 与过程能力</div>''',
    '''                    <div class="pipeline-step step-color-5">
                        <div class="step-num">5</div>
                        <div class="step-title">SPC 与过程能力</div>'''
)
content = content.replace(
    '''                    <div class="pipeline-step step-color-5">
                        <div class="step-num">5</div>
                        <div class="step-title">DOE 与工艺改进</div>''',
    '''                    <div class="pipeline-step step-color-6">
                        <div class="step-num">6</div>
                        <div class="step-title">DOE 与工艺改进</div>'''
)

# ============================================================
# 7. 添加 step-color-6 CSS
# ============================================================
content = content.replace(
    '.step-color-5 {',
    '.step-color-6 { background: linear-gradient(135deg, #a78bfa 0%, #7c3aed 100%); }\n        .step-color-5 {'
)

# ============================================================
# 8. 添加 code 标签样式（用于数据类型列）
# ============================================================
if 'code {' not in content and 'code{' not in content:
    content = content.replace(
        '.card table td {',
        '.card table td code { background: #f1f5f9; padding: 1px 6px; border-radius: 4px; font-size: 11px; color: #6366f1; font-family: monospace; }\n        .card table td {'
    )

# ============================================================
# 写入文件
# ============================================================
html_path.write_text(content, encoding='utf-8')
print(f'✓ Dashboard updated: {len(content)} chars, {len(content.splitlines())} lines')
