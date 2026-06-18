import numpy as np


class GeoTransformer:
    """
    空间坐标转换工具类。
    负责传感器整数坐标的反向缩放，以及 WGS-84 球面坐标到局部笛卡尔平面坐标系的投影。
    """

    def __init__(self, ref_lat: float, ref_lon: float):
        """
        初始化局部平面坐标系原点
        :param ref_lat: 原点纬度 (浮点数，如 38.475350)
        :param ref_lon: 原点经度 (浮点数，如 121.086560)
        """
        self.ref_lat_rad = np.radians(ref_lat)
        self.ref_lon_rad = np.radians(ref_lon)
        self.R = 6378137.0  # WGS-84 地球基准赤道半径 (米)

    def revert_scaled_coord(self, scaled_val: int, scale_factor: int = 1000000) -> float:
        """
        反向缩放整数型坐标
        :param scaled_val: 原始数据中的整数坐标 (如 38475350)
        :param scale_factor: 缩放因子，默认 10^6
        :return: 真实的经纬度浮点数
        """
        return scaled_val / scale_factor

    def wgs84_to_enu_2d(self, lat: float, lon: float) -> tuple:
        """
        将 WGS-84 经纬度投影为局部 ENU (East-North-Up) 二维平面坐标。
        采用简化的球面等距投影模型，适用于局部区域（几百公里范围）的高效计算。

        :param lat: 真实纬度 (浮点数)
        :param lon: 真实经度 (浮点数)
        :return: (x, y) 坐标元组，单位：米。x 轴指向正东，y 轴指向正北。
        """
        lat_rad = np.radians(lat)
        lon_rad = np.radians(lon)

        # 计算 x (East) 向和 y (North) 向的投影距离
        x = self.R * (lon_rad - self.ref_lon_rad) * np.cos(self.ref_lat_rad)
        y = self.R * (lat_rad - self.ref_lat_rad)

        return float(x), float(y)

    # 在 GeoTransformer 类中追加以下方法：
    def enu_2d_to_wgs84(self, x: float, y: float) -> tuple:
        """
        将局部 ENU 二维坐标 (米) 反向还原为 WGS-84 经纬度 (浮点数)
        """
        lat_rad = self.ref_lat_rad + (y / self.R)
        lon_rad = self.ref_lon_rad + (x / (self.R * np.cos(self.ref_lat_rad)))
        return np.degrees(lat_rad), np.degrees(lon_rad)