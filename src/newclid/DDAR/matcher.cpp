#include "matcher.hpp"
#include "numerical.hpp"
#include "theorem.hpp"
#include "problem.hpp"
#include "type/dist.hpp"
#include "type/angle.hpp"
#include "predicate/congruent_triangles.hpp"
#include "predicate/secant.hpp"
#include "predicate/eqpoint.hpp"
#include "predicate/para.hpp"
#include "predicate/perp.hpp"
#include <algorithm>
#include <chrono>
#include <iostream>
#include <tuple>
#include <vector>
#include <set>
#include <map>
#include <unordered_map>
#include <functional>
#include <iomanip>
#include <cmath>

using namespace std;

Matcher::Matcher(Problem *prob, const std::map<std::string, bool> &config)
    : _problem(prob), _config(config)
{
    match_similar_triangles();
    match_between();
    match_equal_angles();
    match_circles();
    match_orthocenters();
    match_perps_paras();
}

vector<tuple<double, double, Triangle>> Matcher::all_triangles()
{
    vector<tuple<double, double, Triangle>> res;
    const size_t num_pts = _problem->num_points();
    res.reserve(num_pts * (num_pts - 1) * (num_pts - 2) / 6);
    for (const auto &pt_a : _problem->points())
    {
        for (const auto &pt_b : _problem->points())
        {
            if (pt_a.is_close(pt_b))
            {
                continue;
            }
            for (const auto &pt_c : _problem->points())
            {
                if (pt_a.is_close(pt_b) || pt_a.is_close(pt_c) || Coll(pt_a, pt_b, pt_c).check_equations())
                {
                    continue;
                }
                double const ab = Dist(pt_a, pt_b).to_double();
                double const ac = Dist(pt_a, pt_c).to_double();
                double const bc = Dist(pt_b, pt_c).to_double();
                if (ab > (1 + REL_TOL) * bc || bc > (1 + REL_TOL) * ac)
                {
                    continue;
                }
                res.emplace_back(ab / ac,
                                 ab / bc,
                                 Triangle(pt_a, pt_b, pt_c));
            }
        }
    }
    return res;
}

void Matcher::on_similar_triangles(const SimilarTriangles &simtri)
{
    for (const auto &rotated : simtri.cyclic_rotations())
    {
        insert_theorem(Theorem::similar_triangles_of_sas(rotated));
    }

    insert_theorem(Theorem::similar_triangles_properties(simtri));
    insert_theorem(Theorem::similar_triangles_of_aa(simtri));
    insert_theorem(Theorem::similar_triangles_of_sss(simtri));

    CongruentTriangles const congtri(simtri.left(), simtri.right(), simtri.sameclock());
    if (congtri.check_numerically())
    {
        // Use SSS and SAS to derive congruent triangles
        for (const auto &rotated : congtri.cyclic_rotations())
        {
            insert_theorem(Theorem::congruent_triangles_of_sas(rotated));
        }
        insert_theorem(Theorem::congruent_triangles_of_sss(congtri));
        insert_theorem(Theorem::congruent_triangles_properties(congtri));
    }
}

void Matcher::match_similar_triangles()
{
    using item_type = tuple<double, double, Triangle>;
    vector<item_type> triangles = all_triangles();

    if (triangles.empty())
    {
        return;
    }

    sort(triangles.begin(), triangles.end(),
         [](const item_type &a, const item_type &b)
         {
             double ratio1_a = get<0>(a);
             double ratio1_b = get<0>(b);
             if (fabs(ratio1_a - ratio1_b) >= 1e-8)
             {
                 return ratio1_a < ratio1_b;
             }
             else
             {
                 return get<1>(a) < get<1>(b);
             }
         });

    vector<item_type> bucket;
    bucket.push_back(triangles[0]);

    for (size_t i = 1; i < triangles.size(); i++)
    {
        const auto &prev = bucket.back();
        const auto &curr = triangles[i];
        if (Numerical::close_enough(get<0>(prev), get<0>(curr)) &&
            Numerical::close_enough(get<1>(prev), get<1>(curr)))
        {
            bucket.push_back(curr);
        }
        else
        {
            if (bucket.size() > 1)
            {
                size_t n = bucket.size();
                for (size_t left = 0; left < n; left++)
                {
                    double area_left = get<2>(bucket[left]).area();
                    for (size_t right = left + 1; right < n; right++)
                    {
                        double area_right = get<2>(bucket[right]).area();
                        bool sameclock = (area_left > 0) == (area_right > 0);
                        on_similar_triangles({get<2>(bucket[left]), get<2>(bucket[right]), sameclock});
                    }
                }
            }
            bucket.clear();
            bucket.push_back(curr);
        }
    }

    if (bucket.size() > 1)
    {
        size_t n = bucket.size();
        for (size_t left = 0; left < n; left++)
        {
            double area_left = get<2>(bucket[left]).area();
            for (size_t right = left + 1; right < n; right++)
            {
                double area_right = get<2>(bucket[right]).area();
                bool sameclock = (area_left > 0) == (area_right > 0);
                on_similar_triangles({get<2>(bucket[left]), get<2>(bucket[right]), sameclock});
            }
        }
    }
}

