#ifndef PROBLEM_HPP
#define PROBLEM_HPP
#include <string>
#include <vector>
#include "predicate/statement.hpp"
#include "type/point.hpp"

class Problem final
{
private:
    std::string _name;
    std::vector<std::unique_ptr<Statement>> _hypotheses;
    std::vector<std::unique_ptr<Statement>> _goals;
    std::vector<Point> _points;

public:
    Problem() = default;

    void clear();

    void add_point(const std::string &name, double x, double y);

    void set_name(const std::string &name);

    void add_hypothesis(std::unique_ptr<Statement> &&p);

    void add_goal(std::unique_ptr<Statement> &&p);

    Point &point(size_t index);

    std::vector<Point> points();

    std::string name();

    const std::vector<std::unique_ptr<Statement>> &hypotheses();

    const std::vector<std::unique_ptr<Statement>> &goals();

    size_t num_points() const;

    Point find_point(const std::string &name) const;

    void load_from_file(const std::string &filename);

    void load_from_data(const std::string name, std::vector<std::tuple<std::string, double, double>> points, std::vector<std::pair<std::string, std::vector<std::string>>> premises, std::vector<std::pair<std::string, std::vector<std::string>>> goals);

    std::unique_ptr<Statement> create_statement(const std::string &type, const std::vector<std::string> &args) const;
};

#endif // PROBLEM_HPP