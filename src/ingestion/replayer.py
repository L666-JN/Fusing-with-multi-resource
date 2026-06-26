import json
import time
from typing import List, Dict, Any


class LocalDataReplayer:
    """
    本地数据流回放引擎。
    负责多传感器数据的聚合、绝对时序排序、严格去重以及模拟真实物理时延的数据分发。
    """

    def __init__(self, speed_factor: float = 1.0):
        self.speed_factor = speed_factor
        self.merged_stream: List[Dict[str, Any]] = []

    def load_files(self, file_paths: Dict[str, str]) -> None:
        """
        加载各传感器独立的数据文件并进行系统级标记。
        :param file_paths: 字典格式，如 {"AIS": "data/raw/ais.json"}
        """
        for source_type, path in file_paths.items():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data = [data]

                    # 注入系统级保留字段，标记数据血缘
                    for item in data:
                        item['_sys_source_type'] = source_type

                    self.merged_stream.extend(data)
            except FileNotFoundError:
                print(f"[错误] 找不到数据文件: {path}")
            except json.JSONDecodeError:
                print(f"[错误] 文件解析失败，非标准 JSON 格式: {path}")

    def _preprocess_and_sort(self) -> None:
        """
        执行全局数据流预处理：按接收时间戳排序及严格去重。
        """
        # 1. 全局按接收时间戳 (recvTs) 进行绝对升序排序
        self.merged_stream.sort(key=lambda x: x.get('recvTs', 0))

        # 2. 时序去重逻辑：相同 recvTs 且相同 MMSI 的数据仅保留一条
        seen_identifiers = set()
        cleaned_stream = []

        for item in self.merged_stream:
            # 针对具备 MMSI 的数据源执行联合主键去重
            if 'mmsi' in item and 'recvTs' in item:

                # 【修改点】：移除 source_type，仅依赖 MMSI 和 时间戳 进行严格去重
                identifier = (item['mmsi'], item['recvTs'])

                if identifier in seen_identifiers:
                    continue
                seen_identifiers.add(identifier)

            cleaned_stream.append(item)

        self.merged_stream = cleaned_stream

    def replay_generator(self):
        """
        生成器：基于 recvTs 计算时间差，模拟真实数据流的离散到达。
        """
        self._preprocess_and_sort()

        if not self.merged_stream:
            return

        last_ts = self.merged_stream[0].get('recvTs', 0)

        for item in self.merged_stream:
            current_ts = item.get('recvTs', 0)
            delta_ms = current_ts - last_ts

            # 若存在时间差，则触发物理休眠机制以模拟网络流
            if delta_ms > 0:
                sleep_time = (delta_ms / 1000.0) / self.speed_factor
                time.sleep(sleep_time)

            last_ts = current_ts
            yield item