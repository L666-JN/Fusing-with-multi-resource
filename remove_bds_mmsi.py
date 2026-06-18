import json
import os


def remove_mmsi_from_bds(input_path: str, output_path: str):
    """
    读取北斗JSON数据，剔除mmsi字段并另存为新文件。
    """
    if not os.path.exists(input_path):
        print(f"错误: 找不到输入文件 {input_path}")
        return

    # 读取原始数据
    with open(input_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            # 兼容单条字典或列表格式
            if isinstance(data, dict):
                data = [data]
        except json.JSONDecodeError:
            print(f"错误: {input_path} 非标准 JSON 格式")
            return

    # 遍历并剔除 mmsi
    for item in data:
        if 'mmsi' in item:
            del item['mmsi']

    # 写入新文件
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"处理完成。无 MMSI 标识的北斗数据已保存至: {output_path}")


# 使用示例
if __name__ == "__main__":
    input_file = "data/raw_sensor/bds.json"
    output_file = "data/raw_sensor/bds_no_mmsi.json"
    remove_mmsi_from_bds(input_file, output_file)