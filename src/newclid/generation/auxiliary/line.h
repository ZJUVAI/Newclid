#pragma once

#include <string>
#include <vector>
#include <array>
#include <unordered_map>

namespace auxiliary_c {

using Point = std::array<double, 2>;

// Find all lines defined by collinear points
// Returns list of (line_name, point_names_on_line)
std::vector<std::pair<std::string, std::vector<std::string>>>
lines(const std::vector<std::string>& point_names,
       const std::unordered_map<std::string, Point>& coords);

// Check if three points are collinear
bool check_on_line(const Point& a, const Point& b, const Point& c);

// Internal: get line name from two point names
std::string get_line_name(const std::string& p1, const std::string& p2);

} // namespace auxiliary_c
