#ifndef CUSTOM_RULE_MATCHER_HPP
#define CUSTOM_RULE_MATCHER_HPP

#include <vector>
#include <map>
#include <string>
#include <set>
#include "theorem.hpp"
#include "problem.hpp"

/**
 * CustomRuleMatcher - Matches custom rules against problem points
 *
 * Takes custom rules (as Theorem objects) and finds all valid instantiations
 * by binding rule variables to concrete points from the problem.
 */
class CustomRuleMatcher
{
public:
    /**
     * Constructor
     *
     * @param problem Problem context with points and coordinates
     */
    explicit CustomRuleMatcher(Problem* problem);

    /**
     * Match custom rules and return instantiated theorems
     *
     * @param rules Vector of custom rules to match
     * @return Vector of instantiated theorems (concrete point bindings)
     */
    std::vector<Theorem> match_rules(const std::vector<Theorem>& rules);

private:
    Problem* _problem;

    /**
     * Extract all unique variable names from a rule
     *
     * @param rule Rule to extract variables from
     * @return Set of variable names
     */
    std::set<std::string> extract_variables(const Theorem& rule);

    /**
     * Find all valid bindings for a rule
     *
     * @param rule Rule to find bindings for
     * @return Vector of variable->point mappings
     */
    std::vector<std::map<std::string, Point>> find_bindings(const Theorem& rule);

    /**
     * Generate all permutations of points for variable binding
     *
     * @param variables Ordered list of variables to bind
     * @param points Available points
     * @param current_binding Current partial binding
     * @param index Current variable index
     * @param result Output vector of complete bindings
     */
    void generate_bindings(
        const std::vector<std::string>& variables,
        const std::vector<Point>& points,
        std::map<std::string, Point>& current_binding,
        size_t index,
        std::vector<std::map<std::string, Point>>& result
    );

    /**
     * Validate a binding by checking hypotheses numerically
     *
     * @param rule Rule to validate
     * @param binding Variable->point mapping
     * @return True if all hypotheses are numerically valid
     */
    bool validate_binding(
        const Theorem& rule,
        const std::map<std::string, Point>& binding
    );

    /**
     * Instantiate a rule with a concrete binding
     *
     * @param rule Rule template
     * @param binding Variable->point mapping
     * @return Instantiated theorem with concrete points
     */
    Theorem instantiate_rule(
        const Theorem& rule,
        const std::map<std::string, Point>& binding
    );

    /**
     * Replace variables in a statement with concrete points
     *
     * @param stmt Statement with variables
     * @param binding Variable->point mapping
     * @return New statement with concrete points
     */
    std::unique_ptr<Statement> instantiate_statement(
        const std::unique_ptr<Statement>& stmt,
        const std::map<std::string, Point>& binding
    );
};

#endif // CUSTOM_RULE_MATCHER_HPP
