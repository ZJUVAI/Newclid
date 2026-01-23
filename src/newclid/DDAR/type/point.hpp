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
    bool operator!=(const Point &other) const;
    bool operator<(const Point &other) const;
    bool operator>(const Point &other) const;
    bool operator<=(const Point &other) const;
    bool operator>=(const Point &other) const;

    static void parseName(const std::string &name,
                          std::string &prefix,
                          int &index)
    {
        size_t i = 0;
        while (i < name.size() && std::isalpha(name[i]))
            ++i;

        prefix = name.substr(0, i);

        if (i == name.size())
            index = -1; // 没有数字
        else
            index = std::stoi(name.substr(i));
    }

private:
    PointNum _num;
    std::string _name;
    std::string _prefix;
    int _index;
};

// 声明 operator<<
std::ostream &operator<<(std::ostream &os, const Point &pt);

#endif // POINT_HPP