vector<tuple<double, Coll>> Matcher::all_betweens()
{
    vector<tuple<double, Coll>> res;
    const size_t num_pts = _problem->num_points();
    res.reserve(num_pts * (num_pts - 1) / 2);
    for (const auto &right : _problem->points())
    {
        for (const auto &left : _problem->points())
        {
            for (const auto &middle : _problem->points())
            {
                if (left.is_close(middle) || middle.is_close(right))
                {
                    continue;
                }
                Coll const pred(left, middle, right);
                if (!pred.is_between())
                {
                    continue;
                }
                double const dist_left = Dist(left, middle).to_double();
                double const dist_right = Dist(middle, right).to_double();
                if (dist_left <= (1 + REL_TOL) * dist_right)
                {
                    res.emplace_back(dist_left / (dist_left + dist_right), pred);
                }
            }
        }
    }
    return res;
}

vector<pair<Point, Point>> Matcher::all_eqpoints()
{
    const auto &pts = _problem->points();
    vector<pair<Point, Point>> res;
    for (size_t i = 0; i < pts.size(); i++)
    {
        for (size_t j = i + 1; j < pts.size(); j++)
        {
            if (pts[i].is_close(pts[j]))
            {
                res.push_back(make_pair(pts[i], pts[j]));
            }
        }
    }
    return res;
}

void Matcher::on_pappus(const Pappus &pappus)
{
    for (const auto &rotated : pappus.permutations())
    {
        insert_theorem(Theorem::pappus(rotated));
    }
}

void Matcher::on_between(const Coll &coll)
{
    for (const auto &rotated : coll.cyclic_rotations())
    {
        insert_theorem(Theorem::coll_of_para(rotated));
        insert_theorem(Theorem::para_of_coll(rotated));
    }
}

void Matcher::on_midpoint(const Midp &midp)
{
    insert_theorem(Theorem::coll_cong_of_midpoint(midp));
    insert_theorem(Theorem::midpoint_of_coll_cong(midp));
    insert_theorem(Theorem::midpoint_ratio_dist(midp));
}

void Matcher::on_eqratio(const Coll &left, const Coll &right)
{
    auto l = left.cyclic_rotations();
    auto r = right.cyclic_rotations();
    insert_theorem(Theorem::eqratio_of_coll(l[0], r[0]));
    insert_theorem(Theorem::eqratio_of_coll(l[1], r[1]));
    insert_theorem(Theorem::eqratio_of_coll(l[2], r[2]));

    if (left.a() == right.a())
    {
        insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(left, right));
        insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(Coll(left.a(), left.c(), left.b()), Coll(right.a(), right.c(), right.b())));
        insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(left, right));
        insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(Coll(left.a(), left.c(), left.b()), Coll(right.a(), right.c(), right.b())));
    }
    else if (left.b() == right.b())
    {
        insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(Coll(left.b(), left.a(), left.c()), Coll(right.b(), right.a(), right.c())));
        insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(Coll(left.b(), left.c(), left.a()), Coll(right.b(), right.c(), right.a())));
        insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(Coll(left.b(), left.a(), left.c()), Coll(right.b(), right.a(), right.c())));
        insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(Coll(left.b(), left.c(), left.a()), Coll(right.b(), right.c(), right.a())));
    }
    else if (left.c() == right.c())
    {
        insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(Coll(left.c(), left.a(), left.b()), Coll(right.c(), right.a(), right.b())));
        insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(Coll(left.c(), left.b(), left.a()), Coll(right.c(), right.b(), right.a())));
        insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(Coll(left.c(), left.a(), left.b()), Coll(right.c(), right.a(), right.b())));
        insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(Coll(left.c(), left.b(), left.a()), Coll(right.c(), right.b(), right.a())));
    }

    Thales const thales(left, right);
    if (!thales.check_numerically())
    {
        return;
    }
    for (const auto &rotated : thales.permutations())
    {
        insert_theorem(Theorem::thales_para_of_eqratio(rotated));
    }
    insert_theorem(Theorem::thales_eqratio_of_para(thales));
}

