#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <vector>
#include <string>
#include <array>

#include "geometry.h"
#include "line.h"
#include "circle.h"
#include "utils.h"

namespace py = pybind11;

static std::unordered_map<std::string, auxiliary_c::Point> dict_to_coords(
    const std::unordered_map<std::string, std::array<double, 2>>& coords_dict) {
    std::unordered_map<std::string, auxiliary_c::Point> coords;
    for (const auto& [name, coord] : coords_dict) {
        coords[name] = coord;
    }
    return coords;
}

static std::unordered_map<std::string, auxiliary_c::Point> make_rounded_coords(
    const std::vector<std::string>& point_names,
    const std::unordered_map<std::string, auxiliary_c::Point>& coords) {
    std::unordered_map<std::string, auxiliary_c::Point> rc;
    for (const auto& name : point_names)
        rc[name] = auxiliary_c::round_coord(coords.at(name));
    return rc;
}

PYBIND11_MODULE(auxiliary, m) {
    m.doc() = "Fast C++ implementation for auxiliary point detection";

    m.def("add_potential_points",
        [](const std::vector<std::string>& point_names,
           const std::unordered_map<std::string, std::array<double, 2>>& coords_dict,
           int max_points = 2,
           uint32_t seed = 0) {
            auto coords = dict_to_coords(coords_dict);
            return auxiliary_c::add_potential_points(point_names, coords, max_points, seed);
        },
        py::arg("point_names"), py::arg("coords"), py::arg("max_points") = 2, py::arg("seed") = 0);

    m.def("lines_cpp",
        [](const std::vector<std::string>& point_names,
           const std::unordered_map<std::string, std::array<double, 2>>& coords_dict) {
            auto coords = dict_to_coords(coords_dict);
            return auxiliary_c::lines(point_names, coords);
        },
        py::arg("point_names"), py::arg("coords"));

    m.def("circles_cpp",
        [](const std::vector<std::string>& point_names,
           const std::unordered_map<std::string, std::array<double, 2>>& coords_dict) {
            auto coords = dict_to_coords(coords_dict);
            return auxiliary_c::circles(point_names, coords);
        },
        py::arg("point_names"), py::arg("coords"));

    m.def("intersection_between_lines_cpp",
        [](const std::vector<std::string>& point_names,
           const std::unordered_map<std::string, std::array<double, 2>>& coords_dict) {
            auto coords = dict_to_coords(coords_dict);
            auto rc = make_rounded_coords(point_names, coords);
            auto ld = auxiliary_c::lines(point_names, coords);
            return auxiliary_c::intersection_between_lines(point_names, coords, &ld, &rc);
        },
        py::arg("point_names"), py::arg("coords"));

    m.def("intersection_between_circles_cpp",
        [](const std::vector<std::string>& point_names,
           const std::unordered_map<std::string, std::array<double, 2>>& coords_dict) {
            auto coords = dict_to_coords(coords_dict);
            auto rc = make_rounded_coords(point_names, coords);
            auto cd = auxiliary_c::circles(point_names, coords);
            return auxiliary_c::intersection_between_circles(point_names, coords, &cd, &rc);
        },
        py::arg("point_names"), py::arg("coords"));

    m.def("intersection_between_line_and_circle_cpp",
        [](const std::vector<std::string>& point_names,
           const std::unordered_map<std::string, std::array<double, 2>>& coords_dict) {
            auto coords = dict_to_coords(coords_dict);
            auto rc = make_rounded_coords(point_names, coords);
            auto ld = auxiliary_c::lines(point_names, coords);
            auto cd = auxiliary_c::circles(point_names, coords);
            return auxiliary_c::intersection_between_line_and_circle(point_names, coords, &ld, &cd, &rc);
        },
        py::arg("point_names"), py::arg("coords"));

    m.def("midpoint_cpp",
        [](const std::vector<std::string>& point_names,
           const std::unordered_map<std::string, std::array<double, 2>>& coords_dict) {
            auto coords = dict_to_coords(coords_dict);
            auto ld = auxiliary_c::lines(point_names, coords);
            auto cd = auxiliary_c::circles(point_names, coords);
            return auxiliary_c::midpoint(point_names, coords, &ld, &cd);
        },
        py::arg("point_names"), py::arg("coords"));

    m.def("reflection_cpp",
        [](const std::vector<std::string>& point_names,
           const std::unordered_map<std::string, std::array<double, 2>>& coords_dict) {
            auto coords = dict_to_coords(coords_dict);
            auto ld = auxiliary_c::lines(point_names, coords);
            auto cd = auxiliary_c::circles(point_names, coords);
            return auxiliary_c::reflection(point_names, coords, &ld, &cd);
        },
        py::arg("point_names"), py::arg("coords"));

    m.def("foot_cpp",
        [](const std::vector<std::string>& point_names,
           const std::unordered_map<std::string, std::array<double, 2>>& coords_dict) {
            auto coords = dict_to_coords(coords_dict);
            auto ld = auxiliary_c::lines(point_names, coords);
            return auxiliary_c::foot(point_names, coords, &ld);
        },
        py::arg("point_names"), py::arg("coords"));

    m.attr("__version__") = "0.1.0";
}
