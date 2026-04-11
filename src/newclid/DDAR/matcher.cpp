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
#include <tuple>
#include <vector>
#include <set>
#include <map>
#include <unordered_map>
#include <functional>

using namespace std;

Matcher::Matcher(Problem *prob) : _problem(prob)
{
    match_similar_triangles();
    match_between();
    match_equal_angles();
    match_circles();
    match_orthocenters();
    // match_perps_paras();
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
        insert_theorem(Theorem::congruent_triangles_of_cong(congtri));
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
             if (!Numerical::close_enough(get<0>(a), get<0>(b)))
             {
                 return get<0>(a) < get<0>(b);
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
        #ifndef DDAR_WEAK
            insert_theorem(Theorem::pappus(rotated));
        #endif
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
        #ifndef DDAR_WEAK
            insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(left, right));
            insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(Coll(left.a(), left.c(), left.b()), Coll(right.a(), right.c(), right.b())));
            insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(left, right));
            insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(Coll(left.a(), left.c(), left.b()), Coll(right.a(), right.c(), right.b())));
        #endif
    }
    else if (left.b() == right.b())
    {
        #ifndef DDAR_WEAK
            insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(Coll(left.b(), left.a(), left.c()), Coll(right.b(), right.a(), right.c())));
            insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(Coll(left.b(), left.c(), left.a()), Coll(right.b(), right.c(), right.a())));
            insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(Coll(left.b(), left.a(), left.c()), Coll(right.b(), right.a(), right.c())));
            insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(Coll(left.b(), left.c(), left.a()), Coll(right.b(), right.c(), right.a())));
        #endif
    }
    else if (left.c() == right.c())
    {
        #ifndef DDAR_WEAK
            insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(Coll(left.c(), left.a(), left.b()), Coll(right.c(), right.a(), right.b())));
            insert_theorem(Theorem::thales_para_of_eqratio_with_common_point(Coll(left.c(), left.b(), left.a()), Coll(right.c(), right.b(), right.a())));
            insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(Coll(left.c(), left.a(), left.b()), Coll(right.c(), right.a(), right.b())));
            insert_theorem(Theorem::thales_eqratio_of_para_with_common_point(Coll(left.c(), left.b(), left.a()), Coll(right.c(), right.b(), right.a())));
        #endif
    }

    Thales const thales(left, right);
    if (!thales.check_numerically())
    {
        return;
    }
    for (const auto &rotated : thales.permutations())
    {
        #ifndef DDAR_WEAK
            insert_theorem(Theorem::thales_para_of_eqratio(rotated));
        #endif
    }
    #ifndef DDAR_WEAK
        insert_theorem(Theorem::thales_eqratio_of_para(thales));
    #endif
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
    #ifndef DDAR_WEAK
        insert_theorem(Theorem::triangle_bisector_of_eqratio(pt, ang));
        insert_theorem(Theorem::triangle_bisector_of_equal_angles(pt, ang));
        insert_theorem(Theorem::incenter(pt, ang));
    #endif
}

void Matcher::on_eqangle(const Angle &left, const Angle &right)
{
    // _stmts.push_back(make_unique<EqAngle>(left, right));
    // ∠ABD = ∠ACD
    if (left.left() == right.left() && left.right() == right.right() && left.left() < left.right() && left.vertex() < left.left() && right.vertex() < right.left())
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

    vector<item_type> bucket;
    bucket.push_back(angles[0]);
    for (size_t i = 1; i < angles.size(); i++)
    {
        const auto &prev = bucket.back();
        const auto &curr = angles[i];
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
                        on_eqangle(get<1>(bucket[left]), get<1>(bucket[right]));
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
                on_eqangle(get<1>(bucket[left]), get<1>(bucket[right]));
            }
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
    #ifndef DDAR_WEAK
        insert_theorem(Theorem::center_of_cyclic_of_cong_of_cong(cyc, center));
        insert_theorem(Theorem::center_of_cyclic_of_cong_of_cong(Cyclic(cyc.a(), cyc.c(), cyc.b(), cyc.d()), center));
        insert_theorem(Theorem::center_of_cyclic_of_cong_of_cong(Cyclic(cyc.a(), cyc.d(), cyc.b(), cyc.c()), center));
    #endif
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
                        #ifndef DDAR_WEAK
                            insert_theorem(Theorem::hypotenuse_is_diameter(Midp(center, points[pt_a].second, points[pt_b].second), points[pt_c].second));
                        #endif
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
                            #ifndef DDAR_WEAK
                                insert_theorem(Theorem::orthocenter(rotated));
                            #endif
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
        return;
    }
    _theorems.push_back(thm.normalize());
}

// ============================================================================
// CustomTheoremMatcher 实现 - 独立的自定义定理匹配功能
// ============================================================================

