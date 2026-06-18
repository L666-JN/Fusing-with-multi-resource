import numpy as np
import math
from typing import Dict, Any, List


class SimpleWeightedManager:
    def __init__(self):
        self.tracks: Dict[int, Dict[str, Any]] = {}

        # 1. 权重解耦配置
        self.pos_weights = {"ais": 0.8, "bds": 0.4, "rmode": 0.3, "radar": 0.2}
        self.vel_weights = {"ais": 0.8, "bds": 0, "rmode": 0, "radar": 0.1}

    def update(self, mmsi: int, x: float, y: float, ts: float, source: str,
               raw_heading: float = None, raw_course: float = None, raw_speed: float = None,
               radar_track_id: Any = None):

        source = source.lower().strip()

        # ==========================================
        # 1. 航迹初始化与基础校验
        # ==========================================
        if mmsi not in self.tracks:
            init_heading = raw_heading if (raw_heading is not None and 0.0 <= raw_heading < 360.0) else None
            init_course = raw_course if (raw_course is not None and raw_course != 3600.0) else None
            init_speed = raw_speed if raw_speed is not None else 0.0

            self.tracks[mmsi] = {
                'mmsi': mmsi,
                'x': x, 'y': y,
                'last_ts': ts,
                'sources': {source},
                'speed': init_speed,
                'heading': init_heading,
                'course': init_course,
                'radar_track_id': radar_track_id if source == 'radar' else None
            }
            return self.tracks[mmsi]

        track = self.tracks[mmsi]
        alpha_pos = self.pos_weights.get(source, 0.3)
        alpha_vel = self.vel_weights.get(source, 0.2)
        dt = (ts - track['last_ts']) / 1000.0

        if dt <= 0:
            track['sources'].add(source)
            return track

        # ==========================================
        # 2. 状态外推预测 (Prediction)
        # ==========================================
        speed_ms = track['speed'] * 0.5144
        course_deg = track['course'] if track['course'] is not None else track.get('heading')

        if course_deg is not None:
            course_rad = math.radians(course_deg)
            vx = speed_ms * math.sin(course_rad)
            vy = speed_ms * math.cos(course_rad)
        else:
            vx, vy = 0.0, 0.0

        pred_x = track['x'] + vx * dt
        pred_y = track['y'] + vy * dt

        # ==========================================
        # 3. 位置通道加权平滑 (Update)
        # ==========================================
        new_x = (1 - alpha_pos) * pred_x + alpha_pos * x
        new_y = (1 - alpha_pos) * pred_y + alpha_pos * y

        dx = new_x - track['x']
        dy = new_y - track['y']

        # ==========================================
        # 4. 速度通道解算 (原生速度直采，阻断位置反推)
        # ==========================================
        if raw_speed is not None:
            # AIS、更新优化后的雷达等信源，存在原生速度直接采信
            current_raw_speed = raw_speed
        else:
            # 北斗、Rmode等信源无速度键值，直接沿用历史航速，彻底阻断利用平滑位置位移反推速度的数学陷阱
            current_raw_speed = track['speed']

        # 60节上限波门截断与一阶滤波
        if current_raw_speed < 60.0:
            if track['speed'] == 0.0:
                track['speed'] = current_raw_speed
            else:
                track['speed'] = (1 - alpha_vel) * track['speed'] + alpha_vel * current_raw_speed

        # ==========================================
        # 5. 航向 (Course) 动态解算与相角平滑
        # ==========================================
        new_course = None
        if source == 'ais' and raw_course is not None and raw_course != 3600.0:
            new_course = raw_course
        else:
            if track['speed'] > 1.0:
                new_course = (math.degrees(math.atan2(dx, dy)) + 360) % 360
            elif raw_course is not None and raw_course != 3600.0:
                new_course = raw_course

        if new_course is not None:
            if track['course'] is None:
                track['course'] = new_course
            else:
                angle_diff = (new_course - track['course'] + 180) % 360 - 180
                track['course'] = (track['course'] + alpha_vel * angle_diff) % 360

        # ==========================================
        # 6. 艏向 (Heading) 511异常值清洗
        # ==========================================
        if raw_heading is not None and 0.0 <= raw_heading < 360.0:
            track['heading'] = raw_heading

        # ==========================================
        # 7. 状态更新持久化
        # ==========================================
        track['x'] = new_x
        track['y'] = new_y
        track['last_ts'] = ts
        track['sources'].add(source)

        # 若当前更新来自雷达，更新绑定的雷达轨迹号；若来自其他无此编号信源，保留原值
        if source == 'radar':
            track['radar_track_id'] = radar_track_id

        return track

    def get_active_backbones(self) -> List[Dict[str, Any]]:
        return [{
            "mmsi": m,
            "x": t['x'],
            "y": t['y'],
            "last_ts": t.get('last_ts'),
            "speed": t.get('speed', 0.0),
            "heading": t.get('heading'),
            "course": t.get('course'),
            "radar_track_id": t.get('radar_track_id')
        } for m, t in self.tracks.items()]