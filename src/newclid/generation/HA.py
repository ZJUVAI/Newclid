from newclid.generation.clause_generation import PointGenerator
from collections import defaultdict, OrderedDict
import re
from itertools import combinations
import numpy as np
from collections import defaultdict
import random


TOLERANCE = 1e-8
ROUND_DECIMALS = 9


def round_coord(coord):
    return (round(coord[0], ROUND_DECIMALS), round(coord[1], ROUND_DECIMALS))


def is_point_too_close(
    new_coords: list[tuple[float, float]],
    existing_coords: list[tuple[float, float]],
    tol: float = 0.05,
    round_eps: float = 1e-10
) -> bool:
    if len(existing_coords) < 2:
        return False

    # 计算所有点对的平均距离（近似平均点间距）
    total_dist = 0.0
    count = 0
    n = len(existing_coords)
    for i in range(n):
        for j in range(i + 1, n):
            x1, y1 = existing_coords[i]
            x2, y2 = existing_coords[j]
            dist = ((x1 - x2)**2 + (y1 - y2)**2) ** 0.5
            total_dist += dist
            count += 1
    avg_dist = total_dist / count

    # 检查每个新点
    for nx, ny in new_coords:
        for px, py in existing_coords:
            dx = nx - px
            dy = ny - py
            dist = (dx*dx + dy*dy) ** 0.5
            if round_eps < dist < tol * avg_dist:
                return True
    return False


def is_point_too_far(
    new_coords: list[tuple[float, float]],
    existing_coords: list[tuple[float, float]],
    factor: float = 5.0
) -> bool:
    if len(existing_coords) < 2:
        return False

    # 计算质心（平均位置）
    n = len(existing_coords)
    sum_x = sum(y for x, y in existing_coords)
    sum_y = sum(y for x, y in existing_coords)
    avg_x = sum_x / n
    avg_y = sum_y / n

    # 计算到质心的最大距离（作为点群尺度）
    maxdist = 0.0
    for px, py in existing_coords:
        dx = px - avg_x
        dy = py - avg_y
        dist = (dx*dx + dy*dy) ** 0.5
        if dist > maxdist:
            maxdist = dist

    for nx, ny in new_coords:
        for px, py in existing_coords:
            dx = nx - px
            dy = ny - py
            dist = (dx*dx + dy*dy) ** 0.5
            if dist > factor * maxdist:
                return True
    return False


def check_on_line(coord, lines, coords, current_line=[]):
    current_sets = [set(cand) for cand in current_line]
    for line_points in lines:
        known_set = set(line_points)
        if any(curr_set.issubset(known_set) for curr_set in current_sets):
            continue
        x1, y1 = coords[line_points[0]]
        x2, y2 = coords[line_points[1]]
        dx = x2 - x1
        dy = y2 - y1
        line_len = (dx**2 + dy**2)**0.5
        vec_x = coord[0] - x1
        vec_y = coord[1] - y1
        cross = vec_x * dy - vec_y * dx
        dist = abs(cross) / line_len
        if dist <= TOLERANCE:
            return True
    return False


def check_on_circle(coord, circles, coords):
    for cir in circles:
        cx, cy = cir["center"]
        r = cir["radius"]
        dist = np.hypot(coord[0] - cx, coord[1] - cy)
        if abs(dist - r) < TOLERANCE:
            return True
    return False


def normalize_direction(dx, dy):
    norm = np.sqrt(dx**2 + dy**2)
    return (0.0, 0.0) if norm < TOLERANCE else (dx / norm, dy / norm)


def extract_points(text: str):
    pattern = r'([a-zA-Z][a-zA0-9]*)@([-+]?\d*\.?\d+)_([-+]?\d*\.?\d+)'
    matches = re.findall(pattern, text)
    original_points = OrderedDict()
    for name, x_str, y_str in matches:
        original_points[name] = (float(x_str), float(y_str))
    point_names = list(original_points.keys())
    return point_names, original_points


