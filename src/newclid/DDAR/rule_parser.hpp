#ifndef RULE_PARSER_HPP
#define RULE_PARSER_HPP

#include <string>
#include <vector>
#include <utility>
#include "theorem.hpp"
#include "problem.hpp"

/**
 * RuleParser - Parses custom rule text into Theorem objects
 *
 * Supports rule format: "premise1, premise2 => conclusion1, conclusion2"
 * Example: "cong a b c d, para a b c d => cyclic a b c d"
 */
class RuleParser
{
public:
    /**
     * Parse a single rule text into a Theorem object
     *
     * @param rule_text Rule in format "premise1, premise2 => conclusion"
     * @param rule_id Unique identifier for the rule (e.g., "r0001")
     * @param problem Problem context for creating statements
     * @return Theorem object representing the rule
     * @throws runtime_error if rule format is invalid
     */
    static Theorem parse_rule(
        const std::string& rule_text,
        const std::string& rule_id,
        Problem* problem
    );

    /**
     * Parse multiple rules in batch
     *
     * @param rules_text Vector of rule texts
     * @param problem Problem context for creating statements
     * @return Vector of Theorem objects
     */
    static std::vector<Theorem> parse_rules(
        const std::vector<std::string>& rules_text,
        Problem* problem
    );

private:
    /**
     * Split rule text into premises and conclusions
     *
     * @param rule_text Rule text to split
     * @return Pair of (premises, conclusions) as string vectors
     */
    static std::pair<std::vector<std::string>, std::vector<std::string>>
        split_rule(const std::string& rule_text);

    /**
     * Parse a single clause like "cong a b c d"
     *
     * @param clause Clause text to parse
     * @return Pair of (predicate_name, arguments)
     */
    static std::pair<std::string, std::vector<std::string>>
        parse_clause(const std::string& clause);

    /**
     * Trim whitespace from both ends of a string
     */
    static std::string trim(const std::string& str);
};

#endif // RULE_PARSER_HPP
