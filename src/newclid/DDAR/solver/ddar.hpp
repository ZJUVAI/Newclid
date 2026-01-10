#ifndef DDAR_HPP
#define DDAR_HPP

#include <vector>
#include <map>
#include <string>
#include <memory>
#include "problem.hpp"
#include "ar/linear_system.hpp"
#include "ar/reduced_equation.hpp"
#include "typedef.hpp"
#include "theorem.hpp"
#include "solver/application.hpp"
#include "solver/proof.hpp"
#include "solver/object_table.hpp"

class DDARSolver
{
private:
    Problem *_problem;

    size_t _level{0};

    std::vector<Application> _applications;

    std::map<std::string, std::unique_ptr<Proof>> _statement_proofs;

    std::vector<Proof *> _goals;

    std::vector<Proof *> _ars;

    std::vector<Proof *> _checked_statements;

    bool _solved{false};

    bool _log_enabled;
    bool _exp_enabled;

    LinearSystem _system_slope;
    LinearSystem _system_dist;
    LinearSystem _system_distlog;

    using eqns_map_type = std::unordered_map<Equation, ReducedEquation>;

    eqns_map_type _equations_slope;
    eqns_map_type _equations_dist;
    eqns_map_type _equations_distlog;

public:
    bool run_level(const Point &max_pt);

    bool run(size_t max_levels);

    size_t get_level() const { return _level; }

    bool is_solved() const { return _solved; }

    Proof *insert_statement(const std::unique_ptr<Statement> &p);

    const std::vector<Application> &applications() const { return _applications; }

    size_t num_applications() const;

    size_t push_established_statement(Proof *pf);

    DDARSolver(Problem *problem, bool log_enabled = false, bool exp_enabled = false);

    void advance_theorem(size_t index);

    void insert_application(Theorem thm);

    static bool establish_statement(Proof *pf, size_t thm_id);

    void add_established_equations(Proof *pf);

    void print_equations() const;

    std::vector<std::tuple<std::vector<std::string>, std::vector<std::vector<std::string>>, std::string>> dependency_graph() const;

    std::vector<ReducedEquation *> insert_equation(const std::unique_ptr<Statement> &pf, std::string type);
};

#endif // DDAR_HPP