def lines(point_names, coords) -> list[tuple[str]]:
    line_to_points = defaultdict(set)

    # 找到所有基础线
    for a, b in combinations(point_names, 2):
        if a >= b:
            continue
        p1, p2 = coords[a], coords[b]
        dir_norm = normalize_direction(p2[0] - p1[0], p2[1] - p1[1])
        if dir_norm == (0.0, 0.0):
            continue
        key = (p1[0], p1[1], dir_norm[0], dir_norm[1])
        line_to_points[key].update([a, b])

    # 线合并
    final_lines = []
    for key, pts_set in line_to_points.items():
        current_pts = sorted(list(pts_set))
        while True:
            added = False
            max_dist = -1
            base_a, base_b = current_pts[0], current_pts[1]
            for i in range(len(current_pts)):
                for j in range(i + 1, len(current_pts)):
                    pa = np.array(coords[current_pts[i]])
                    pb = np.array(coords[current_pts[j]])
                    dist_sq = np.sum((pa - pb)**2)
                    if dist_sq > max_dist:
                        max_dist = dist_sq
                        base_a, base_b = current_pts[i], current_pts[j]

            direction = np.subtract(coords[base_b], coords[base_a])
            dir_norm = np.linalg.norm(direction)

            for name in point_names:
                if name in pts_set:
                    continue
                pt = np.array(coords[name])
                vec = pt - np.array(coords[base_a])
                # 点到直线的距离（向量叉积 / 方向向量长度）
                dist = abs(np.cross(direction, vec)) / dir_norm

                if dist < TOLERANCE:
                    pts_set.add(name)
                    current_pts.append(name)
                    added = True
            if not added:
                break
        if len(pts_set) >= 2:  # 至少两条点才算有效线
            final_lines.append(sorted(list(pts_set)))

    result = sorted(
        {tuple(sorted(line)) for line in final_lines},
        key=lambda x: (-len(x), x)
    )

    return result