void Matcher::match_between()
{
    using item_type = tuple<double, Coll>;
    vector<item_type> betweens = all_betweens();

    vector<pair<Point, Point>> eqpoints = all_eqpoints();

    for (const auto &eq_pair : eqpoints)
    {
        const Point &p1 = eq_pair.first;
        const Point &p2 = eq_pair.second;
        vector<Coll> colls;
        for (const auto &item : betweens)
        {
            const Coll &coll = get<1>(item);
            if (coll.a() == p1 || coll.b() == p1 || coll.c() == p1)
            {
                colls.push_back(coll);
            }
        }
        set<Point> used_points;
        vector<tuple<double, Point, Point>> candidates;
        for (const auto &coll : colls)
        {
            Point a = p1 == coll.a() ? coll.b() : coll.a();
            Point b = p1 == coll.c() ? coll.b() : coll.c();
            used_points.insert(a);
            used_points.insert(b);
            candidates.emplace_back(coll.angle(), a, b);
        }
        for (const Point &pt : _problem->points())
        {
            if (pt == p1 || p1.is_close(pt))
            {
                continue;
            }
            candidates.emplace_back(Slope(p1, pt).angle(), p1, pt);
            insert_theorem(Theorem::cong_of_eqpoints(EqPoint(p1, p2), pt));
        }

        std::sort(candidates.begin(), candidates.end());

        for (size_t i = 0; i < candidates.size(); ++i)
        {
            const Point &a = std::get<1>(candidates[i]);
            const Point &b = std::get<2>(candidates[i]);
            insert_theorem(Theorem::eqpoints_of_same_ratio_on_line(p1, p2, a, b));
            for (size_t j = i + 1; j < candidates.size(); ++j)
            {
                const Point &c = std::get<1>(candidates[j]);
                const Point &d = std::get<2>(candidates[j]);
                if (Coll(a, b, d).check_numerically())
                {
                    continue;
                }
                insert_theorem(Theorem::eqpoints_of_same_intersections(p1, p2, a, b, c, d));
            }
        }
    }

    if (betweens.empty())
    {
        return;
    }

    // for (size_t i = 0; i < betweens.size(); i++)
    // {
    //     for (size_t j = i + 1; j < betweens.size(); j++)
    //     {
    //         for (size_t k = j + 1; k < betweens.size(); k++)
    //         {
    //             Coll left1 = get<1>(betweens[i]);
    //             Coll middle1 = get<1>(betweens[j]);
    //             Coll right1 = get<1>(betweens[k]);
    //             Coll left2 = left1.reverse();
    //             Coll middle2 = middle1.reverse();
    //             Coll right2 = right1.reverse();
    //             Pappus p1(left1, middle1, right1);
    //             Pappus p2(left1, middle1, right2);
    //             Pappus p3(left1, middle2, right1);
    //             Pappus p4(left1, middle2, right2);
    //             Pappus p5(left2, middle1, right1);
    //             Pappus p6(left2, middle1, right2);
    //             Pappus p7(left2, middle2, right1);
    //             Pappus p8(left2, middle2, right2);
    //             if (p1.check_numerically())
    //             {
    //                 on_pappus(p1);
    //             }
    //             if (p2.check_numerically())
    //             {
    //                 on_pappus(p2);
    //             }
    //             if (p3.check_numerically())
    //             {
    //                 on_pappus(p3);
    //             }
    //             if (p4.check_numerically())
    //             {
    //                 on_pappus(p4);
    //             }
    //             if (p5.check_numerically())
    //             {
    //                 on_pappus(p5);
    //             }
    //             if (p6.check_numerically())
    //             {
    //                 on_pappus(p6);
    //             }
    //             if (p7.check_numerically())
    //             {
    //                 on_pappus(p7);
    //             }
    //             if (p8.check_numerically())
    //             {
    //                 on_pappus(p8);
    //             }
    //         }
    //     }
    // }

    sort(betweens.begin(), betweens.end(),
         [](const item_type &a, const item_type &b)
         {
             return get<0>(a) < get<0>(b);
         });

    for (size_t i = 0; i < betweens.size(); i++)
    {
        const auto &curr = betweens[i];
        on_between(get<1>(curr));
        if (Numerical::close_enough(get<0>(curr), 0.5))
        {
            auto base = get<1>(curr);
            on_midpoint(Midp(base.b(), base.a(), base.c()));
        }
    }

    vector<item_type> bucket;
    bucket.push_back(betweens[0]);

    for (size_t i = 1; i < betweens.size(); i++)
    {
        const auto &prev = bucket.back();
        const auto &curr = betweens[i];
        if (Numerical::close_enough(get<0>(prev), get<0>(curr)))
        {
            bucket.push_back(curr);
        }
        else
        {
            if (bucket.size() > 1)
            {
                for (size_t left = 0; left < bucket.size(); left++)
                {
                    for (size_t right = left + 1; right < bucket.size(); right++)
                    {
                        on_eqratio(get<1>(bucket[left]), get<1>(bucket[right]));
                    }
                }
            }
            bucket.clear();
            bucket.push_back(curr);
        }
    }

    if (bucket.size() > 1)
    {
        for (size_t left = 0; left < bucket.size(); left++)
        {
            for (size_t right = left + 1; right < bucket.size(); right++)
            {
                on_eqratio(get<1>(bucket[left]), get<1>(bucket[right]));
            }
        }
    }
}

