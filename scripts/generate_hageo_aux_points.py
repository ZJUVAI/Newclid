#!/usr/bin/env python3
"""
基于 HAGeo 论文方法，生成候选辅助点。

用法:
    python scripts/generate_hageo_aux_points.py
    python scripts/generate_hageo_aux_points.py --input <输入文件> --output <输出文件>

输入格式（rebuild 格式）：
    Problem Name:
    2000USATSTp2
    Points:
    a:x1,y1
    b:x2,y2
    ...
    Premises:
    predicate1 arg1 arg2 ...
    ...
    Goal:
    predicate arg1 arg2 ...

输出格式：
    Problem Name:
    2000USATSTp2
    aux_int_0
    (1.234,5.678)
    coll aux_int_0 a b, coll aux_int_0 c d
    ...
"""

import argparse
import logging
import math
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

# ==================== 默认配置（硬编码路径） ====================

DEFAULT_INPUT = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/rebuild_problems/hageo_224_remain_rebuild.txt"
DEFAULT_OUTPUT = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/rebuild_problems/hageo_224_remain_rebuild_aux_points.txt"
DEFAULT_TOLERANCE = 1e-6

# ==================== 日志配置 ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ==================== 几何计算函数 ====================

def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """计算两点之间的距离"""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def points_equal(p1: Tuple[float, float], p2: Tuple[float, float], tol: float) -> bool:
    """判断两点是否重合"""
    return distance(p1, p2) < tol


def cross_product(o: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """计算向量OA和OB的叉积"""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def points_collinear(p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float], tol: float) -> bool:
    """判断三点是否共线"""
    # 使用叉积判断
    area = abs(cross_product(p1, p2, p3))
    # 归一化：除以最长边长
    max_dist = max(distance(p1, p2), distance(p2, p3), distance(p1, p3))
    if max_dist < tol:
        return True
    return area / max_dist < tol


def point_on_line(point: Tuple[float, float], line_p1: Tuple[float, float], line_p2: Tuple[float, float], tol: float) -> bool:
    """判断点是否在线上"""
    return points_collinear(point, line_p1, line_p2, tol)


def point_on_circle(point: Tuple[float, float], center: Tuple[float, float], radius: float, tol: float) -> bool:
    """判断点是否在圆上"""
    return abs(distance(point, center) - radius) < tol


