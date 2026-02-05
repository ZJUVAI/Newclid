"""
Standalone test script for generation_new modules.

This script tests the refactored modules without requiring
the full newclid package dependencies.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, '/root/autodl-fs/projects/GenesisGeo/src')


def test_primitives():
    """Test primitives module."""
    print("\n" + "="*60)
    print("Testing primitives module...")
    print("="*60)

    from newclid.generation_new.auxiliary import (
        TOLERANCE, ROUND_DECIMALS, round_coord, normalize_direction
    )

    # Test round_coord
    coord = (1.123456789012345, 2.987654321098765)
    result = round_coord(coord)
    assert result == (1.123456789, 2.987654321), f"Expected (1.123456789, 2.987654321), got {result}"
    print("✓ round_coord test passed")

    # Test normalize_direction
    dx, dy = normalize_direction(3.0, 4.0)
    norm = (dx**2 + dy**2) ** 0.5
    assert abs(norm - 1.0) < TOLERANCE, f"Expected norm=1.0, got {norm}"
    print("✓ normalize_direction test passed")

    # Test zero vector
    dx, dy = normalize_direction(0.0, 0.0)
    assert dx == 0.0 and dy == 0.0, f"Expected (0, 0), got ({dx}, {dy})"
    print("✓ zero vector test passed")

    print("\n✅ All primitives tests passed!")


def test_distance():
    """Test distance module."""
    print("\n" + "="*60)
    print("Testing distance module...")
    print("="*60)

    from newclid.generation_new.auxiliary import is_point_too_close, is_point_too_far

    # Test is_point_too_close
    existing_coords = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]

    # Point too close to (0, 0)
    new_coords = [(0.01, 0.01)]
    result = is_point_too_close(new_coords, existing_coords, tol=0.1)
    assert result is True, "Expected True for point too close"
    print("✓ is_point_too_close (close) test passed")

    # Point not too close
    new_coords = [(0.5, 0.5)]
    result = is_point_too_close(new_coords, existing_coords, tol=0.05)
    assert result is False, "Expected False for point not too close"
    print("✓ is_point_too_close (not close) test passed")

    # Test is_point_too_far
    new_coords = [(100.0, 100.0)]
    result = is_point_too_far(new_coords, existing_coords, factor=5.0)
    assert result is True, "Expected True for point too far"
    print("✓ is_point_too_far (far) test passed")

    new_coords = [(0.5, 0.5)]
    result = is_point_too_far(new_coords, existing_coords, factor=5.0)
    assert result is False, "Expected False for point not too far"
    print("✓ is_point_too_far (not far) test passed")

    print("\n✅ All distance tests passed!")


def test_point_naming():
    """Test point_naming module."""
    print("\n" + "="*60)
    print("Testing point_naming module...")
    print("="*60)

    from newclid.generation_new.point_naming import PointNaming

    # Test initialization
    gen = PointNaming(max_points=100)
    assert gen.max_points == 100, "Expected max_points=100"
    assert gen.defined_points == [], "Expected empty defined_points"
    print("✓ initialization test passed")

    # Test single letter names
    assert gen.get_point_name(0) == 'a', "Expected 'a'"
    assert gen.get_point_name(25) == 'z', "Expected 'z'"
    print("✓ single letter names test passed")

    # Test names with numbers
    assert gen.get_point_name(26) == 'a0', "Expected 'a0'"
    assert gen.get_point_name(52) == 'a1', "Expected 'a1'"
    print("✓ names with numbers test passed")

    # Test prefetch
    points = gen.prefetch_points(3)
    assert points == ['a', 'b', 'c'], f"Expected ['a', 'b', 'c'], got {points}"
    print("✓ prefetch test passed")

    # Test define
    gen.define_points(points)
    assert gen.defined_points == ['a', 'b', 'c'], "Expected ['a', 'b', 'c']"
    print("✓ define test passed")

    # Test max points limit
    gen2 = PointNaming(max_points=2)
    try:
        gen2.prefetch_points(3)
        assert False, "Should have raised ValueError"
    except ValueError:
        print("✓ max points limit test passed")

    print("\n✅ All point_naming tests passed!")


def test_line_utils():
    """Test line_utils module."""
    print("\n" + "="*60)
    print("Testing line_utils module...")
    print("="*60)

    from newclid.generation_new.auxiliary import extract_points, lines, check_on_line

    # Test extract_points
    text = "a@0.0_0.0 b@1.0_0.0 c@0.0_1.0"
    point_names, coords = extract_points(text)
    assert point_names == ['a', 'b', 'c'], f"Expected ['a', 'b', 'c'], got {point_names}"
    assert coords['a'] == (0.0, 0.0), "Expected a at (0, 0)"
    print("✓ extract_points test passed")

    # Test lines - collinear points
    point_names = ['a', 'b', 'c']
    coords = {'a': (0.0, 0.0), 'b': (1.0, 0.0), 'c': (2.0, 0.0)}
    result = lines(point_names, coords)
    assert len(result) == 1, f"Expected 1 line, got {len(result)}"
    assert set(result[0]) == {'a', 'b', 'c'}, "Expected line with a, b, c"
    print("✓ lines (collinear) test passed")

    # Test lines - triangle
    coords = {'a': (0.0, 0.0), 'b': (1.0, 0.0), 'c': (0.0, 1.0)}
    result = lines(point_names, coords)
    assert len(result) == 3, f"Expected 3 lines, got {len(result)}"
    print("✓ lines (triangle) test passed")

    # Test check_on_line
    coords = {'a': (0.0, 0.0), 'b': (2.0, 0.0)}
    all_lines = [('a', 'b')]
    assert check_on_line((1.0, 0.0), all_lines, coords) is True, "Expected True"
    assert check_on_line((1.0, 1.0), all_lines, coords) is False, "Expected False"
    print("✓ check_on_line test passed")

    print("\n✅ All line_utils tests passed!")


def test_construction_types():
    """Test construction_types module."""
    print("\n" + "="*60)
    print("Testing construction_types module...")
    print("="*60)

    from newclid.generation_new.constructions import BASIC, BASIC_FREE, INTERSECT, OTHER

    assert 'triangle' in BASIC, "Expected 'triangle' in BASIC"
    assert 'free' in BASIC_FREE, "Expected 'free' in BASIC_FREE"
    assert 'angle_bisector' in INTERSECT, "Expected 'angle_bisector' in INTERSECT"
    assert 'midpoint' in OTHER, "Expected 'midpoint' in OTHER"
    print("✓ construction types test passed")

    print("\n✅ All construction_types tests passed!")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("GENERATION_NEW MODULE TEST SUITE")
    print("="*60)

    try:
        test_primitives()
        test_distance()
        test_point_naming()
        test_line_utils()
        test_construction_types()

        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nSummary:")
        print("  - primitives: 3/3 tests passed")
        print("  - distance: 4/4 tests passed")
        print("  - point_naming: 6/6 tests passed")
        print("  - line_utils: 4/4 tests passed")
        print("  - construction_types: 1/1 test passed")
        print("\n  Total: 18/18 tests passed ✓")

    except Exception as e:
        print(f"\n❌ Test failed with error:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