def circles(point_names, coords):
    def get_circle_from_three(p1, p2, p3):
        A = coords[p1]
        B = coords[p2]
        C = coords[p3]

        ba = (B[0] - A[0], B[1] - A[1])
        ca = (C[0] - A[0], C[1] - A[1])

        # 共线检查
        cross = ba[0] * ca[1] - ba[1] * ca[0]
        if abs(cross) < TOLERANCE:
            return None

        # 行列式 D
        D = 2 * (
            A[0] * (B[1] - C[1]) +
            B[0] * (C[1] - A[1]) +
            C[0] * (A[1] - B[1])
        )

        if abs(D) < TOLERANCE:
            return None

        # 圆心坐标
        ux = (
            (A[0]**2 + A[1]**2) * (B[1] - C[1]) +
            (B[0]**2 + B[1]**2) * (C[1] - A[1]) +
            (C[0]**2 + C[1]**2) * (A[1] - B[1])
        ) / D

        uy = (
            (A[0]**2 + A[1]**2) * (C[0] - B[0]) +
            (B[0]**2 + B[1]**2) * (A[0] - C[0]) +
            (C[0]**2 + C[1]**2) * (B[0] - A[0])
        ) / D

        center = (ux, uy)
        radius = np.hypot(ux - A[0], uy - A[1])

        return center, radius

    def point_on_circle(pt_name, center, radius):
        px, py = coords[pt_name]
        cx, cy = center
        dist = np.hypot(cx - px, cy - py)
        return abs(dist - radius) < 1e-8

    # 收集所有由三个点确定的圆（用元组做key）
    raw_circles = defaultdict(set)

    for comb in combinations(point_names, 3):
        cir = get_circle_from_three(*comb)
        if cir is not None:
            raw_circles[cir].update(comb)

    # 扩展：把所有能落在圆上的点都加进来
    circles = []
    for (center, radius), pts_set in raw_circles.items():
        all_pts = set(pts_set)
        for pt in point_names:
            if pt not in all_pts:
                if point_on_circle(pt, center, radius):
                    all_pts.add(pt)
        if len(all_pts) >= 3:  # 至少三个点才算有效圆
            circles.append({
                "center": center,
                "radius": radius,
                "points": sorted(all_pts)
            })

    # 按点集去重（同一个点集可能有多个圆心/半径很接近的表示）
    circles_by_points = defaultdict(list)

    for cir in circles:
        key = frozenset(cir["points"])
        circles_by_points[key].append(cir)

    # 对每个点集取代表圆（目前取中间那个，可改成取半径最小/最大/平均等）
    dedup_circles = []
    for points_key, group in circles_by_points.items():
        if len(group) == 1:
            dedup_circles.append(group[0])
        else:
            # 按半径排序，取中间的作为代表（可改策略）
            group.sort(key=lambda x: x["radius"])
            rep = group[len(group) // 2]
            dedup_circles.append({
                "center": rep["center"],
                "radius": rep["radius"],
                "points": sorted(points_key)
            })

    # 最终排序：点数多 → 半径小
    dedup_circles.sort(key=lambda x: (-len(x["points"]), x["radius"]))

    return dedup_circles


def intersection_between_lines(point_names, coords) -> list[tuple[tuple[float, float], str]]:
    result = []
    ls = lines(point_names, coords)
    point_to_lines = defaultdict(set)
    for l1, l2 in combinations(ls, 2):
        A = coords[l1[0]]
        B = coords[l1[1]]
        C = coords[l2[0]]
        D = coords[l2[1]]
        AB = (B[0] - A[0], B[1] - A[1])
        CD = (D[0] - C[0], D[1] - C[1])
        denom = AB[0] * CD[1] - AB[1] * CD[0]
        if abs(denom) < TOLERANCE:
            continue
        CA = (A[0] - C[0], A[1] - C[1])
        t = (CA[0] * CD[1] - CA[1] * CD[0]) / denom
        inter = (A[0] - t * AB[0], A[1] - t * AB[1])
        inter = round_coord(inter)

        cleaned_l1 = []
        for name in l1:
            orig = coords[name]
            rounded = round_coord(orig)
            if rounded != inter:
                cleaned_l1.append(name)
        cleaned_l2 = []
        for name in l2:
            orig = coords[name]
            rounded = round_coord(orig)
            if rounded != inter:
                cleaned_l2.append(name)

        len1 = len(cleaned_l1)
        len2 = len(cleaned_l2)
        if len1 <= 1 and len2 <= 1:
            continue
        use_l1 = cleaned_l1
        use_l2 = cleaned_l2
        if len1 <= 1:
            use_l1 = l1[:]
        if len2 <= 1:
            use_l2 = l2[:]

        point_to_lines[inter].add(tuple(sorted(use_l1)))
        point_to_lines[inter].add(tuple(sorted(use_l2)))

    # 保证三线共点
    for coord, line_set in point_to_lines.items():
        if (len(line_set)) < 3:
            continue
        line_list = [list(t) for t in line_set]
        sorted_lines = sorted(
            line_list, key=lambda ln: ln[0])
        line1 = sorted_lines[0]
        line2 = sorted_lines[1]
        text1 = f"on_line X {line1[0]} {line1[1]}"
        text2 = f"on_line X {line2[0]} {line2[1]}"
        a, b = sorted([text1, text2])
        text = f"X@{coord[0]}_{coord[1]} = {a}, {b}"
        result.append((coord, text))
    return result


def intersection_between_circles(point_names, coords) -> list[tuple[tuple[float, float], str]]:
    result = []
    cs = circles(point_names, coords)
    point_to_circles = defaultdict(set)
    for cir1, cir2 in combinations(cs, 2):
        c1 = cir1["center"]
        c2 = cir2["center"]
        r1 = cir1["radius"]
        r2 = cir2["radius"]
        dx = c2[0] - c1[0]
        dy = c2[1] - c1[1]
        d = (dx*dx + dy*dy) ** 0.5
        if d < TOLERANCE:
            continue
        if d > r1 + r2 + TOLERANCE:
            continue
        if d + min(r1, r2) < max(r1, r2) - TOLERANCE:
            continue
        a = (r1*r1 - r2*r2 + d*d) / (2 * d)
        h_squared = r1*r1 - a*a
        h = (max(0.0, h_squared)) ** 0.5
        px = c1[0] + a * (dx / d)
        py = c1[1] + a * (dy / d)
        candidates = []
        if h < TOLERANCE:
            candidates.append((px, py))
        else:
            perp_x = -dy
            perp_y = dx
            perp_len = (perp_x*perp_x + perp_y*perp_y) ** 0.5
            ux = perp_x / perp_len
            uy = perp_y / perp_len
            pt1 = (px + h * ux, py + h * uy)
            pt2 = (px - h * ux, py - h * uy)
            candidates.append(pt1)
            candidates.append(pt2)
        unique = []
        for pt in candidates:
            if not any(
                ((pt[0] - u[0])**2 + (pt[1] - u[1])**2) ** 0.5 < TOLERANCE*2
                for u in unique
            ):
                unique.append(round_coord(pt))

        for pt in unique:
            cleaned_l1 = []
            for name in cir1["points"]:
                orig = coords[name]
                rounded = round_coord(orig)
                if rounded != pt:
                    cleaned_l1.append(name)
            cleaned_l2 = []
            for name in cir2["points"]:
                orig = coords[name]
                rounded = round_coord(orig)
                if rounded != pt:
                    cleaned_l2.append(name)
            len1 = len(cleaned_l1)
            len2 = len(cleaned_l2)
            if len1 <= 2 and len2 <= 2:
                continue
            use1 = cleaned_l1
            use2 = cleaned_l2
            if len1 <= 2:
                use1 = cir1["points"][:]
            if len2 <= 2:
                use2 = cir2["points"][:]

            point_to_circles[pt].add(tuple(use1))
            point_to_circles[pt].add(tuple(use2))

    # 保证三圆共点
    for coord, circle_set in point_to_circles.items():
        if (len(circle_set)) < 3:
            continue
        circle_list = [list(t) for t in circle_set]
        sorted_circles = sorted(
            circle_list, key=lambda ln: ln[0])
        c1 = sorted_circles[0]
        c2 = sorted_circles[1]
        text1 = f"on_circum X {c1[0]} {c1[1]} {c1[2]}"
        text2 = f"on_circum X {c2[0]} {c2[1]} {c2[2]}"
        a, b = sorted([text1, text2])
        text = f"X@{coord[0]}_{coord[1]} = {a}, {b}"
        result.append((coord, text))
    return result


def intersection_between_line_and_circle(point_names, coords) -> list[tuple[tuple[float, float], str]]:
    result = []
    ls = lines(point_names, coords)
    cs = circles(point_names, coords)
    point_to_objects = defaultdict(set)
    for cir in cs:
        for l in ls:
            center = cir["center"]
            radius = cir["radius"]
            A = coords[l[0]]
            B = coords[l[1]]
            dx = B[0] - A[0]
            dy = B[1] - A[1]
            fx = A[0] - center[0]
            fy = A[1] - center[1]
            a = dx*dx + dy*dy
            b = 2 * (fx*dx + fy*dy)
            c = fx*fx + fy*fy - radius*radius
            disc = b*b - 4*a*c
            if disc < -TOLERANCE:
                continue
            disc = max(0.0, disc)
            sqrt_disc = disc ** 0.5
            candidates = []
            if abs(a) < TOLERANCE:
                dist_sq = fx*fx + fy*fy
                if abs(dist_sq - radius*radius) < TOLERANCE:
                    candidates.append(A)
            else:
                for sign in [1, -1]:
                    t = (-b + sign * sqrt_disc) / (2 * a)
                    inter_x = A[0] + t * dx
                    inter_y = A[1] + t * dy
                    candidates.append((inter_x, inter_y))
            unique = []
            for pt in candidates:
                if not any(
                    abs(pt[0] - u[0]) < TOLERANCE and abs(pt[1] - u[1]) < TOLERANCE
                    for u in unique
                ):
                    unique.append(round_coord(pt))
            for pt in unique:
                cleaned_line = []
                for name in l:
                    orig = coords[name]
                    rounded_orig = round_coord(orig)
                    if rounded_orig != pt:
                        cleaned_line.append(name)
                cleaned_circle = []
                for name in cir["points"]:
                    orig = coords[name]
                    rounded_orig = round_coord(orig)
                    if rounded_orig != pt:
                        cleaned_circle.append(name)

                len_line = len(cleaned_line)
                len_circle = len(cleaned_circle)
                if len_line <= 2 and len_circle <= 3:
                    continue
                use_line = cleaned_line if len_line >= 2 else l[:]
                use_circle = cleaned_circle if len_circle >= 3 else cir["points"][:]

                point_to_objects[pt].add(("line", tuple(sorted(use_line))))
                point_to_objects[pt].add(("circle", tuple(sorted(use_circle))))

    # 保证至少3个组件
    for coord, obj_set in point_to_objects.items():
        line_objs = [obj for obj in obj_set if obj[0] == "line"]
        circle_objs = [obj for obj in obj_set if obj[0] == "circle"]
        lines_count = len(line_objs)
        circles_count = len(circle_objs)
        if lines_count + circles_count < 3:
            continue
        if lines_count <= 0 or circles_count <= 0:
            continue

        line_objs.sort(key=lambda x: x[1][0])
        smallest_line = line_objs[0][1]
        line_part = f"on_line X {smallest_line[0]} {smallest_line[1]}"
        circle_objs.sort(key=lambda x: x[1][0])
        smallest_circle = circle_objs[0][1]
        circle_part = f"on_circum X {smallest_circle[0]} {smallest_circle[1]} {smallest_circle[2]}"

        text = f"X@{coord[0]}_{coord[1]} = " + circle_part + ", " + line_part
        result.append((coord, text))

    return result


def midpoint(point_names, coords) -> list[tuple[tuple[float, float], str]]:
    result = []
    ls = lines(point_names, coords)
    cs = circles(point_names, coords)
    for p1, p2 in combinations(point_names, 2):
        x1, y1 = coords[p1]
        x2, y2 = coords[p2]
        mid_coord = ((x1 + x2) / 2, (y1 + y2) / 2)

        # 要求非平凡的在线上或圆上
        if check_on_line(mid_coord, ls, coords, [[p1, p2]]) or check_on_circle(mid_coord, cs, coords):
            text = f"X@{mid_coord[0]}_{mid_coord[1]} = midpoint X {p1} {p2}"
            result.append((mid_coord, text))

    return result


def reflection(point_names, coords) -> list[tuple[tuple[float, float], str]]:
    result = []
    ls = lines(point_names, coords)
    cs = circles(point_names, coords)
    # 关于点对称
    for center_name in point_names:  # 中心点（对称中心）
        for pt_name in point_names:  # 被对称的点
            if pt_name == center_name:
                continue
            center_coord = coords[center_name]
            pt_coord = coords[pt_name]
            refl_coord = (
                2 * center_coord[0] - pt_coord[0],
                2 * center_coord[1] - pt_coord[1]
            )

            # 要求非平凡的在线上或圆上
            if check_on_line(refl_coord, ls, coords, [[center_name, pt_name]]) or check_on_circle(refl_coord, cs, coords):
                text = f"X@{refl_coord[0]}_{refl_coord[1]} = mirror X {pt_name} {center_name}"
                result.append((refl_coord, text))

    # 关于线对称
    for l in ls:
        line_sorted = sorted(l)
        for pt_name in point_names:
            if pt_name in line_sorted:
                continue
            px, py = coords[pt_name]
            x1, y1 = coords[line_sorted[0]]
            x2, y2 = coords[line_sorted[1]]
            abx = x2 - x1
            aby = y2 - y1
            denom = abx * abx + aby * aby
            if abs(denom) < TOLERANCE:
                continue
            apx = px - x1
            apy = py - y1
            t = (apx * abx + apy * aby) / denom
            foot_coord = (x1 + t * abx, y1 + t * aby)
            refl_coord = (2 * foot_coord[0] - px, 2 * foot_coord[1] - py)

            # 要求非平凡的在线上或圆上
            if check_on_line(refl_coord, ls, coords) or check_on_circle(refl_coord, cs, coords):
                text = f"X@{refl_coord[0]}_{refl_coord[1]} = reflect X {pt_name} {line_sorted[0]} {line_sorted[1]}"
                result.append((refl_coord, text))

    return result


def foot(point_names, coords) -> list[tuple[tuple[float, float], str]]:
    ls = lines(point_names, coords)
    result = []
    for l in ls:
        line_sorted = sorted(l)
        for pt_name in point_names:
            if pt_name in line_sorted:
                continue
            px, py = coords[pt_name]
            x1, y1 = coords[line_sorted[0]]
            x2, y2 = coords[line_sorted[1]]
            abx = x2 - x1
            aby = y2 - y1
            denom = abx * abx + aby * aby
            if abs(denom) < TOLERANCE:
                continue
            apx = px - x1
            apy = py - y1
            t = (apx * abx + apy * aby) / denom
            foot_coord = (x1 + t * abx, y1 + t * aby)

            # 要求非平凡的在线上或圆上
            if check_on_line(foot_coord, ls, coords, [[pt_name], line_sorted]):
                text = f"X@{foot_coord[0]}_{foot_coord[1]} = foot X {pt_name} {line_sorted[0]} {line_sorted[1]}"
                result.append((foot_coord, text))

    return result


def enhance_text_with_potential_points(original_text: str, generator: PointGenerator) -> str:
    # 1. 提取原始点
    point_names, coords = extract_points(original_text)

    MAX_NEW_POINTS = 2

    # 先随机选取若干种类（数量 < MAX_NEW_POINTS，且至少 1 种）
    all_types = list(range(6))  # 0..5 六种类型
    random.shuffle(all_types)
    max_type_count = max(1, min(MAX_NEW_POINTS, len(all_types)))
    type_count = random.randint(1, max_type_count)
    selected_types = all_types[:type_count]

    # 只对选中的种类计算 potential points，避免不必要的计算
    type_to_points: dict[int, list[tuple[tuple[float, float], str]]] = {}
    for t in selected_types:
        if t == 0:
            type_to_points[t] = intersection_between_lines(point_names, coords)
        elif t == 1:
            type_to_points[t] = intersection_between_circles(point_names, coords)
        elif t == 2:
            type_to_points[t] = intersection_between_line_and_circle(point_names, coords)
        elif t == 3:
            type_to_points[t] = midpoint(point_names, coords)
        elif t == 4:
            type_to_points[t] = reflection(point_names, coords)
        elif t == 5:
            type_to_points[t] = foot(point_names, coords)

    # 如果选中的所有类型都没有可用点，直接返回
    if all(len(v) == 0 for v in type_to_points.values()):
        return original_text

    added_count = 0
    current_text = original_text
    existing_coords = list(coords.values())

    # 为了避免死循环，设置一个最大尝试次数
    max_trials = MAX_NEW_POINTS * 20
    trials = 0

    while added_count < MAX_NEW_POINTS and trials < max_trials:
        trials += 1
        # 每次选择一个新点时，从已选类型中随机一个种类
        t = random.choice(selected_types)
        candidates = type_to_points.get(t, [])
        if not candidates:
            # 该类型已经没有候选点，继续尝试
            continue

        # 从该种类的 points 中随机选取一个
        coord, text_tmpl = random.choice(candidates)

        # 距离过滤
        if is_point_too_close([coord], existing_coords) or is_point_too_far([coord], existing_coords):
            # 该点不合适，继续尝试
            # 同时从该类型候选中删除这个点，避免反复选到
            type_to_points[t] = [item for item in candidates if item[0] != coord]
            continue

        # 通过过滤后，真正加入
        existing_coords.append(coord)

        new_point_names = generator.prefetch_points(1)
        generator.define_points(new_point_names)

        new_name = new_point_names[0]
        construction_str = text_tmpl.replace('X', new_name)
        current_text += "; " + construction_str
        added_count += 1

        # 为了减少将来重复选择同一个几何位置，把该点从候选集中删除
        type_to_points[t] = [item for item in candidates if item[0] != coord]

    return current_text