vector<tuple<double, Angle>> Matcher::all_angles()
{
    vector<tuple<double, Angle>> res;
    const size_t num_pts = _problem->num_points();
    res.reserve(num_pts * (num_pts - 1) * (num_pts - 2));
    for (const auto &left : _problem->points())
    {
        for (const auto &vertex : _problem->points())
        {
            for (const auto &right : _problem->points())
            {
                Angle const ang(left, vertex, right);
                if (ang.check_nondegen())
                {
                    res.emplace_back(ang.angle(), ang);
                }
            }
        }
    }
    return res;
}

void Matcher::on_cyclic(const Cyclic &cyclic)
{
    for (const auto &rotated : cyclic.permutation())
    {
        insert_theorem(Theorem::cyclic_of_equal_angles(rotated));
        insert_theorem(Theorem::cyclic_properties(cyclic));
    }
}

void Matcher::on_bisector(const Point &pt, const Angle &ang)
{
    insert_theorem(Theorem::triangle_bisector_of_eqratio(pt, ang));
    insert_theorem(Theorem::triangle_bisector_of_equal_angles(pt, ang));
    insert_theorem(Theorem::incenter(pt, ang));
}

void Matcher::on_eqangle(const Angle &left, const Angle &right)
{
    // _stmts.push_back(make_unique<EqAngle>(left, right));
    // ∠ABD = ∠ACD
    if (left.left() == right.left() && left.right() == right.right() && left.left() < left.right())
    {
        on_cyclic({left.vertex(), right.vertex(), left.left(), left.right()});
    }

    // ∠ABC = ∠CBD, A ≠ D
    if (left.vertex() == right.vertex())
    {
        if (left.right() == right.left() && left.left() < right.right())
        {
            on_bisector(left.right(), {left.left(), left.vertex(), right.right()});
        }
        else if (left.left() == right.right() && right.left() < left.right())
        {
            on_bisector(left.left(), {right.left(), left.vertex(), left.right()});
        }
    }
}

void Matcher::match_equal_angles()
{
    using item_type = tuple<double, Angle>;
    vector<item_type> angles = all_angles();

    if (angles.empty())
    {
        return;
    }

    sort(angles.begin(), angles.end(),
         [](const item_type &a, const item_type &b)
         {
             return get<0>(a) < get<0>(b);
         });

    // --- 新增：打印排序后的所有角度 ---
    // cout << "排序后的角度: ";
    // for (const auto& item : angles) {
    //     cout << get<1>(item) << ": " << get<0>(item) << endl;
    // }
    // cout << endl;
    // ----------------------------
    
    size_t hi = 0;
    for (size_t i = 0; i < angles.size(); i++)
                {
        if (hi < i + 1)
        {
            hi = i + 1;
        }
        while (hi < angles.size() &&
               Numerical::close_enough(get<0>(angles[i]), get<0>(angles[hi])))
    {
            hi++;
        }
        for (size_t j = i + 1; j < hi; j++)
        {
            on_eqangle(get<1>(angles[i]), get<1>(angles[j]));
        }
    }
}

void Matcher::on_circumcenter(const CircumCenter &circumcenter)
{
    insert_theorem(Theorem::cong_of_circumcenter(circumcenter));
    insert_theorem(Theorem::circumcenter_of_cong(circumcenter));
}

void Matcher::on_quadrangle_circumcenter(const Point &center, const Cyclic &cyc)
{
    insert_theorem(Theorem::cong_of_circumcenter_of_cyclic({center, Triangle(cyc.a(), cyc.b(), cyc.c())}, cyc.d()));
    insert_theorem(Theorem::cong_of_circumcenter_of_cyclic({center, Triangle(cyc.b(), cyc.c(), cyc.d())}, cyc.a()));
    insert_theorem(Theorem::cong_of_circumcenter_of_cyclic({center, Triangle(cyc.c(), cyc.d(), cyc.a())}, cyc.b()));
    insert_theorem(Theorem::cong_of_circumcenter_of_cyclic({center, Triangle(cyc.d(), cyc.a(), cyc.b())}, cyc.c()));
    insert_theorem(Theorem::center_of_cyclic_of_cong_of_cong(cyc, center));
    insert_theorem(Theorem::center_of_cyclic_of_cong_of_cong(Cyclic(cyc.a(), cyc.c(), cyc.b(), cyc.d()), center));
    insert_theorem(Theorem::center_of_cyclic_of_cong_of_cong(Cyclic(cyc.a(), cyc.d(), cyc.b(), cyc.c()), center));
}

