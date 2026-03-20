#ifndef ROUND_HPP
#define ROUND_HPP

#include "type/rational.hpp"

/**
 * @brief Round类，维护一个在[0, 1)范围内的分数
 */
class Round
{
public:
    // 构造函数
    Round();                             ///< 默认构造，值为 0/1
    Round(long long num);                ///< 整数构造
    Round(int num);                      ///< 整数构造
    Round(long long num, long long den); ///< 分子/分母构造
    Round(Rational r);
    explicit Round(double value, long long maxDen = 1000000); ///< 从double构造

    long long numerator() const { return _num; }                          ///< 获取分子
    long long denominator() const { return _den; }                        ///< 获取分母
    double to_double() const { return static_cast<double>(_num) / _den; } ///< 转为double

    // 重新定义算术运算符，确保结果在[0, 1)范围内
    Round operator+(const Round &rhs) const;
    Round operator-(const Round &rhs) const;
    Round operator*(const Round &rhs) const;
    Round operator/(const Round &rhs) const;

    // 重新定义复合赋值运算符，确保结果在[0, 1)范围内
    Round &operator+=(const Round &rhs);
    Round &operator-=(const Round &rhs);
    Round &operator*=(const Round &rhs);
    Round &operator/=(const Round &rhs);

    // 一元运算
    Round operator-() const { return Round(-_num, _den); }

    // 比较运算
    bool operator==(const Round &rhs) const;
    bool operator!=(const Round &rhs) { return !(*this == rhs); }
    bool operator<(const Round &rhs) const;
    bool operator<=(const Round &rhs) const { return (*this < rhs) || (*this == rhs); }
    bool operator>(const Round &rhs) const { return !(*this <= rhs); }
    bool operator>=(const Round &rhs) const { return !(*this < rhs); }

    bool operator==(const Rational &rhs) const;
    bool operator!=(const Rational &rhs) { return !(*this == rhs); }

    friend std::ostream &operator<<(std::ostream &os, const Round &r);

private:
    void normalize(); ///< 归一化，使数值保持在[0, 1)之间
    long long _num;   ///< 分子
    long long _den;   ///< 分母
};

#endif // ROUND_HPP