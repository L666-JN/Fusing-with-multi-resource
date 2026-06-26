# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指导。

## 项目概述

多源海事传感器数据融合系统，融合雷达、AIS（自动识别系统）、BDS（北斗）和 R-Mode 数据进行船舶跟踪。系统处理异构传感器流，通过匈牙利分配算法将无标签观测匹配到已知航迹，并输出融合轨迹。

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行主融合流水线
python main.py

# 启动实时轨迹监控器（在 main.py 运行输出时使用）
python visualization/realtime_viewer.py

# 生成静态多源对比图
python visualization/visualize_tracks.py
```

数据处理工具（位于 `Goose/data_processing/`）：

```bash
python Goose/data_processing/radar_json_to_csv.py   # 雷达 JSON → CSV 转换
python Goose/data_processing/remove_bds_mmsi.py      # 去除北斗数据中的 MMSI
```

分析工具（位于 `Goose/analysis/`）：

```bash
python Goose/analysis/analyze_fusion.py              # 融合结果分析
python Goose/analysis/analyze_fusion_fixed.py         # 修正版（含错误修正）
python Goose/analysis/check_mmsi.py                   # MMSI 校验
python Goose/analysis/check_specific_mmsi.py          # 单 MMSI 轨迹检查
python Goose/analysis/debug_mmsi.py                   # MMSI 调试
```

本项目暂无测试。

## 架构

### 三分支融合流水线（`main.py`）

主循环按时间戳回放传感器数据，将每条观测路由至以下三个分支之一：

1. **骨干航迹分支（AIS、R-Mode）** — 具有全球唯一 MMSI 标识的源直接驱动 `SimpleWeightedManager.update()` 中的类卡尔曼状态估计器。每条观测初始化或更新一条航迹。

2. **时间窗口匈牙利分支（雷达）** — 雷达没有 MMSI。观测被缓冲为 `TIME_WINDOW_MS`（3秒）批次。窗口关闭时，`execute_hungarian_match()` 在所有活动骨干航迹（运动学外推至观测时刻）与所有缓冲的雷达点之间构建代价矩阵，然后使用 `scipy.optimize.linear_sum_assignment` 求解分配。经过 500m 动态波门筛选的匹配对被融合到对应航迹中。

3. **事件驱动匈牙利分支（BDS）** — 去除 MMSI 后的北斗数据立即（无缓冲）与活动骨干航迹进行匹配，使用相同的匈牙利 + 运动学外推逻辑，但采用时间膨胀后的动态波门以吸收低频更新带来的较大预测误差。

### 加权融合引擎（`src/core/weighted_fusion.py`）

`SimpleWeightedManager` 按 MMSI 维护航迹状态，并配备按源区分的定位/速度权重：

```python
self.pos_weights = {"ais": 0.8, "bds": 0.4, "rmode": 0.3, "radar": 0.2}
self.vel_weights = {"ais": 0.8, "bds": 0, "rmode": 0, "radar": 0.1}
```

每次更新时：
- 使用最新已知的速度/航向，将航迹运动学外推至观测时间戳
- 应用指数平滑：`new_x = (1-α) * pred_x + α * obs_x`
- 速度：源数据中有则直接使用（AIS、雷达），否则继承（BDS、R-Mode）
- 航向：使用角度感知插值进行平滑（处理 0°/360° 跳变）
- 艏向：对 AIS 数据使用 511 哨兵值过滤（511 = 无效值）

### 数据回放引擎（`src/ingestion/replayer.py`）

`LocalDataReplayer` 加载 JSON 传感器文件，注入 `_sys_source_type` 标签，按 `recvTs` 对合并后的数据流排序，按 `(mmsi, recvTs)` 去重，然后按时间顺序逐条产出数据。`speed_factor` 参数控制回放速率（当前设为 600×，为批量处理已将实际的 `time.sleep` 注释掉）。

### 坐标系（`src/utils/geo_transform.py`）

所有融合运算均以 (38.475°N, 121.086°E) 为原点的本地 ENU 笛卡尔平面（米）进行。原始传感器坐标为缩放整数（×10⁶）；`revert_scaled_coord()` 恢复为十进制度数，然后 `wgs84_to_enu_2d()` 使用球面等距近似将其投影到平面（x=东, y=北）。输出结果在写入 CSV 之前通过 `enu_2d_to_wgs84()` 投影回 WGS-84。

### 输出格式

`data/output_tracks/final_fusion.csv` — 10列：
`timestamp, mmsi, latitude, longitude, speed, heading, course, source, radar_track_number, radar_speed`

`source` 字段为所有已贡献数据至该航迹的数据源列表，以分号分隔。

## 关键设计决策

- **500m 动态波门**：统一应用于雷达和 BDS 匹配（在 `execute_hungarian_match` 中硬编码）。距外推航迹位置超过 500m 的观测将被剔除。
- **速度方向继承**：当数据源不携带本地速度时（BDS、R-Mode），航迹保留其最后已知速度，而非从位置差分推导速度，以避短时间间隔下的数值噪声放大。
- **AIS 航向为权威源**：AIS 提供的航向直接使用；对于其他数据源，仅当速度超过 1 节时才从位置差分计算航向，低于此阈值时保留现有航向。
- **雷达不进行航位推算**：雷达代价矩阵使用骨干航迹最后状态的运动学外推，而非从雷达自身做航位推算预测，因为雷达观测不携带身份信息。
