#pragma once

#include <string>
#include <vector>
#include <array>
#include <unordered_map>

namespace auxiliary_c {

using Point = std::array<double, 2>;

// Circle type
struct Circle {
    Point center;
    double radius;
};

// Find all circles defined by three or more concyclic points
// Returns list of (circle_name, {center, radius, point_names_on_circle})
std::vector<std::tuple<std::string, Point, double, std::vector<std::string>>>
circles(const std::vector<std::string>& point_names,
        const std::unordered_map<std::string, Point>& coords);

// Check if three points are concyclic (they always define a unique circle)
// But we use this to check if a fourth point lies on the same circle
bool check_on_circle(const Point& a, const Point& b, const Point& c, const Point& d);

// Internal: compute circumcircle of three points
Circle circumcircle(const Point& a, const Point& b, const Point& c);

// Internal: get circle name from three point names
std::string get_circle_name(const std::string& p1, const std::string& p2, const std::string& p3);

} // namespace auxiliary_c
