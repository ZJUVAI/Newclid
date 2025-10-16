#ifndef RATIONAL_HPP
#define RATIONAL_HPP

#include <iostream>
#include <stdexcept>
#include <numeric>
#include <limits>

/**
 * @brief 有理数类，支持基本的分数运算
 */
class Rational
{
private:
    long long _num; ///< 分子
    long long _den; ///< 分母（始终保持 > 0）

    void normalize(); ///< 约分并保证分母 > 0

public:
    // 构造函数
    Rational();                                                  ///< 默认 0/1
    Rational(long long num);                                     ///< 整数构造
    Rational(int num);                                           ///< 整数构造
    Rational(long long num, long long den);                      ///< 分子/分母构造
    explicit Rational(double value, long long maxDen = 1000000); ///< 从 double 构造（近似）

    // 基本方法
    long long numerator() const { return _num; }
    long long denominator() const { return _den; }
    double to_double() const { return static_cast<double>(_num) / _den; }

    // 四则运算
    Rational operator+(const Rational &rhs) const;
    Rational operator-(const Rational &rhs) const;
    Rational operator*(const Rational &rhs) const;
    Rational operator/(const Rational &rhs) const;

    Rational &operator+=(const Rational &rhs);
    Rational &operator-=(const Rational &rhs);
    Rational &operator*=(const Rational &rhs);
    Rational &operator/=(const Rational &rhs);

    // 一元运算
    Rational operator-() const { return Rational(-_num, _den); }

    // 比较运算
    bool operator==(const Rational &rhs) const;
    bool operator!=(const Rational &rhs) const { return !(*this == rhs); }
    bool operator<(const Rational &rhs) const;
    bool operator<=(const Rational &rhs) const { return *this < rhs || *this == rhs; }
    bool operator>(const Rational &rhs) const { return rhs < *this; }
    bool operator>=(const Rational &rhs) const { return !(*this < rhs); }

    // 流输出
    friend std::ostream &operator<<(std::ostream &os, const Rational &r);

    std::string to_string() const;
};

long long gcd(long long a, long long b);

#endif // RATIONAL_HPP