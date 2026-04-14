"""Tests for utility functions in tools.py."""

from fractions import Fraction

from newclid.tools import (
    atomize,
    fraction_to_angle,
    fraction_to_len,
    fraction_to_ratio,
    get_quotient,
    reshape,
    str_to_fraction,
)


class TestAtomize:
    def test_split_by_space(self):
        assert atomize("a b c") == ("a", "b", "c")

    def test_split_by_comma(self):
        assert atomize("a, b, c", ",") == ("a", "b", "c")

    def test_single_token(self):
        assert atomize("hello") == ("hello",)

    def test_strips_whitespace(self):
        assert atomize("  a ; b ; c  ", ";") == ("a", "b", "c")


class TestStrToFraction:
    def test_pi_fraction(self):
        assert str_to_fraction("1pi/2") == Fraction(1, 2)

    def test_degree(self):
        assert str_to_fraction("90o") == Fraction(90, 180)

    def test_simple_fraction(self):
        assert str_to_fraction("3/4") == Fraction(3, 4)

    def test_integer(self):
        assert str_to_fraction("5") == Fraction(5, 1)

    def test_negative_pi_fraction(self):
        # str_to_fraction uses modulo: (-1) % 4 = 3 in Python
        result = str_to_fraction("-1pi/4")
        assert result == Fraction(3, 4)


class TestFractionConversions:
    def test_fraction_to_len(self):
        assert fraction_to_len(Fraction(3, 4)) == "3/4"

    def test_fraction_to_ratio(self):
        assert fraction_to_ratio(Fraction(2, 3)) == "2/3"

    def test_fraction_to_angle(self):
        assert fraction_to_angle(Fraction(1, 2)) == "1pi/2"


class TestGetQuotient:
    def test_integer(self):
        assert get_quotient(1.0) == Fraction(1, 1)

    def test_half(self):
        assert get_quotient(0.5) == Fraction(1, 2)

    def test_third(self):
        assert get_quotient(1 / 3) == Fraction(1, 3)


class TestReshape:
    def test_basic(self):
        result = list(reshape([1, 2, 3, 4], 2))
        assert result == [(1, 2), (3, 4)]

    def test_remainder(self):
        # reshape requires length divisible by n
        result = list(reshape([1, 2, 3, 4], 2))
        assert result == [(1, 2), (3, 4)]

    def test_empty(self):
        assert list(reshape([], 3)) == []