void Matcher::on_circle(const Point &center, const vector<pair<double, Point>> &points)
{
    size_t const size = points.size();
    for (size_t pt_a = 0; pt_a < size; pt_a++)
    {
        for (size_t pt_b = pt_a + 1; pt_b < size; pt_b++)
        {
            if (Coll(points[pt_a].second, points[pt_b].second, center).check_numerically())
            {
                for (size_t pt_c = 0; pt_c < size; pt_c++)
                {
                    if (pt_c != pt_a && pt_c != pt_b)
                    {
                        insert_theorem(Theorem::hypotenuse_is_diameter(Midp(center, points[pt_a].second, points[pt_b].second), points[pt_c].second));
                    }
                }
            }
            for (size_t pt_c = pt_b + 1; pt_c < size; pt_c++)
            {
                on_circumcenter(CircumCenter(center, Triangle(points[pt_a].second, points[pt_b].second, points[pt_c].second)));
                for (size_t pt_d = pt_c + 1; pt_d < size; pt_d++)
                {
                    on_quadrangle_circumcenter(center, {points[pt_a].second, points[pt_b].second, points[pt_c].second, points[pt_d].second});
                }
            }
            if (points[pt_a].second.is_close(points[pt_b].second))
            {
                continue;
            }
            for (auto const &pt : _problem->points())
            {
                auto sec = Secant(center, points[pt_a].second, points[pt_b].second, pt);
                if (sec.check_numerically())
                {
                    insert_theorem(Theorem::definition_of_secant(sec));
                }
            }
        }
    }
}

void Matcher::match_circles()
{
    using item_type = pair<double, Point>;
    const size_t num_pts = _problem->num_points();
    for (const Point &center : _problem->points())
    {
        vector<item_type> pts;
        pts.reserve(num_pts - 1);
        for (const Point &pt : _problem->points())
        {
            if (!center.is_close(pt))
            {
                pts.emplace_back(Dist(center, pt).to_double(), pt);
            }
        }

        sort(pts.begin(), pts.end(), [](const item_type &a, const item_type &b)
             { return a.first < b.first; });

        vector<item_type> bucket;
        bucket.push_back(pts[0]);
        for (size_t i = 1; i < pts.size(); i++)
        {
            const auto &prev = bucket.back();
            const auto &curr = pts[i];
            if (Numerical::close_enough(prev.first, curr.first))
            {
                bucket.push_back(curr);
            }
            else
            {
                if (bucket.size() > 1)
                {
                    on_circle(center, bucket);
                }
                bucket.clear();
                bucket.push_back(curr);
            }
        }

        if (bucket.size() > 1)
        {
            on_circle(center, bucket);
        }
    }
}

void Matcher::match_orthocenters()
{
    const auto &all_pts = _problem->points();
    const size_t n = all_pts.size();

    // 使用索引遍历，避免重复组合：只考虑 a < b < c < d
    for (size_t idx_d = 0; idx_d < n; idx_d++)
    {
        for (size_t idx_c = 0; idx_c < idx_d; idx_c++)
        {
            for (size_t idx_b = 0; idx_b < idx_c; idx_b++)
            {
                for (size_t idx_a = 0; idx_a < idx_b; idx_a++)
                {
                    const auto &pt_a = all_pts[idx_a];
                    const auto &pt_b = all_pts[idx_b];
                    const auto &pt_c = all_pts[idx_c];
                    const auto &pt_d = all_pts[idx_d];

                    OrthoCenter const ortho(pt_d, Triangle(pt_a, pt_b, pt_c));
                    if (ortho.check_numerically())
                    {
                        for (const auto &rotated : ortho.cyclic_rotations())
                        {
                            insert_theorem(Theorem::orthocenter(rotated));
                        }
                    }
                }
            }
        }
    }
}

void Matcher::match_perps_paras()
{
    using item_type = pair<double, Slope>;
    vector<item_type> slopes;
    const size_t num_pt = _problem->num_points();
    slopes.reserve(num_pt * (num_pt - 1) / 2);

    for (size_t pt_a = 0; pt_a < num_pt; pt_a++)
    {
        for (size_t pt_b = pt_a + 1; pt_b < num_pt; pt_b++)
        {
            Slope slope(_problem->point(pt_a), _problem->point(pt_b));
            slopes.emplace_back(slope.angle(), slope);
        }
    }

    sort(slopes.begin(), slopes.end(), [](const item_type &a, const item_type &b)
         { return a.first < b.first; });

    for (size_t i = 0; i < slopes.size(); ++i)
    {
        for (size_t j = i + 1; j < slopes.size(); ++j)
        {
            const auto &l = slopes[i];
            const auto &r = slopes[j];

            if (Numerical::close_enough(l.first, r.first))
            {
                std::vector<Point> right_points = r.second.points();
                std::vector<Point> points = l.second.points();
                points.insert(points.end(), right_points.begin(), right_points.end());
                std::set<Point> s_points(points.begin(), points.end());
                if (s_points.size() == 3)
                {
                    auto it = s_points.begin();
                    Point p1 = *it++;
                    Point p2 = *it++;
                    Point p3 = *it;
                    _stmts.push_back(std::make_unique<Coll>(p1, p2, p3));
                }
                else
                {
                    _stmts.push_back(std::make_unique<Para>(l.second, r.second));
                }
            }

            if (Numerical::close_enough(r.first - l.first, M_PI / 2.0))
            {
                _stmts.push_back(std::make_unique<Perp>(l.second, r.second));
            }
        }
    }
}

