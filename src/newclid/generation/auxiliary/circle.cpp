#include "circle.h"
#include "utils.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>

namespace auxiliary_c {

std::string get_circle_name(const std::string& p1, const std::string& p2, const std::string& p3) {
    std::vector<std::string> points = {p1, p2, p3};
    std::sort(points.begin(), points.end());
    return points[0] + "_" + points[1] + "_" + points[2];
}

// Returns {center, radius}. If points are collinear, returns {{nan,nan}, nan}.
Circle circumcircle(const Point& a, const Point& b, const Point& c) {
    double ax = a[0], ay = a[1];
    double bx = b[0], by = b[1];
    double cx = c[0], cy = c[1];

    // Check collinearity: cross product of (B-A) x (C-A)
    double bax = bx - ax, bay = by - ay;
    double cax = cx - ax, cay = cy - ay;
    double cross = bax * cay - bay * cax;
    if (std::abs(cross) < 1e-8) {
        return {{std::numeric_limits<double>::quiet_NaN(),
                 std::numeric_limits<double>::quiet_NaN()},
                std::numeric_limits<double>::quiet_NaN()};
    }

    double d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));

    double ux = ((ax*ax + ay*ay) * (by - cy) +
                (bx*bx + by*by) * (cy - ay) +
                (cx*cx + cy*cy) * (ay - by)) / d;

    double uy = ((ax*ax + ay*ay) * (cx - bx) +
                (bx*bx + by*by) * (ax - cx) +
                (cx*cx + cy*cy) * (bx - ax)) / d;

    Point center = {ux, uy};
    double radius = dist(center, a);

    return {center, radius};
}

bool check_on_circle(const Point& a, const Point& b, const Point& c, const Point& d) {
    // Check if point d lies on the circle passing through a, b, c
    Circle circle = circumcircle(a, b, c);
    double dist_from_center = dist(d, circle.center);
    return std::abs(dist_from_center - circle.radius) < 1e-8;
}

std::vector<std::tuple<std::string, Point, double, std::vector<std::string>>>
circles(const std::vector<std::string>& point_names,
        const std::unordered_map<std::string, Point>& coords) {

    std::vector<std::tuple<std::string, Point, double, std::vector<std::string>>> result;

    int n = point_names.size();
    if (n < 3) return result;

    // For each triplet of points, define a circle and find other points on it
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            for (int k = j + 1; k < n; ++k) {
                const std::string& p1 = point_names[i];
                const std::string& p2 = point_names[j];
                const std::string& p3 = point_names[k];

                const Point& a = coords.at(p1);
                const Point& b = coords.at(p2);
                const Point& c = coords.at(p3);

                Circle circle = circumcircle(a, b, c);
                // Skip degenerate (collinear) circles
                if (std::isnan(circle.radius)) continue;
                std::vector<std::string> points_on_circle = {p1, p2, p3};

                // Find other points on this circle
                for (int l = 0; l < n; ++l) {
                    if (l == i || l == j || l == k) continue;
                    const std::string& p4 = point_names[l];
                    const Point& d = coords.at(p4);

                    if (check_on_circle(a, b, c, d)) {
                        points_on_circle.push_back(p4);
                    }
                }

                // Only keep circles with 3 or more points (we already have 3)
                if (points_on_circle.size() >= 3) {
                    std::string circle_name = get_circle_name(p1, p2, p3);
                    result.push_back({circle_name, circle.center, circle.radius, points_on_circle});
                }
            }
        }
    }

    // Remove duplicates (circles with same set of points but different reference points)
    std::set<std::string> seen_circles;
    std::vector<std::tuple<std::string, Point, double, std::vector<std::string>>> unique_result;

    for (auto& [name, center, radius, points] : result) {
        // Create sorted signature for the circle
        std::vector<std::string> sorted_points = points;
        std::sort(sorted_points.begin(), sorted_points.end());
        std::string signature;
        for (const auto& p : sorted_points) {
            signature += p + ",";
        }

        if (seen_circles.find(signature) == seen_circles.end()) {
            seen_circles.insert(signature);
            unique_result.push_back({name, center, radius, points});
        }
    }

    return unique_result;
}

} // namespace auxiliary_c
