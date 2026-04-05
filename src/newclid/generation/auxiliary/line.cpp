#include "line.h"
#include "utils.h"
#include <algorithm>
#include <cmath>
#include <set>

namespace auxiliary_c {

std::string get_line_name(const std::string& p1, const std::string& p2) {
    if (p1 < p2) {
        return p1 + "_" + p2;
    } else {
        return p2 + "_" + p1;
    }
}

bool check_on_line(const Point& a, const Point& b, const Point& c) {
    // Check if point c lies on line through a and b
    // Using distance from point to line: |cross| / |direction| < TOLERANCE
    double dx = b[0] - a[0];
    double dy = b[1] - a[1];
    double line_len = std::sqrt(dx * dx + dy * dy);
    if (line_len < 1e-8) return false;
    double cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    return std::abs(cross) / line_len < 1e-8;  // TOLERANCE = 1e-8, matching Python
}

std::vector<std::pair<std::string, std::vector<std::string>>>
lines(const std::vector<std::string>& point_names,
       const std::unordered_map<std::string, Point>& coords) {

    std::vector<std::pair<std::string, std::vector<std::string>>> result;

    int n = point_names.size();
    if (n < 3) return result;

    // For each pair of points, find all points that lie on their line
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            const std::string& p1 = point_names[i];
            const std::string& p2 = point_names[j];
            const Point& a = coords.at(p1);
            const Point& b = coords.at(p2);

            // Skip degenerate pairs (nearly coincident points)
            double seg_len = dist(a, b);
            if (seg_len < 1e-8) continue;

            std::vector<std::string> points_on_line = {p1, p2};

            // Find other points on this line
            for (int k = 0; k < n; ++k) {
                if (k == i || k == j) continue;
                const std::string& p3 = point_names[k];
                const Point& c = coords.at(p3);

                if (check_on_line(a, b, c)) {
                    points_on_line.push_back(p3);
                }
            }

            // Keep lines with 2 or more points (every pair defines a line)
            if (points_on_line.size() >= 2) {
                std::string line_name = get_line_name(p1, p2);
                result.push_back({line_name, points_on_line});
            }
        }
    }

    // Remove duplicates (lines with same set of points but different endpoints)
    std::set<std::string> seen_lines;
    std::vector<std::pair<std::string, std::vector<std::string>>> unique_result;

    for (auto& [name, points] : result) {
        // Create sorted signature for the line
        std::vector<std::string> sorted_points = points;
        std::sort(sorted_points.begin(), sorted_points.end());
        std::string signature;
        for (const auto& p : sorted_points) {
            signature += p + ",";
        }

        if (seen_lines.find(signature) == seen_lines.end()) {
            seen_lines.insert(signature);
            unique_result.push_back({name, points});
        }
    }

    return unique_result;
}

} // namespace auxiliary_c