void Matcher::insert_theorem(const Theorem &thm)
{
    if (!thm.check_numerically())
    {
        // cout << "定理未通过数值检测: " << thm.name() << endl;
        // cout << "前提: " << endl;
        // for (const auto &stmt : thm.hypotheses())
        // {
        //     cout << "  " << *stmt << endl;
        // }
        // cout << "结论: " << endl;
        // for (const auto &stmt : thm.conclusions())
        // {
        //     cout << "  " << *stmt << endl;
        // }
        return;
    }
    if (!get_config(thm.rule(), false))
    {
        return;
    }
    _theorems.push_back(thm.normalize());
}

// ============================================================================
// CustomTheoremMatcher 实现 - 独立的自定义定理匹配功能
// ============================================================================

namespace
{
    // 内部工具：判断谓词是否包含尾部常量参数
    bool HasTrailingConstant(const string &pred)
    {
        return pred == "rconst" || pred == "aconst";
    }

    // 内部工具：获取谓词中“点”参数的数量
    size_t GetPointArgsCount(const Stmt &stmt)
    {
        size_t n = stmt.second.size();
        return (HasTrailingConstant(stmt.first) && n > 0) ? n - 1 : n;
    }

    // 内部工具：在 Mapping 中查找变量绑定的点索引
    int FindBinding(const Mapping &mapping, const string &var)
    {
        for (const auto &kv : mapping)
        {
            if (kv.first == var)
                return kv.second;
        }
        return -1;
    }
}

// ----------------------------------------------------------------------------
// 辅助成员函数
// ----------------------------------------------------------------------------

void CustomTheoremMatcher::DebugLog(const string &msg) const
{
    if (get_config("verbose", false))
    {
        cout << "[DEBUG] " << msg << endl;
    }
}

vector<string> CustomTheoremMatcher::collect_new_vars(const Stmt &stmt, const Mapping &current) const
{
    vector<string> new_vars;
    size_t n_point_args = GetPointArgsCount(stmt);

    for (size_t i = 0; i < n_point_args; ++i)
    {
        const string &arg = stmt.second[i];
        // 如果当前 mapping 中没有，且 new_vars 中也没加入过，则视为新变量
        if (FindBinding(current, arg) == -1 &&
            std::find(new_vars.begin(), new_vars.end(), arg) == std::end(new_vars))
        {
            new_vars.push_back(arg);
        }
    }
    return new_vars;
}

bool CustomTheoremMatcher::verify_stmt(const Stmt &stmt, const Mapping &mapping) const
{
    vector<string> real_args;
    size_t n_point_args = GetPointArgsCount(stmt);

    for (size_t i = 0; i < stmt.second.size(); ++i)
    {
        const string &arg = stmt.second[i];
        if (i < n_point_args)
        {
            int pt_idx = FindBinding(mapping, arg);
            if (pt_idx == -1)
                return false;
            real_args.push_back(_problem->point(pt_idx).name());
        }
        else
        {
            real_args.push_back(arg); // 透传常量参数
        }
    }

    try
    {
        auto s = _problem->create_statement(stmt.first, real_args);
        return s && s->check_numerically();
    }
    catch (...)
    {
        return false;
    }
}

// ----------------------------------------------------------------------------
// 核心逻辑：谓词索引构建
// ----------------------------------------------------------------------------

