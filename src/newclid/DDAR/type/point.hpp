#ifndef POINT_HPP
#define POINT_HPP

#include "type/pointnum.hpp"
#include "numerical.hpp"
#include <string>
#include <ostream> // 引入 std::ostream 以便声明 operator<<

// 声明类 Point
class Point
{
public:
    Point(std::string name, double x, double y); // 构造函数
    Point(std::string name, PointNum num);       // 构造函数

    std::string name() const;
    double x() const;
    double y() const;
    PointNum num() const;
    std::string to_string() const;

    bool is_close(const Point &other) const;

    bool operator==(const Point &other) const;
    bool operator<(const Point &other) const;
    bool operator>(const Point &other) const;
    bool operator<=(const Point &other) const;
    bool operator>=(const Point &other) const;

private:
    PointNum _num;
    std::string _name;
};

// 声明 operator<<
std::ostream &operator<<(std::ostream &os, const Point &pt);

#endif // POINT_HPP
