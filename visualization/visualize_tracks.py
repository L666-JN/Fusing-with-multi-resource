import os
import json
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

# 设置中文字体与负号正常显示
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


def load_json_source(file_path):
    """读取JSON数据源，转换为DataFrame"""
    if not os.path.exists(file_path):
        print(f"警告: 文件 {file_path} 不存在，跳过该数据源。")
        return None
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 假设JSON格式为列表嵌套字典，标准字段：timestamp, lon, lat
    df = pd.DataFrame(data)
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def load_csv_fusion(file_path):
    """读取融合后的CSV数据"""
    if not os.path.exists(file_path):
        print(f"错误: 融合文件 {file_path} 不存在。")
        return None
    df = pd.read_csv(file_path)
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def plot_trajectory_fusion(json_paths, csv_path):
    """绘制多源数据与融合数据的对比图"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    # 定义各数据源的显示样式
    styles = {
        'ais': {'color': '#1f77b4', 'marker': 'o', 'label': 'AIS (原始)', 'markersize': 4},
        'radar': {'color': '#2ca02c', 'marker': 'x', 'label': '雷达 (原始)', 'markersize': 5},
        'bds': {'color': '#ff7f0e', 'marker': '^', 'label': '北斗 (采样)', 'markersize': 4},
        'rmode': {'color': '#9467bd', 'marker': 's', 'label': 'R模式 (采样)', 'markersize': 3},
        'fusion': {'color': '#d62728', 'marker': '*', 'label': '融合轨迹', 'markersize': 6, 'linewidth': 1.5}
    }

    # 1. 加载并绘制原始多源数据
    for src_key, path in json_paths.items():
        df_src = load_json_source(path)
        if df_src is not None and not df_src.empty:
            # 左图：空间轨迹
            ax1.scatter(df_src['lon'], df_src['lat'],
                        color=styles[src_key]['color'],
                        marker=styles[src_key]['marker'],
                        s=styles[src_key]['markersize'] ** 2,
                        label=styles[src_key]['label'],
                        alpha=0.6)
            # 右图：时间-经度序列
            ax2.scatter(df_src['timestamp'], df_src['lon'],
                        color=styles[src_key]['color'],
                        marker=styles[src_key]['marker'],
                        s=styles[src_key]['markersize'] ** 2,
                        alpha=0.5)

    # 2. 加载并绘制融合后的CSV数据
    df_fusion = load_csv_fusion(csv_path)
    if df_fusion is not None and not df_fusion.empty:
        # 左图：融合轨迹连线与点
        ax1.plot(df_fusion['lon'], df_fusion['lat'],
                 color=styles['fusion']['color'],
                 linewidth=styles['fusion']['linewidth'],
                 label=styles['fusion']['label'],
                 zorder=5)
        ax1.scatter(df_fusion['lon'], df_fusion['lat'],
                    color=styles['fusion']['color'],
                    marker=styles['fusion']['marker'],
                    s=styles['fusion']['markersize'] ** 2,
                    zorder=6)

        # 右图：融合时间-经度序列连线
        ax2.plot(df_fusion['timestamp'], df_fusion['lon'],
                 color=styles['fusion']['color'],
                 linewidth=styles['fusion']['linewidth'],
                 label='融合轨迹 (时间维)',
                 zorder=5)

    # 图表基本设置
    # 左图设置 (空间几何)
    ax1.set_title("多源数据空间轨迹融合对比", fontsize=14)
    ax1.set_xlabel("经度 (Longitude)", fontsize=12)
    ax1.set_ylabel("纬度 (Latitude)", fontsize=12)
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.legend(loc='best')
    # 保持地理坐标系比例合理
    ax1.axis('equal')

    # 右图设置 (时间序列)
    ax2.set_title("时间-经度序列特征对比", fontsize=14)
    ax2.set_xlabel("时间 (Timestamp)", fontsize=12)
    ax2.set_ylabel("经度 (Longitude)", fontsize=12)
    ax2.grid(True, linestyle='--', alpha=0.5)
    plt.xticks(rotation=30)

    plt.tight_layout()

    # 保存并展示
    output_fig = "multi_source_fusion_vis.png"
    plt.savefig(output_fig, dpi=300)
    print(f"可视化图表已保存至: {output_fig}")
    plt.show()


if __name__ == "__main__":
    # 请根据实际文件路径进行修改
    file_config = {
        'json_paths': {
            'ais': r'D:\研究生阶段\刘佳宁\海创\子课题2.3\多源数据匹配融合研究\Multi-source_data_real-time_fusion system_260430\data\raw_sensor\ais.json',
            'radar': r'D:\研究生阶段\刘佳宁\海创\子课题2.3\多源数据匹配融合研究\Multi-source_data_real-time_fusion system_260430\data\raw_sensor\radar.json',
            'bds': r'D:\研究生阶段\刘佳宁\海创\子课题2.3\多源数据匹配融合研究\Multi-source_data_real-time_fusion system_260430\data\raw_sensor\bds.json',
            'rmode': r'D:\研究生阶段\刘佳宁\海创\子课题2.3\多源数据匹配融合研究\Multi-source_data_real-time_fusion system_260430\data\raw_sensor\rmode.json'
        },
        'csv_path': r'D:\研究生阶段\刘佳宁\海创\子课题2.3\多源数据匹配融合研究\Multi-source_data_real-time_fusion system_260430\data\output_tracks\final_fusion.csv'
    }

    plot_trajectory_fusion(file_config['json_paths'], file_config['csv_path'])