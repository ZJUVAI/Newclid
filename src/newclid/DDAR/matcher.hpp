#ifndef MATCHER_HPP
#define MATCHER_HPP

#include <vector>
#include "type/triangle.hpp"
#include "theorem.hpp"
#include "problem.hpp"

#define REL_TOL 0.001
#define EPS 1E-12

// 在构建对象时完成匹配，匹配结果存放在_theorems中
class Matcher
{
private:
    Problem *_problem;

    std::vector<Theorem> _theorems;

    std::vector<std::unique_ptr<Statement>> _stmts;

    void match_similar_triangles();

    void match_between();

    void match_equal_angles();

    void match_circles();

    void match_orthocenters();

    void match_perps_paras();

    std::vector<std::tuple<double, double, Triangle>> all_triangles();

    std::vector<std::tuple<double, Coll>> all_betweens();

    std::vector<std::pair<Point, Point>> all_eqpoints();

    std::vector<std::tuple<double, Angle>> all_angles();

    void on_similar_triangles(const SimilarTriangles &simtri);

    void on_pappus(const Pappus &pappus);

    void on_between(const Coll &coll);

    void on_midpoint(const Midp &midp);

    void on_eqratio(const Coll &left, const Coll &right);

    void on_cyclic(const Cyclic &cyclic);

    void on_bisector(const Point &pt, const Angle &ang);

    void on_eqangle(const Angle &left, const Angle &right);

    void on_circle(const Point &center, const std::vector<std::pair<double, Point>> &points);

    void on_circumcenter(const CircumCenter &circumcenter);

    void on_quadrangle_circumcenter(const Point &center, const Cyclic &cyc);

    void insert_theorem(const Theorem &thm);

public:
    Matcher(Problem *prob);

    const std::vector<Theorem> &theorems() const { return _theorems; }

    const std::vector<std::unique_ptr<Statement>> &stmts() const { return _stmts; }
};

#endif // MATCHER_HPP