// 收集 stmt 参数中尚未在 mapping 中出现的新点代号（去重，保序）
static vector<string> new_vars(const Stmt &stmt, const Mapping &mapping)
{
    vector<string> vars;
    for (const auto &arg : stmt.second)
    {
        bool known = false;
        for (const auto &kv : mapping)
            if (kv.first == arg)
            {
                known = true;
                break;
            }
        if (!known)
        {
            bool dup = false;
            for (const auto &v : vars)
                if (v == arg)
                {
                    dup = true;
                    break;
                }
            if (!dup)
                vars.push_back(arg);
        }
    }
    return vars;
}

// 将 mapping 中的代号替换为实际点名，构造 Statement 并做数值检测
static bool check_stmt_numerically(const Stmt &stmt, const Mapping &mapping, Problem *problem)
{
    vector<string> real_args;
    for (const auto &arg : stmt.second)
    {
        bool found = false;
        for (const auto &kv : mapping)
        {
            if (kv.first == arg)
            {
                real_args.push_back(problem->point(kv.second).name());
                found = true;
                break;
            }
        }
        if (!found)
            return false;
    }
    try
    {
        auto s = problem->create_statement(stmt.first, real_args);
        if (!s)
            return false;
        return s->check_numerically();
    }
    catch (...)
    {
        return false;
    }
}

void CustomTheoremMatcher::backtrack(
    const vector<Stmt> &stmts,
    size_t idx,
    Mapping &current,
    vector<Mapping> &out) const
{
    if (idx == stmts.size())
    {
        out.push_back(current);
        return;
    }

    const Stmt &stmt = stmts[idx];
    vector<string> vars = new_vars(stmt, current);

    if (vars.empty())
    {
        if (check_stmt_numerically(stmt, current, _problem))
            backtrack(stmts, idx + 1, current, out);
        return;
    }

    size_t n_pts = _problem->num_points();
    size_t n_vars = vars.size();
    vector<size_t> indices(n_vars, 0);

    while (true)
    {
        for (size_t i = 0; i < n_vars; i++)
            current.push_back({vars[i], (int)indices[i]});

        if (check_stmt_numerically(stmt, current, _problem))
            backtrack(stmts, idx + 1, current, out);

        for (size_t i = 0; i < n_vars; i++)
            current.pop_back();

        // 进位
        size_t carry = n_vars;
        while (carry > 0)
        {
            carry--;
            indices[carry]++;
            if (indices[carry] < n_pts)
                break;
            indices[carry] = 0;
            if (carry == 0)
                goto done;
        }
    }
done:;
}

void CustomTheoremMatcher::match_rule(const CustomRule &rule)
{
    // 按新变量数量升序排列前提，优先匹配约束强的
    vector<Stmt> sorted_premises = rule.premises;
    sort(sorted_premises.begin(), sorted_premises.end(), [](const Stmt &a, const Stmt &b)
         {
        set<string> sa(a.second.begin(), a.second.end());
        set<string> sb(b.second.begin(), b.second.end());
        return sa.size() < sb.size(); });

    Mapping current;
    vector<Mapping> mappings;
    backtrack(sorted_premises, 0, current, mappings);

    // 去重
    set<map<string, int>> seen;
    for (auto &mapping : mappings)
    {
        map<string, int> mm(mapping.begin(), mapping.end());
        if (!seen.insert(mm).second)
            continue;

        Theorem thm(rule.name, rule.rule);

        // 添加前提
        for (const auto &stmt : rule.premises)
        {
            vector<string> real_args;
            for (const auto &arg : stmt.second)
            {
                auto it = mm.find(arg);
                if (it != mm.end())
                    real_args.push_back(_problem->point(it->second).name());
                else
                    real_args.push_back(arg);
            }
            try
            {
                auto s = _problem->create_statement(stmt.first, real_args);
                if (s)
                    thm.add_hypothesis(move(s));
            }
            catch (...)
            {
            }
        }

        // 添加结论
        for (const auto &stmt : rule.conclusions)
        {
            vector<string> real_args;
            for (const auto &arg : stmt.second)
            {
                auto it = mm.find(arg);
                if (it != mm.end())
                    real_args.push_back(_problem->point(it->second).name());
                else
                    real_args.push_back(arg);
            }
            try
            {
                auto s = _problem->create_statement(stmt.first, real_args);
                if (s)
                    thm.add_conclusion(move(s));
            }
            catch (...)
            {
            }
        }

        if (thm.check_numerically())
            _theorems.push_back(thm.normalize());
    }
}

CustomTheoremMatcher::CustomTheoremMatcher(Problem *prob, const vector<CustomRule> &rules)
    : _problem(prob)
{
    for (const auto &rule : rules)
    {
        match_rule(rule);
    }
}