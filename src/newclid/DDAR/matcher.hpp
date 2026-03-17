#ifndef MATCHER_HPP
#define MATCHER_HPP

#include <vector>
#include <unordered_map>
#include <string>
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

// 自定义定理匹配器 - 独立功能，不影响原有Matcher

// Stmt: (谓词类型, [点代号列表])，例如 ("coll", ["A","B","C"])
using Stmt = std::pair<std::string, std::vector<std::string>>;

// Mapping: 定理点代号 -> Problem中点的索引
using Mapping = std::vector<std::pair<std::string, int>>;

// Rule: (前提列表, 结论列表, 定理名, 规则名)
struct CustomRule
{
    std::vector<Stmt> premises;
    std::vector<Stmt> conclusions;
    std::string name;
    std::string rule;
};

class CustomTheoremMatcher
{
private:
    Problem *_problem;
    std::vector<Theorem> _theorems;

    // 递归匹配 stmts[idx..] 在当前 mapping 下的所有合法扩展
    void backtrack(
        const std::vector<Stmt> &stmts,
        size_t idx,
        Mapping &current,
        std::vector<Mapping> &out) const;

    // 对一条 rule 的所有前提匹配，生成 Theorem 并插入 _theorems
    void match_rule(const CustomRule &rule);

public:
    // rules: 每条规则包含前提、结论、名称、规则id
    CustomTheoremMatcher(Problem *prob, const std::vector<CustomRule> &rules);

    const std::vector<Theorem> &theorems() const { return _theorems; }
};

#endif // MATCHER_HPP