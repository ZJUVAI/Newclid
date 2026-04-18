#pragma once

#include "circle.h"
#include <cstdint>
#include <string>
#include <vector>
#include <array>
#include <unordered_map>
#include <tuple>
#include <set>
#include <map>

namespace auxiliary_c {

using Point = std::array<double, 2>;
using Line = std::pair<Point, Point>;

// Return type: list of (coord, construction_statements)
using PotentialPoint = std::tuple<Point, std::vector<std::string>>;
using PotentialPoints = std::vector<PotentialPoint>;

// Main entry point: find and select potential auxiliary points
PotentialPoints add_potential_points(
    const std::vector<std::string>& point_names,
    const std::unordered_map<std::string, Point>& coords,
    int max_points,
    uint32_t seed = 0);

// Intersection functions (internal)
PotentialPoints intersection_between_lines(
    const std::vector<std::string>& point_names,
    const std::unordered_map<std::string, Point>& coords,
    const std::vector<std::pair<std::string, std::vector<std::string>>>* lines_data,
    const std::unordered_map<std::string, Point>* rounded_coords);

PotentialPoints intersection_between_circles(
    const std::vector<std::string>& point_names,
    const std::unordered_map<std::string, Point>& coords,
    const std::vector<std::tuple<std::string, Point, double, std::vector<std::string>>>* circles_data,
    const std::unordered_map<std::string, Point>* rounded_coords);

PotentialPoints intersection_between_line_and_circle(
    const std::vector<std::string>& point_names,
    const std::unordered_map<std::string, Point>& coords,
    const std::vector<std::pair<std::string, std::vector<std::string>>>* lines_data,
    const std::vector<std::tuple<std::string, Point, double, std::vector<std::string>>>* circles_data,
    const std::unordered_map<std::string, Point>* rounded_coords);

// Auxiliary point functions (internal)
PotentialPoints midpoint(
    const std::vector<std::string>& point_names,
    const std::unordered_map<std::string, Point>& coords,
    const std::vector<std::pair<std::string, std::vector<std::string>>>* lines_data,
    const std::vector<std::tuple<std::string, Point, double, std::vector<std::string>>>* circles_data);

PotentialPoints reflection(
    const std::vector<std::string>& point_names,
    const std::unordered_map<std::string, Point>& coords,
    const std::vector<std::pair<std::string, std::vector<std::string>>>* lines_data,
    const std::vector<std::tuple<std::string, Point, double, std::vector<std::string>>>* circles_data);

PotentialPoints foot(
    const std::vector<std::string>& point_names,
    const std::unordered_map<std::string, Point>& coords,
    const std::vector<std::pair<std::string, std::vector<std::string>>>* lines_data);

} // namespace auxiliary_c
