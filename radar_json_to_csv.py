import pandas as pd
import json
import os


def robust_radar_to_csv(input_path: str, output_path: str):
    if not os.path.exists(input_path):
        print(f"错误：找不到文件 {input_path}")
        return

    print("正在加载数据，请稍候...")

    # 1. 自动适配 JSON 或 JSON Lines 格式加载
    try:
        df = pd.read_json(input_path)
        print("-> 成功以标准 JSON 格式解析。")
    except ValueError:
        try:
            df = pd.read_json(input_path, lines=True)
            print("-> 成功以 JSON Lines 格式解析。")
        except Exception as e:
            print(f"解析失败: {e}")
            return

    # 2. 客观输出原始数据的时间跨度统计
    if 'recvTs' in df.columns:
        min_ts = df['recvTs'].min()
        max_ts = df['recvTs'].max()
        duration_mins = (max_ts - min_ts) / 1000.0 / 60.0
        print(f"\n【原始数据客观统计】")
        print(f"数据总条数: {len(df)} 条")
        print(f"起始时间戳: {min_ts}")
        print(f"结束时间戳: {max_ts}")
        print(f"真实物理时间跨度: {duration_mins:.2f} 分钟\n")
    else:
        print("警告：数据中未检测到 recvTs 时间戳字段。")

    # 3. 处理嵌套字典 (回波轮廓) 转化为字符串以供 CSV 存储
    if 'profile' in df.columns:
        # 仅当元素为字典或列表时才进行 JSON 序列化，防止重复处理
        df['profile'] = df['profile'].apply(
            lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else x
        )

    # 4. 落盘导出
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False, encoding='utf-8')
    print(f"转换完成！全量数据已落盘至: {output_path}")


if __name__ == "__main__":
    INPUT_JSON = "data/raw_sensor/radar.json"
    OUTPUT_CSV = "data/raw_sensor/radar.csv"

    robust_radar_to_csv(INPUT_JSON, OUTPUT_CSV)