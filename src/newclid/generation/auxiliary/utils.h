#pragma once

#include <array>
#include <cmath>
#include <string>
#include <unordered_map>
#include <vector>

namespace auxiliary_c {

// Constants
constexpr int ROUND_DECIMALS = 9;
constexpr double MIN_DIST = 0.05;
constexpr double MAX_DIST = 15.0;

// Point type using std::array for better cache locality
using Point = std::array<double, 2>;

// Basic utilities

// Round coordinates to specified decimal places (normalize -0.0 to 0.0)
inline Point round_coord(const Point& p) {
    double x = std::round(p[0] * std::pow(10, ROUND_DECIMALS)) / std::pow(10, ROUND_DECIMALS);
    double y = std::round(p[1] * std::pow(10, ROUND_DECIMALS)) / std::pow(10, ROUND_DECIMALS);
    return {x + 0.0, y + 0.0};
}

// Compute squared distance between two points
inline double dist_sq(const Point& a, const Point& b) {
    double dx = a[0] - b[0];
    double dy = a[1] - b[1];
    return dx * dx + dy * dy;
}

// Compute distance between two points
inline double dist(const Point& a, const Point& b) {
    return std::sqrt(dist_sq(a, b));
}

// Check if any point is too close to existing points
bool is_point_too_close(const std::vector<Point>& points,
                       const std::vector<Point>& existing);

// Check if any point is too far from all existing points
bool is_point_too_far(const std::vector<Point>& points,
                      const std::vector<Point>& existing);

// Compute rounded coordinates for all points
inline std::unordered_map<std::string, Point> compute_rounded_coords(
    const std::vector<std::string>& point_names,
    const std::unordered_map<std::string, Point>& coords) {
    std::unordered_map<std::string, Point> result;
    for (const auto& name : point_names) {
        result[name] = round_coord(coords.at(name));
    }
    return result;
}

} // namespace auxiliary_c
