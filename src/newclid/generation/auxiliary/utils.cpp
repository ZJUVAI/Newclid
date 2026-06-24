#include "utils.h"
#include <algorithm>
#include <cmath>

namespace auxiliary_c {

bool is_point_too_close(const std::vector<Point>& points,
                       const std::vector<Point>& existing) {
    if (existing.size() < 2) return false;

    // Calculate average pairwise distance
    double total_dist = 0.0;
    int count = 0;
    int n = (int)existing.size();
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            total_dist += dist(existing[i], existing[j]);
            count++;
        }
    }
    double avg_dist = total_dist / count;

    double tol = 0.05;
    double round_eps = 1e-10;

    for (const auto& p : points) {
        for (const auto& e : existing) {
            double d = dist(p, e);
            if (round_eps < d && d < tol * avg_dist) {
                return true;
            }
        }
    }
    return false;
}

bool is_point_too_far(const std::vector<Point>& points,
                      const std::vector<Point>& existing) {
    if (existing.size() < 2) return false;

    double max_dist = 6.0;
    for (const auto& p : points) {
        for (const auto& e : existing) {
            double d = dist(p, e);
            if(d > max_dist)
            {
                return true;
            }
        }
    }
    return false;
}

} // namespace auxiliary_c
