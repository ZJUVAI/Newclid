#ifndef DDAR_HPP
#define DDAR_HPP

#include <vector>
#include <map>
#include <string>
#include "problem.hpp"
#include "ar/linear_system.hpp"
#include "ar/reduced_equation.hpp"
#include "typedef.hpp"
#include "theorem.hpp"
#include "solver/application.hpp"

class Proof;

class DDARSolver
{
private:
    Problem *_problem;

    size_t _level{0};

    std::vector<Application> _applications;

    std::map<std::string, Proof *> _statement_proofs;

    std::vector<Proof *> _goals;

    std::vector<const Proof *> _checked_statements;

    bool _solved{false};

    LinearSystem<Dist> _dist_system;

    LinearSystem<Slope> _slope_system;

    LinearSystem<DistLog> _distlog_system;

    template <typename VarT>
    using eqns_map_type = std::unordered_map<Equation<VarT>, ReducedEquation<VarT>>;

    eqns_map_type<Dist> _dist_equations;

    eqns_map_type<Slope> _slope_equations;

    eqns_map_type<DistLog> _distlog_equations;

    std::vector<std::tuple<double, Angle>> _angles;

    std::vector<std::tuple<double, Coll>> _ratios;

public:
    bool run_level(const Point &max_pt);

    bool run(size_t max_levels);

    size_t get_level() const { return _level; }

    bool is_solved() const { return _solved; }

    Proof *insert_statement(const std::unique_ptr<Statement> &p);

    const std::vector<Application> &applications() const { return _applications; }

    size_t num_applications() const;

    size_t push_established_statement(const Proof *pf);

    DDARSolver(Problem *problem);

    void advance_theorem(size_t index);

    void insert_application(Theorem thm);

    static bool establish_statement(Proof *pf, size_t thm_id);

    void add_established_equations(Proof *pf);

    std::vector<std::tuple<std::vector<std::string>, std::vector<std::vector<std::string>>, std::string>> dependency_graph() const;

    template <typename VarT>
    std::pair<Rational, ReducedEquation<VarT> *> insert_equation(const std::unique_ptr<Statement> &pf);
};

#endif // DDAR_HPP