void CustomTheoremMatcher::build_triangle_indices(size_t n)
{
    struct TriangleInfo
    {
        double ratio1, ratio2; // 形状签名：ab/ac, ab/bc
        int a, b, c;           // 原始点索引
    };

    vector<TriangleInfo> triangles;
    const double eps = 1e-8;

    // 1. 遍历并过滤所有合法三角形
    for (int a = 0; a < n; ++a)
    {
        for (int b = 0; b < n; ++b)
        {
            if (a == b)
                continue;
            for (int c = 0; c < n; ++c)
            {
                if (c == a || c == b)
                    continue;

                auto pt_a = _problem->point(a);
                auto pt_b = _problem->point(b);
                auto pt_c = _problem->point(c);

                // 排除共线三角形
                if (Coll(pt_a, pt_b, pt_c).check_equations())
                    continue;

                double ab = Dist(pt_a, pt_b).to_double();
                double ac = Dist(pt_a, pt_c).to_double();
                double bc = Dist(pt_b, pt_c).to_double();

                // 使用 Canonical Order 过滤：ab ≤ bc ≤ ac 以去重并统一对应关系
                // 这里的 REL_TOL 建议定义在配置类中
                if (ab > (1 + 1e-6) * bc || bc > (1 + 1e-6) * ac)
                    continue;

                triangles.push_back({ab / ac, ab / bc, a, b, c});
            }
        }
    }

    // 2. 按形状签名排序
    std::sort(triangles.begin(), triangles.end(), [eps](const TriangleInfo &t1, const TriangleInfo &t2)
              {
        if (std::abs(t1.ratio1 - t2.ratio1) > eps) return t1.ratio1 < t2.ratio1;
        return t1.ratio2 < t2.ratio2; });

    // 3. 桶内配对
    auto &idx_simtri = _index["simtri"];
    auto &idx_simtrir = _index["simtrir"];

    for (size_t i = 0; i < triangles.size(); ++i)
    {
        for (size_t j = i + 1; j < triangles.size(); ++j)
        {
            // 检查形状是否相同（是否在同一个桶）
            if (std::abs(triangles[i].ratio1 - triangles[j].ratio1) > eps ||
                std::abs(triangles[i].ratio2 - triangles[j].ratio2) > eps)
            {
                break;
            }

            const auto &t1 = triangles[i];
            const auto &t2 = triangles[j];

            // 判断方向：利用面积正负判断是相似(simtri)还是反相似(simtrir)
            double area1 = Triangle(_problem->point(t1.a), _problem->point(t1.b), _problem->point(t1.c)).area();
            double area2 = Triangle(_problem->point(t2.a), _problem->point(t2.b), _problem->point(t2.c)).area();
            bool same_orientation = (area1 > 0) == (area2 > 0);

            auto &target_idx = same_orientation ? idx_simtri : idx_simtrir;

            // 注入所有可能的对应排列（共 12 种：2 个三角形交换 × 6 种顶点置换）
            // 这里封装一个 lambda 简化代码
            auto push_all_perms = [&](int a, int b, int c, int d, int e, int f)
            {
                target_idx.push_back({a, b, c, d, e, f});
                target_idx.push_back({b, c, a, e, f, d});
                target_idx.push_back({c, a, b, f, d, e});
                target_idx.push_back({a, c, b, d, f, e});
                target_idx.push_back({b, a, c, e, d, f});
                target_idx.push_back({c, b, a, f, e, d});
            };

            push_all_perms(t1.a, t1.b, t1.c, t2.a, t2.b, t2.c);
            push_all_perms(t2.a, t2.b, t2.c, t1.a, t1.b, t1.c);
        }
    }
}

void CustomTheoremMatcher::build_predicate_index()
{
    auto t_total = chrono::steady_clock::now();
    const size_t n = _problem->num_points();

    // 辅助检查函数
    auto quick_check = [&](const string &pred, const vector<int> &p_indices)
    {
        vector<string> names;
        for (int i : p_indices)
            names.push_back(_problem->point(i).name());
        try
        {
            auto s = _problem->create_statement(pred, names);
            return s && s->check_numerically();
        }
        catch (...)
        {
            return false;
        }
    };

    // 1. 处理简单谓词 (midp, coll, cong, para, perp)
    auto add_simple_indices = [&](const string &pred, int arity)
    {
        auto &idx = _index[pred];
        // 这里可以根据 arity 使用通用的组合枚举逻辑，为了性能此处保持展开
        if (arity == 3)
        {
            for (int a = 0; a < n; ++a)
                for (int b = 0; b < n; ++b)
                {
                    if (a == b)
                        continue;
                    for (int c = 0; c < n; ++c)
                    {
                        if (c == a || c == b)
                            continue;
                        if (quick_check(pred, {a, b, c}))
                            idx.push_back({a, b, c});
                    }
                }
        }
        else if (arity == 4)
        {
            for (int a = 0; a < n; ++a)
                for (int b = 0; b < n; ++b)
                {
                    if (a == b)
                        continue;
                    for (int c = 0; c < n; ++c)
                        for (int d = 0; d < n; ++d)
                        {
                            if (c == d)
                                continue;
                            if (quick_check(pred, {a, b, c, d}))
                                idx.push_back({a, b, c, d});
                        }
                }
        }
    };

    for (auto &p : {make_pair("midp", 3), {"coll", 3}, {"cong", 4}, {"para", 4}, {"perp", 4}})
    {
        add_simple_indices(p.first, p.second);
    }

    // 2. 处理三角形相似 (simtri/simtrir) - 保持原有形状签名算法，但逻辑更紧凑
    build_triangle_indices(n);

    auto ms = chrono::duration_cast<chrono::milliseconds>(chrono::steady_clock::now() - t_total).count();
    DebugLog("Predicate cache built in " + to_string(ms) + "ms");
}

// ----------------------------------------------------------------------------
// 核心逻辑：回溯匹配
// ----------------------------------------------------------------------------

