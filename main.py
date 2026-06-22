import csv
import math
import os
from datetime import datetime, timezone, timedelta
from scipy.optimize import linear_sum_assignment  # 匈牙利算法核心
import numpy as np
import pandas as pd

from src.ingestion.replayer import LocalDataReplayer
from src.utils.geo_transform import GeoTransformer
from src.core.weighted_fusion import SimpleWeightedManager

CENTER_LAT, CENTER_LON = 38.475000, 121.086000
OUTPUT_PATH = "data/output_tracks/final_fusion.csv"

# ================= 配置区 =================
# 设定固定时间窗大小（毫秒）。例如 3000 代表每 3 秒执行一次雷达批处理与匹配
TIME_WINDOW_MS = 3000


# ==========================================

def main():
    sensor_files = {
        "ais": "data/raw_sensor/ais.json",
        "radar": "data/raw_sensor/radar.json",
        "bds": "data/raw_sensor/bds_no_mmsi.json",  # 修改点：指向无mmsi的北斗数据
        "rmode": "data/raw_sensor/rmode.json"
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    replayer = LocalDataReplayer(speed_factor=600.0)
    geo_transformer = GeoTransformer(CENTER_LAT, CENTER_LON)
    fusion_manager = SimpleWeightedManager()

    # --- 1. 严格按照要求初始化 CSV 表头 (新增雷达追踪字段) ---
    headers = [
        "timestamp", "mmsi", "latitude", "longitude", "speed",
        "heading", "course", "source", "radar_track_number", "radar_speed"
    ]
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(headers)

    radar_buffer = []

    # 【新增】时间窗控制变量
    current_window_end = None

    replayer.load_files(sensor_files)
    print(
        f"二级融合启动：骨干生成 + 无标识信源匈牙利匹配 (雷达基于 {TIME_WINDOW_MS / 1000}秒 时间窗, 北斗基于事件驱动)...")

    for data in replayer.replay_generator():

        s_type = data.get('_sys_source_type')

        # 异常数据阻断：如果存在不属于这四类的未知标签，直接丢弃
        if s_type not in ["ais", "radar", "rmode", "bds"]:
            continue

        ts = data['recvTs']

        # 【核心逻辑】：初始化时间窗边界
        if current_window_end is None:
            current_window_end = ts + TIME_WINDOW_MS

        # 【核心逻辑】：检查当前数据时间戳是否已越过时间窗边界 (针对雷达)
        if ts >= current_window_end:
            if radar_buffer:
                # 触发匈牙利匹配：清空本窗口内积攒的所有雷达点
                execute_hungarian_match(radar_buffer, "radar", fusion_manager, geo_transformer)
                radar_buffer = []

            # 滑动时间窗：使用 while 循环以防数据流中存在长时间的空白断层
            while ts >= current_window_end:
                current_window_end += TIME_WINDOW_MS

        # 坐标投影
        lat_raw = geo_transformer.revert_scaled_coord(data.get('latitude', 0))
        lon_raw = geo_transformer.revert_scaled_coord(data.get('longitude', 0))
        x_m, y_m = geo_transformer.wgs84_to_enu_2d(lat_raw, lon_raw)

        # ================= 分支 1：骨干航迹驱动 (AIS, R-Mode) =================
        if s_type in ["ais", "rmode"]:
            mmsi = data.get('mmsi')
            if not mmsi: continue

            # 提取基础数据
            raw_heading = data.get('heading')
            raw_course = data.get('course')
            raw_speed = data.get('speed')

            # 针对 AIS 协议的特定量纲还原
            if s_type == "ais":
                if raw_speed is not None:
                    raw_speed = (raw_speed / 10.0) if raw_speed != 1023 else None

                if raw_course is not None:
                    raw_course = (raw_course / 10.0) if raw_course != 3600 else None

                if raw_heading == 511:
                    raw_heading = None

            # 执行状态机更新 (传入还原后的物理参数)
            res = fusion_manager.update(
                mmsi, x_m, y_m, ts, s_type,
                raw_heading, raw_course, raw_speed
            )
            write_result(res, geo_transformer, OUTPUT_PATH)

        # ================= 分支 2：高频无标识信源 (雷达数据缓存分支) =================
        elif s_type == "radar":
            data['x_m'], data['y_m'] = x_m, y_m

            raw_radar_speed = data.get('speed')
            data['speed_reverted'] = (raw_radar_speed / 100.0) if raw_radar_speed is not None else 0.0

            raw_radar_course = data.get('course')
            data['course_reverted'] = (raw_radar_course / 10.0) if raw_radar_course is not None else None
            radar_buffer.append(data)

        # ================= 分支 3：低频无标识信源 (北斗数据，事件驱动即时匹配) =================
        elif s_type == "bds":
            data['x_m'], data['y_m'] = x_m, y_m
            # 包装为列表直接触发匹配，不进入时间窗积攒
            execute_hungarian_match([data], "bds", fusion_manager, geo_transformer)

    if radar_buffer:
        execute_hungarian_match(radar_buffer, "radar", fusion_manager, geo_transformer)

    print(f"融合完成，结果见: {OUTPUT_PATH}")
    # ================= 新增调用区 =================
    # 定义输出的 Excel 文件路径
    excel_output_path = "data/output_tracks/comprehensive_data.xlsx"
    # export_to_excel(OUTPUT_PATH, sensor_files, excel_output_path)
    # ==============================================


def execute_hungarian_match(batch, sensor_type, fusion_manager, geo_transformer):
    """泛化的无标识数据源匹配逻辑（引入运动学外推预测与动态波门）"""
    backbones = fusion_manager.get_active_backbones()
    if not backbones or not batch: return

    # 构建距离代价矩阵
    cost_matrix = np.zeros((len(backbones), len(batch)))
    for i, b in enumerate(backbones):
        # 1. 提取航迹最后已知状态
        trk_x = b['x']
        trk_y = b['y']
        trk_ts = b['last_ts']

        # 提取速度（节），并转换为 米/秒 (1 节 ≈ 0.5144 m/s)
        speed_knots = b.get('speed', 0.0)
        speed_ms = speed_knots * 0.5144

        # 提取航向角（优先使用航向 course，退化使用艏向 heading）
        course_deg = b.get('course')
        if course_deg is None:
            course_deg = b.get('heading', 0.0)

        # 2. 速度向量分解 (ENU坐标系下，正北为0度，顺时针。Y轴指向北，X轴指向东)
        if course_deg is not None:
            course_rad = math.radians(course_deg)
            vx = speed_ms * math.sin(course_rad)
            vy = speed_ms * math.cos(course_rad)
        else:
            vx, vy = 0.0, 0.0

        for j, obs in enumerate(batch):
            obs_ts = obs['recvTs']

            # 3. 计算时间差 (毫秒转为秒)
            dt_seconds = max((obs_ts - trk_ts) / 1000.0, 0.0)

            # 4. 状态外推 (计算预测坐标)
            pred_x = trk_x + vx * dt_seconds
            pred_y = trk_y + vy * dt_seconds

            # 5. 计算观测点与外推预测点之间的真实残差距离
            dist = math.sqrt((pred_x - obs['x_m']) ** 2 + (pred_y - obs['y_m']) ** 2)
            if dist < 400 :
                cost_matrix[i, j] = dist
            else :
                cost_matrix[i, j] = 9999


    
    # 执行匈牙利算法
    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    for b_idx, obs_idx in zip(row_ind, col_ind):
        # 计算真实外推差
        trk_ts = backbones[b_idx]['last_ts']
        obs_ts = batch[obs_idx]['recvTs']
        dt_seconds = max((obs_ts - trk_ts) / 1000.0, 0.0)

        # 动态波门计算 - 统一设为500m
        gate_dist = 500.0  # 匈牙利匹配后500m过滤阈值

        # 执行截获判定
        if cost_matrix[b_idx, obs_idx] < gate_dist:
            target_mmsi = backbones[b_idx]['mmsi']
            obs_pt = batch[obs_idx]

            # 区分信源提取特定的物理量
            raw_speed = obs_pt.get('speed_reverted') if sensor_type == "radar" else None
            raw_course = obs_pt.get('course_reverted') if sensor_type == "radar" else None

            res = fusion_manager.update(
                target_mmsi,
                obs_pt['x_m'],
                obs_pt['y_m'],
                obs_pt['recvTs'],
                sensor_type,
                None,  # 均无艏向
                raw_course,
                raw_speed
            )

            # 【核心修改点】：提取当前匹配成功的雷达点特定追踪属性
            track_number = obs_pt.get('trackNumber', "") if sensor_type == "radar" else ""
            radar_speed_val = obs_pt.get('speed_reverted', "") if sensor_type == "radar" else ""

            write_result(res, geo_transformer, OUTPUT_PATH, track_number=track_number, radar_speed=radar_speed_val)


def write_result(res_dict, geo_transformer, path, track_number="", radar_speed=""):
    f_lat, f_lon = geo_transformer.enu_2d_to_wgs84(res_dict['x'], res_dict['y'])

    # 【修改点 3】：安全格式化 None 值，避免 TypeError
    # 如果值为 None，输出空字符串，否则保留 1 位小数
    heading_val = res_dict.get('heading')
    course_val = res_dict.get('course')

    heading_str = f"{heading_val:.1f}" if heading_val is not None else ""
    course_str = f"{course_val:.1f}" if course_val is not None else ""

    # 对雷达速度进行格式化输出控制
    if isinstance(radar_speed, (int, float)):
        radar_speed_str = f"{radar_speed:.2f}"
    elif radar_speed != "":
        radar_speed_str = str(radar_speed)
    else:
        radar_speed_str = ""

    with open(path, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([
            res_dict['last_ts'],  # 毫秒级时间戳
            res_dict.get('mmsi', "N/A"),  # MMSI
            round(f_lat, 6),  # 纬度
            round(f_lon, 6),  # 经度
            round(res_dict['speed'], 2),  # 航速
            heading_str,  # 安全处理后的艏向字符串
            course_str,  # 安全处理后的航向字符串
            ";".join(res_dict['sources']),  # 标签汇聚
            track_number,  # 新增字段：雷达批处理航迹号
            radar_speed_str  # 新增字段：雷达预处理后的真实物理速度（节）
        ])


def export_to_excel(csv_path, json_files_dict, output_excel_path):
    """
    将融合结果和原始传感器数据横向拼接为一个宽表，输出至单个 Excel Sheet 中。
    不同长度的数据源自动以空白(NaN)补齐。
    """
    print(f"\n开始生成横向拼接Excel文件: {output_excel_path} ...")
    os.makedirs(os.path.dirname(output_excel_path), exist_ok=True)

    dfs_to_concat = []

    # 1. 提取并处理融合结果 (CSV)
    if os.path.exists(csv_path):
        df_fusion = pd.read_csv(csv_path)
        # 增加列前缀，防止列名冲突
        df_fusion = df_fusion.add_prefix('融合_')
        dfs_to_concat.append(df_fusion)
    else:
        print(f"警告：未找到融合结果文件 {csv_path}")

    # 定义后续读取顺序和对应的列前缀
    sensor_order = [
        ('ais', 'AIS_'),
        ('bds', '北斗_'),
        ('rmode', 'R模式_'),
        ('radar', '雷达_')
    ]

    # 2. 依次提取各个 JSON 数据源
    for key, prefix in sensor_order:
        file_path = json_files_dict.get(key)
        if file_path and os.path.exists(file_path):
            try:
                df_sensor = pd.read_json(file_path)
            except ValueError:
                df_sensor = pd.read_json(file_path, lines=True)

            # 增加列前缀
            df_sensor = df_sensor.add_prefix(prefix)
            dfs_to_concat.append(df_sensor)
        else:
            print(f"警告：未找到传感器文件 {file_path}")

    # 3. 执行横向拼接核心逻辑
    if not dfs_to_concat:
        print("未找到任何有效数据，终止 Excel 导出。")
        return

    # axis=1 表示按列横向拼接；长度不足的部分自动填入 NaN
    df_combined = pd.concat(dfs_to_concat, axis=1)

    # 4. 落盘写入 Excel
    with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
        df_combined.to_excel(writer, sheet_name='综合横向拼接数据', index=False)

    print(f"横向拼接完毕，存储路径: {output_excel_path}")


if __name__ == "__main__":
    main()