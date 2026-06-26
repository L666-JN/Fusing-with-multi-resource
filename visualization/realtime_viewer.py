import pandas as pd
import matplotlib.pyplot as plt
import time
import os


def run_realtime_monitor():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    csv_path = os.path.join(project_root, "data", "output_tracks", "final_fusion.csv")

    # 【解决中文警告问题】设置中文字体并修复负号显示
    plt.rcParams['font.sans-serif'] = ['SimHei']  # Windows 用户默认使用黑体
    # plt.rcParams['font.sans-serif'] = ['Arial Unicode MS'] # macOS 用户请解除这行注释
    plt.rcParams['axes.unicode_minus'] = False

    # 开启 Matplotlib 交互模式
    plt.ion()
    fig, ax = plt.subplots(figsize=(12, 8))

    print("📡 启动实时航迹监控大屏 (全量历史轨迹模式)...")
    print("请确保主程序 main.py 正在运行并不断生成数据。按 Ctrl+C 退出监控。")

    # 定义标准的 CSV 列名，确保代码能准确提取最后面的 source 字段
    columns = ['timestamp', 'mmsi', 'latitude', 'longitude', 'speed',
               'heading', 'course', 'source', 'radar_track_number', 'radar_speed']

    while True:
        if not os.path.exists(csv_path):
            print("等待 CSV 文件生成...")
            time.sleep(2)
            continue

        try:
            # 动态读取 CSV 数据，加上 names 参数映射字段名
            df = pd.read_csv(csv_path, names=columns).tail(50000)

            # 【核心修复 1】：精准拦截并剔除表头那一行“幽灵船”数据
            df = df[df['latitude'] != 'latitude']

            # 【核心修复 2】：强制将坐标和航速转为数字类型，防止字符串导致画图卡死
            df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
            df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
            df['speed'] = pd.to_numeric(df['speed'], errors='coerce')

            # 清理掉可能产生的空值（脏数据）
            df = df.dropna(subset=['latitude', 'longitude'])

        except Exception:
            time.sleep(0.5)
            continue

        if df.empty:
            time.sleep(1)
            continue

        ax.clear()

        ax.set_title("实时多源融合航迹监控 (全量历史轨迹)", fontsize=14, pad=15)
        ax.set_xlabel("Longitude (经度)", fontsize=12)
        ax.set_ylabel("Latitude (纬度)", fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.6)

        grouped = df.groupby('mmsi')
        for mmsi, group_data in grouped:
            group_data = group_data.sort_values(by='timestamp')

            # 1. 绘制完整的历史航迹线 (半透明细线)
            line, = ax.plot(group_data['longitude'], group_data['latitude'],
                            linestyle='-', linewidth=1.5, alpha=0.6, label=f'MMSI: {mmsi}')

            # 获取当前这根线的颜色，确保船头和轨迹颜色一致
            current_color = line.get_color()

            if not group_data.empty:
                # 获取最新的一点（船头）
                last_point = group_data.iloc[-1]

                # --- 提取动态标签 ---
                sources_label = last_point['source']

                # 2. 在船头画一个实心大圆点，代表当前位置
                ax.plot(last_point['longitude'], last_point['latitude'],
                        marker='o', markersize=6, color=current_color)

                # 3. 仅在船头位置打上文字标签（加入数据血缘动态显示）
                display_text = f" {mmsi}\n[{sources_label}]"

                # 加了底色框和偏移量，防止字体和航迹重叠看不清
                ax.text(last_point['longitude'] + 0.0005, last_point['latitude'] + 0.0005,
                        display_text,
                        fontsize=8, color='yellow', fontweight='bold',
                        bbox=dict(facecolor='black', alpha=0.5, edgecolor='none', pad=1.0))

        # 【核心修正】：图例必须放在 for 循环外部，否则极其消耗 CPU 导致卡顿
        if len(grouped) <= 30:  # 保护机制：如果屏幕上超过30艘船，则隐藏图例防止遮挡画面
            ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')

        plt.tight_layout()
        plt.pause(1.0)


if __name__ == "__main__":
    try:
        run_realtime_monitor()
    except KeyboardInterrupt:
        print("\n监控已手动停止。")