void CustomTheoremMatcher::enumerate_brute_force(
    const vector<Stmt> &stmts,
    size_t stmt_idx,
    const vector<string> &new_vars,
    Mapping &current,
    vector<bool> &used,
    vector<Mapping> &results) const
{
    const size_t n_pts = _problem->num_points();
    const size_t n_vars = new_vars.size();

    // 内部递归 Lambda 函数用于生成笛卡尔积
    std::function<void(size_t)> generate_combinations = [&](size_t v_idx)
    {
        // 所有新变量都已绑定
        if (v_idx == n_vars)
        {
            if (verify_stmt(stmts[stmt_idx], current))
            {
                // 当前谓词数值校验通过，进入下一条 Stmt 的匹配
                backtrack(stmts, stmt_idx + 1, current, used, results);
            }
            return;
        }

        // 为第 v_idx 个新变量尝试绑定每一个点
        for (size_t p = 0; p < n_pts; ++p)
        {
            if (used[p]) continue;
            current.push_back({new_vars[v_idx], (int)p});
            used[p] = true;
            generate_combinations(v_idx + 1);
            used[p] = false;
            current.pop_back();
        }
    };

    generate_combinations(0);
}

void CustomTheoremMatcher::backtrack(const vector<Stmt> &stmts, size_t stmt_idx,
                                     Mapping &current, vector<bool> &used,
                                     vector<Mapping> &results) const
{
    if (stmt_idx == stmts.size())
    {
        results.push_back(current);
        return;
    }

    const auto &stmt = stmts[stmt_idx];
    auto new_vars = collect_new_vars(stmt, current);

    // 情况 A：没有新变量，直接验证当前谓词
    if (new_vars.empty())
    {
        if (verify_stmt(stmt, current))
        {
            backtrack(stmts, stmt_idx + 1, current, used, results);
        }
        return;
    }

    // 情况 B：利用预计算索引快速匹配
    if (auto it = _index.find(stmt.first); it != _index.end())
    {
        for (const auto &combo : it->second)
        {
            size_t added_count = 0;
            bool conflict = false;

            for (size_t i = 0; i < stmt.second.size(); ++i)
            {
                int bound_val = FindBinding(current, stmt.second[i]);
                if (bound_val != -1)
                {
                    if (bound_val != combo[i])
                    {
                        conflict = true;
                        break;
                    }
                }
                else
                {
                    if (used[combo[i]])
                    {
                        conflict = true;
                        break;
                    }
                    current.push_back({stmt.second[i], combo[i]});
                    used[combo[i]] = true;
                    added_count++;
                }
            }

            if (!conflict)
                backtrack(stmts, stmt_idx + 1, current, used, results);

            // 回溯清理
            while (added_count--)
            {
                used[current.back().second] = false;
                current.pop_back();
            }
        }
    }
    // 情况 C：暴力枚举（仅针对无索引谓词）
    else
    {
        enumerate_brute_force(stmts, stmt_idx, new_vars, current, used, results);
    }
}

void CustomTheoremMatcher::match_rule(const CustomRule &rule)
{
    // 1. 准备并排序前提 (约束强的优先)
    vector<Stmt> sorted_stmts = rule.premises;
    sorted_stmts.insert(sorted_stmts.end(), rule.conclusions.begin(), rule.conclusions.end());

    std::sort(sorted_stmts.begin(), sorted_stmts.end(), [this](const Stmt &a, const Stmt &b)
              {
        auto it_a = _index.find(a.first), it_b = _index.find(b.first);
        size_t size_a = (it_a != _index.end()) ? it_a->second.size() : 999999;
        size_t size_b = (it_b != _index.end()) ? it_b->second.size() : 999999;
        return size_a < size_b; });

    // 2. 执行匹配
    Mapping current;
    vector<bool> used(_problem->num_points(), false);
    vector<Mapping> raw_results;
    backtrack(sorted_stmts, 0, current, used, raw_results);

    // 3. 结果转换与去重
    std::set<map<string, int>> unique_mappings;
    for (auto &m : raw_results)
    {
        map<string, int> m_map(m.begin(), m.end());
        if (!unique_mappings.insert(m_map).second)
            continue;

        Theorem thm(rule.name, rule.rule);
        auto fill_thm = [&](const vector<Stmt> &source, bool is_hypo)
        {
            for (const auto &s_stmt : source)
            {
                vector<string> args;
                for (const auto &arg : s_stmt.second)
                {
                    auto it = m_map.find(arg);
                    args.push_back(it != m_map.end() ? _problem->point(it->second).name() : arg);
                }
                auto res_stmt = _problem->create_statement(s_stmt.first, args);
                if (res_stmt)
                {
                    is_hypo ? thm.add_hypothesis(move(res_stmt)) : thm.add_conclusion(move(res_stmt));
                }
            }
        };

        fill_thm(rule.premises, true);
        fill_thm(rule.conclusions, false);

        if (thm.check_numerically())
        {
            _theorems.push_back(thm.normalize());
        }
    }
}

CustomTheoremMatcher::CustomTheoremMatcher(Problem *prob, const vector<CustomRule> &rules,
                                           const map<string, bool> &config)
    : _problem(prob), _config(config)
{
    // 默认启用预计算索引
    bool use_cache = get_config("use_predicate_cache", true);
    if (use_cache)
        build_predicate_index();

    for (const auto &rule : rules)
    {
        match_rule(rule);
    }
}