def line_intersection(p1: Tuple[float, float], p2: Tuple[float, float], 
                      p3: Tuple[float, float], p4: Tuple[float, float], 
                      tol: float) -> Optional[Tuple[float, float]]:
    """
    计算线p1p2与线p3p4的交点。
    若平行或重合则返回None。
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < tol:
        return None  # 平行或重合
    
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    
    x = x1 + t * (x2 - x1)
    y = y1 + t * (y2 - y1)
    
    return (x, y)


def circle_from_3points(p1: Tuple[float, float], p2: Tuple[float, float], 
                        p3: Tuple[float, float], tol: float) -> Optional[Tuple[Tuple[float, float], float]]:
    """
    从三个不共线的点计算外接圆的圆心和半径。
    若共线则返回None。
    """
    if points_collinear(p1, p2, p3, tol):
        return None
    
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < tol:
        return None
    
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    
    center = (ux, uy)
    radius = distance(center, p1)
    
    return (center, radius)


def line_circle_intersection(p1: Tuple[float, float], p2: Tuple[float, float], 
                             center: Tuple[float, float], radius: float, 
                             tol: float) -> List[Tuple[float, float]]:
    """
    计算线p1p2与圆的交点（0-2个）。
    """
    cx, cy = center
    x1, y1 = p1
    x2, y2 = p2
    
    dx = x2 - x1
    dy = y2 - y1
    
    # 参数化: P = P1 + t * (P2 - P1)
    # |P - C|^2 = r^2
    # 展开得到关于t的二次方程: a*t^2 + b*t + c = 0
    
    a = dx * dx + dy * dy
    if a < tol:
        return []
    
    b = 2 * (dx * (x1 - cx) + dy * (y1 - cy))
    c = (x1 - cx) ** 2 + (y1 - cy) ** 2 - radius ** 2
    
    discriminant = b * b - 4 * a * c
    
    if discriminant < -tol:
        return []
    
    results = []
    if abs(discriminant) < tol:
        # 相切，一个交点
        t = -b / (2 * a)
        results.append((x1 + t * dx, y1 + t * dy))
    else:
        # 两个交点
        sqrt_disc = math.sqrt(discriminant)
        t1 = (-b + sqrt_disc) / (2 * a)
        t2 = (-b - sqrt_disc) / (2 * a)
        results.append((x1 + t1 * dx, y1 + t1 * dy))
        results.append((x1 + t2 * dx, y1 + t2 * dy))
    
    return results


def circle_circle_intersection(c1: Tuple[float, float], r1: float, 
                               c2: Tuple[float, float], r2: float, 
                               tol: float) -> List[Tuple[float, float]]:
    """
    计算两圆的交点（0-2个）。
    """
    d = distance(c1, c2)
    
    if d < tol:
        return []  # 同心圆
    
    if d > r1 + r2 + tol or d < abs(r1 - r2) - tol:
        return []  # 不相交
    
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h_sq = r1 * r1 - a * a
    
    if h_sq < -tol:
        return []
    
    h = math.sqrt(max(0, h_sq))
    
    # 中点
    px = c1[0] + a * (c2[0] - c1[0]) / d
    py = c1[1] + a * (c2[1] - c1[1]) / d
    
    if abs(h) < tol:
        # 相切
        return [(px, py)]
    
    # 两个交点
    dx = h * (c2[1] - c1[1]) / d
    dy = h * (c2[0] - c1[0]) / d
    
    return [(px + dx, py - dy), (px - dx, py + dy)]


def midpoint(p1: Tuple[float, float], p2: Tuple[float, float]) -> Tuple[float, float]:
    """计算中点"""
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


def reflect_point_over_line(point: Tuple[float, float], 
                            line_p1: Tuple[float, float], 
                            line_p2: Tuple[float, float]) -> Tuple[float, float]:
    """计算点关于线的镜像"""
    # 先求垂足
    foot = foot_of_perpendicular(point, line_p1, line_p2)
    # 镜像点 = 2 * 垂足 - 原点
    return (2 * foot[0] - point[0], 2 * foot[1] - point[1])


def foot_of_perpendicular(point: Tuple[float, float], 
                          line_p1: Tuple[float, float], 
                          line_p2: Tuple[float, float]) -> Tuple[float, float]:
    """计算点到线的垂足"""
    px, py = point
    x1, y1 = line_p1
    x2, y2 = line_p2
    
    dx = x2 - x1
    dy = y2 - y1
    
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return line_p1
    
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    
    return (x1 + t * dx, y1 + t * dy)


def is_same_line(l1: Tuple[str, str], l2: Tuple[str, str], 
                 points: Dict[str, Tuple[float, float]], tol: float) -> bool:
    """判断两条线是否相同（方向相同或相反）"""
    p1, p2 = points[l1[0]], points[l1[1]]
    p3, p4 = points[l2[0]], points[l2[1]]
    
    # 检查l2的两个点是否都在l1上
    return point_on_line(p3, p1, p2, tol) and point_on_line(p4, p1, p2, tol)


def is_same_circle(c1: Tuple[Tuple[float, float], float], 
                   c2: Tuple[Tuple[float, float], float], tol: float) -> bool:
    """判断两个圆是否相同"""
    return points_equal(c1[0], c2[0], tol) and abs(c1[1] - c2[1]) < tol


# ==================== 空间哈希索引 ====================

class SpatialHash:
    """
    空间哈希索引，用于快速查找相近坐标。
    将 O(n²) 的近邻查找降低到接近 O(n)。
    """
    def __init__(self, cell_size: float):
        self.cell_size = cell_size
        self.grid: Dict[Tuple[int, int], List[int]] = {}  # cell -> list of indices
        self.points: List[Tuple[float, float]] = []
        self.data: List[dict] = []  # 存储每个点的附加数据
    
    def _get_cell(self, coord: Tuple[float, float]) -> Tuple[int, int]:
        """获取坐标所在的网格单元"""
        return (int(math.floor(coord[0] / self.cell_size)),
                int(math.floor(coord[1] / self.cell_size)))
    
    def _get_neighbor_cells(self, coord: Tuple[float, float]) -> List[Tuple[int, int]]:
        """获取坐标及其相邻的 9 个网格单元"""
        cx, cy = self._get_cell(coord)
        cells = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                cells.append((cx + dx, cy + dy))
        return cells
    
    def find_near(self, coord: Tuple[float, float], tol: float) -> Optional[int]:
        """
        查找与给定坐标距离小于 tol 的已有点的索引。
        返回第一个匹配的索引，若无匹配则返回 None。
        """
        for cell in self._get_neighbor_cells(coord):
            if cell in self.grid:
                for idx in self.grid[cell]:
                    if points_equal(coord, self.points[idx], tol):
                        return idx
        return None
    
    def add(self, coord: Tuple[float, float], data: dict) -> int:
        """
        添加一个点和其附加数据，返回其索引。
        """
        idx = len(self.points)
        self.points.append(coord)
        self.data.append(data)
        
        cell = self._get_cell(coord)
        if cell not in self.grid:
            self.grid[cell] = []
        self.grid[cell].append(idx)
        
        return idx
    
    def get_all(self) -> List[Tuple[Tuple[float, float], dict]]:
        """返回所有点及其数据"""
        return list(zip(self.points, self.data))


# ==================== 题目解析 ====================

def parse_rebuild_file(filepath: str) -> List[dict]:
    """
    解析 rebuild 格式的文件。
    
    返回:
        [{
            'name': str,
            'points': {name: (x, y), ...},
            'premises': [str, ...],
            'goal': str
        }, ...]
    """
    problems = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 按空行分割题目
    blocks = content.strip().split('\n\n')
    
    for block in blocks:
        if not block.strip():
            continue
        
        lines = [line.strip() for line in block.strip().split('\n')]
        
        problem = {
            'name': '',
            'points': {},
            'premises': [],
            'goal': ''
        }
        
        section = None
        for line in lines:
            if line == 'Problem Name:':
                section = 'name'
            elif line == 'Points:':
                section = 'points'
            elif line == 'Premises:':
                section = 'premises'
            elif line == 'Goal:':
                section = 'goal'
            elif section == 'name':
                problem['name'] = line
            elif section == 'points':
                # 格式: name:x,y
                if ':' in line:
                    name, coords = line.split(':', 1)
                    x, y = coords.split(',')
                    problem['points'][name.strip()] = (float(x), float(y))
            elif section == 'premises':
                if line:
                    problem['premises'].append(line)
            elif section == 'goal':
                if line:
                    problem['goal'] = line
        
        if problem['name']:
            problems.append(problem)
    
    logger.info(f"从 {filepath} 解析到 {len(problems)} 道题目")
    return problems


# ==================== 辅助点生成 ====================

def generate_all_lines(points: Dict[str, Tuple[float, float]]) -> List[Tuple[str, str]]:
    """生成所有线（两两组合）"""
    point_names = list(points.keys())
    lines = list(combinations(point_names, 2))
    return lines


def generate_all_circles(points: Dict[str, Tuple[float, float]], tol: float) -> List[Tuple[Tuple[str, str, str], Tuple[Tuple[float, float], float]]]:
    """
    生成所有圆（三三组合，跳过共线点组）。
    
    返回:
        [((p1_name, p2_name, p3_name), (center, radius)), ...]
    """
    point_names = list(points.keys())
    circles = []
    seen_circles = []  # 用于去重
    
    for combo in combinations(point_names, 3):
        p1, p2, p3 = points[combo[0]], points[combo[1]], points[combo[2]]
        result = circle_from_3points(p1, p2, p3, tol)
        if result is not None:
            center, radius = result
            # 检查是否已有相同的圆
            is_dup = False
            for seen_center, seen_radius in seen_circles:
                if is_same_circle((center, radius), (seen_center, seen_radius), tol):
                    is_dup = True
                    break
            if not is_dup:
                circles.append((combo, (center, radius)))
                seen_circles.append((center, radius))
    
    return circles


def find_coinciding_point(aux_point: Tuple[float, float], 
                          points: Dict[str, Tuple[float, float]], 
                          tol: float) -> Optional[str]:
    """检查辅助点是否与已有点重合，返回重合点的名称"""
    for name, coord in points.items():
        if points_equal(aux_point, coord, tol):
            return name
    return None


def deduplicate_aux_points(aux_points: List[dict], tol: float) -> List[dict]:
    """对辅助点去重，使用空间哈希加速"""
    spatial_hash = SpatialHash(cell_size=tol * 2)
    result = []
    
    for ap in aux_points:
        coord = ap['coord']
        # 查找是否已有相近的点
        if spatial_hash.find_near(coord, tol) is None:
            # 没有重复，添加到结果和索引中
            spatial_hash.add(coord, ap)
            result.append(ap)
    
    return result


def generate_intersection_points(points: Dict[str, Tuple[float, float]], 
                                  lines: List[Tuple[str, str]], 
                                  circles: List[Tuple[Tuple[str, str, str], Tuple[Tuple[float, float], float]]], 
                                  tol: float) -> List[dict]:
    """
    生成交点类辅助点。
    只考虑线-线和线-圆的交点，如果同一个坐标由多个来源产生，则记录。
    （不计算圆-圆交点，因为复杂度太高）
    
    使用空间哈希索引加速坐标聚合，将 O(n²) 降低到 O(n)。
    """
    aux_points = []
    
    # 使用空间哈希索引，cell_size 设为 tol 的 2 倍以确保相邻点能被找到
    spatial_hash = SpatialHash(cell_size=tol * 2)
    
    ll_count = 0
    # 线-线交点
    for i, l1 in enumerate(lines):
        for j, l2 in enumerate(lines):
            if j <= i:
                continue
            # 跳过有公共点的线
            if l1[0] in l2 or l1[1] in l2:
                continue
            
            p1, p2 = points[l1[0]], points[l1[1]]
            p3, p4 = points[l2[0]], points[l2[1]]
            
            inter = line_intersection(p1, p2, p3, p4, tol)
            if inter is not None:
                ll_count += 1
                # 查找是否已有相近的坐标
                existing_idx = spatial_hash.find_near(inter, tol)
                if existing_idx is not None:
                    # 添加来源到已有点
                    data = spatial_hash.data[existing_idx]
                    source1 = ('line', l1)
                    source2 = ('line', l2)
                    if source1 not in data['sources']:
                        data['sources'].append(source1)
                    if source2 not in data['sources']:
                        data['sources'].append(source2)
                else:
                    # 新坐标
                    spatial_hash.add(inter, {
                        'coord': inter,
                        'sources': [('line', l1), ('line', l2)]
                    })
    
    # 线-圆交点
    lc_count = 0
    for line in lines:
        p1, p2 = points[line[0]], points[line[1]]
        for circle_info in circles:
            circle_points, (center, radius) = circle_info
            inters = line_circle_intersection(p1, p2, center, radius, tol)
            for inter in inters:
                lc_count += 1
                # 查找是否已有相近的坐标
                existing_idx = spatial_hash.find_near(inter, tol)
                if existing_idx is not None:
                    # 添加来源到已有点
                    data = spatial_hash.data[existing_idx]
                    source_line = ('line', line)
                    source_circle = ('circle', circle_info)
                    if source_line not in data['sources']:
                        data['sources'].append(source_line)
                    if source_circle not in data['sources']:
                        data['sources'].append(source_circle)
                else:
                    # 新坐标
                    spatial_hash.add(inter, {
                        'coord': inter,
                        'sources': [('line', line), ('circle', circle_info)]
                    })
    
    # 筛选：来源数 >= 3（即至少有3个不同的线/圆经过该点）
    for coord, data in spatial_hash.get_all():
        sources = data['sources']
        if len(sources) >= 3:
            # 分离线和圆
            passing_lines = [obj for t, obj in sources if t == 'line']
            passing_circles = [obj for t, obj in sources if t == 'circle']
            
            # 生成 predicate：优先用线
            objects_used = []
            for line in passing_lines[:2]:
                objects_used.append(('line', line))
            if len(objects_used) < 2:
                for circle_info in passing_circles[:2 - len(objects_used)]:
                    objects_used.append(('circle', circle_info))
            
            aux_points.append({
                'coord': data['coord'],
                'type': 'int',
                'objects': objects_used,
                'all_lines': passing_lines,
                'all_circles': passing_circles
            })
    
    return aux_points


def generate_midpoint_points(points: Dict[str, Tuple[float, float]], 
                              lines: List[Tuple[str, str]], 
                              circles: List[Tuple[Tuple[str, str, str], Tuple[Tuple[float, float], float]]], 
                              tol: float) -> List[dict]:
    """
    生成中点类辅助点。
    线段AB的中点C，且C落在另一条线或圆上（该线不为AB）。
    """
    aux_points = []
    point_names = list(points.keys())
    
    for combo in combinations(point_names, 2):
        a_name, b_name = combo
        a_coord, b_coord = points[a_name], points[b_name]
        mid = midpoint(a_coord, b_coord)
        
        # 检查中点是否在某条其他线上
        for line in lines:
            # 跳过AB线本身
            if set(line) == set(combo):
                continue
            # 跳过包含A或B的线（中点自然在这些线上如果共线的话）
            if a_name in line or b_name in line:
                # 需要检查是否真的共线
                l1, l2 = points[line[0]], points[line[1]]
                if point_on_line(a_coord, l1, l2, tol) or point_on_line(b_coord, l1, l2, tol):
                    continue
            
            l1, l2 = points[line[0]], points[line[1]]
            if point_on_line(mid, l1, l2, tol):
                aux_points.append({
                    'coord': mid,
                    'type': 'mid',
                    'segment': (a_name, b_name),
                    'on_object': ('line', line)
                })
        
        # 检查中点是否在某个圆上
        for circle_info in circles:
            circle_points, (center, radius) = circle_info
            if point_on_circle(mid, center, radius, tol):
                aux_points.append({
                    'coord': mid,
                    'type': 'mid',
                    'segment': (a_name, b_name),
                    'on_object': ('circle', circle_info)
                })
    
    return aux_points


def generate_reflection_points(points: Dict[str, Tuple[float, float]], 
                                lines: List[Tuple[str, str]], 
                                tol: float) -> List[dict]:
    """
    生成镜像类辅助点。
    A关于线CD的镜像B（要求A不在线CD上），且B落在另一条线EF上（EF ≠ CD）。
    """
    aux_points = []
    point_names = list(points.keys())
    
    for a_name in point_names:
        a_coord = points[a_name]
        for line_cd in lines:
            c_name, d_name = line_cd
            c_coord, d_coord = points[c_name], points[d_name]
            
            # A不能在线CD上
            if point_on_line(a_coord, c_coord, d_coord, tol):
                continue
            
            # 计算镜像点
            ref = reflect_point_over_line(a_coord, c_coord, d_coord)
            
            # 检查镜像点是否落在另一条线EF上
            for line_ef in lines:
                # EF不能与CD相同
                if is_same_line(line_cd, line_ef, points, tol):
                    continue
                
                e_name, f_name = line_ef
                e_coord, f_coord = points[e_name], points[f_name]
                
                if point_on_line(ref, e_coord, f_coord, tol):
                    aux_points.append({
                        'coord': ref,
                        'type': 'ref',
                        'point': a_name,
                        'line': line_cd,
                        'on_line': line_ef
                    })
    
    return aux_points


def generate_foot_points(points: Dict[str, Tuple[float, float]], 
                          lines: List[Tuple[str, str]], 
                          tol: float) -> List[dict]:
    """
    生成垂足类辅助点。
    A到线CD的垂足B，且B落在另一条线EF上（EF ≠ CD，A不在EF上）。
    """
    aux_points = []
    point_names = list(points.keys())
    
    for a_name in point_names:
        a_coord = points[a_name]
        for line_cd in lines:
            c_name, d_name = line_cd
            c_coord, d_coord = points[c_name], points[d_name]
            
            # A不能在线CD上
            if point_on_line(a_coord, c_coord, d_coord, tol):
                continue
            
            # 计算垂足
            foot = foot_of_perpendicular(a_coord, c_coord, d_coord)
            
            # 检查垂足是否在另一条线上
            for line_ef in lines:
                # EF不能与CD相同
                if is_same_line(line_cd, line_ef, points, tol):
                    continue
                
                e_name, f_name = line_ef
                e_coord, f_coord = points[e_name], points[f_name]
                
                # A不能在线EF上
                if point_on_line(a_coord, e_coord, f_coord, tol):
                    continue
                
                if point_on_line(foot, e_coord, f_coord, tol):
                    aux_points.append({
                        'coord': foot,
                        'type': 'foot',
                        'point': a_name,
                        'line_cd': line_cd,
                        'line_ef': line_ef
                    })
    
    return aux_points


def format_predicate(aux_point: dict, aux_name: str) -> str:
    """生成辅助点的 predicate 字符串"""
    ap_type = aux_point['type']
    
    if ap_type == 'int':
        # 交点: coll + coll / coll + cyclic / cyclic + cyclic
        parts = []
        for obj_type, obj in aux_point['objects']:
            if obj_type == 'line':
                parts.append(f"coll {aux_name} {obj[0]} {obj[1]}")
            else:  # circle
                circle_points = obj[0]
                parts.append(f"cyclic {aux_name} {circle_points[0]} {circle_points[1]} {circle_points[2]}")
        return ", ".join(parts)
    
    elif ap_type == 'mid':
        # 中点: coll c a b, cong a c b c, coll c e f / cyclic c p q r
        a_name, b_name = aux_point['segment']
        obj_type, obj = aux_point['on_object']
        
        base = f"coll {aux_name} {a_name} {b_name}, cong {a_name} {aux_name} {b_name} {aux_name}"
        
        if obj_type == 'line':
            return f"{base}, coll {aux_name} {obj[0]} {obj[1]}"
        else:  # circle
            circle_points = obj[0]
            return f"{base}, cyclic {aux_name} {circle_points[0]} {circle_points[1]} {circle_points[2]}"
    
    elif ap_type == 'ref':
        # 镜像: perp a b c d, cong a c b c, coll b e f
        a_name = aux_point['point']
        c_name, d_name = aux_point['line']
        e_name, f_name = aux_point['on_line']
        return f"perp {a_name} {aux_name} {c_name} {d_name}, cong {a_name} {c_name} {aux_name} {c_name}, coll {aux_name} {e_name} {f_name}"
    
    elif ap_type == 'foot':
        # 垂足: perp a b c d, coll b c d, coll b e f
        a_name = aux_point['point']
        c_name, d_name = aux_point['line_cd']
        e_name, f_name = aux_point['line_ef']
        return f"perp {a_name} {aux_name} {c_name} {d_name}, coll {aux_name} {c_name} {d_name}, coll {aux_name} {e_name} {f_name}"
    
    return ""


def generate_aux_points_for_problem(problem: dict, tol: float) -> List[dict]:
    """为单个题目生成所有辅助点"""
    points = problem['points']
    
    # 生成所有线和圆
    lines = generate_all_lines(points)
    circles = generate_all_circles(points, tol)
    all_aux_points = []
    # 1. 交点
    int_points = generate_intersection_points(points, lines, circles, tol)
    all_aux_points.extend(int_points)
    
    # 2. 中点
    mid_points = generate_midpoint_points(points, lines, circles, tol)
    all_aux_points.extend(mid_points)
    
    # 3. 镜像
    ref_points = generate_reflection_points(points, lines, tol)
    all_aux_points.extend(ref_points)
    
    # 4. 垂足
    foot_points = generate_foot_points(points, lines, tol)
    all_aux_points.extend(foot_points)
    
    # 去重
    all_aux_points = deduplicate_aux_points(all_aux_points, tol)
    
    return all_aux_points


# ==================== 输出 ====================

def write_output(problems: List[dict], all_aux_results: List[List[dict]], 
                 output_path: str, tol: float) -> None:
    """写出结果文件"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    total_aux = 0
    total_coincide = 0
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for problem, aux_points in zip(problems, all_aux_results):
            f.write("Problem Name:\n")
            f.write(f"{problem['name']}\n")
            
            # 按类型分组命名
            type_counters = {'int': 0, 'mid': 0, 'ref': 0, 'foot': 0}
            
            for ap in aux_points:
                ap_type = ap['type']
                idx = type_counters[ap_type]
                type_counters[ap_type] += 1
                
                aux_name = f"aux_{ap_type}_{idx}"
                
                # 检查是否与已有点重合
                coincide_point = find_coinciding_point(ap['coord'], problem['points'], tol)
                
                x, y = ap['coord']
                predicate = format_predicate(ap, aux_name)
                
                if coincide_point:
                    f.write(f"#{aux_name} (coincides with {coincide_point})\n")
                    f.write(f"#({x},{y})\n")
                    f.write(f"#{predicate}\n")
                    total_coincide += 1
                else:
                    f.write(f"{aux_name}\n")
                    f.write(f"({x},{y})\n")
                    f.write(f"{predicate}\n")
                
                total_aux += 1
            
            f.write("\n")
    
    logger.info(f"已写入 {len(problems)} 道题目的辅助点到 {output_path}")
    logger.info(f"总共生成 {total_aux} 个辅助点，其中 {total_coincide} 个与已有点重合")


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(
        description="基于 HAGeo 论文方法，生成候选辅助点"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=DEFAULT_INPUT,
        help=f"输入文件路径 (默认: {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=DEFAULT_OUTPUT,
        help=f"输出文件路径 (默认: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--tolerance", "-t",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=f"数值容差 (默认: {DEFAULT_TOLERANCE})"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("开始生成辅助点")
    logger.info(f"输入文件: {args.input}")
    logger.info(f"输出文件: {args.output}")
    logger.info(f"容差: {args.tolerance}")
    logger.info("=" * 60)
    
    # 解析输入文件
    problems = parse_rebuild_file(args.input)
    
    # 为每道题目生成辅助点
    all_aux_results = []
    for idx, problem in enumerate(problems):
        logger.info(f"[{idx + 1}/{len(problems)}] 处理: {problem['name']} (共 {len(problem['points'])} 个点)")
        aux_points = generate_aux_points_for_problem(problem, args.tolerance)
        all_aux_results.append(aux_points)
        logger.info(f"  生成 {len(aux_points)} 个辅助点")
    
    # 写出结果
    write_output(problems, all_aux_results, args.output, args.tolerance)
    
    logger.info("=" * 60)
    logger.info("辅助点生成完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
