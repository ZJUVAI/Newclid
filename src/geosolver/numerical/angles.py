from typing import TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from geosolver.numerical.geometries import Point


def ang_of(tail: "Point", head: "Point") -> float:
    vector = head - tail
    arctan = np.arctan2(vector.y, vector.x) % (2 * np.pi)
    return arctan


def ang_between(tail: "Point", head1: "Point", head2: "Point") -> float:
    ang1 = ang_of(tail, head1)
    ang2 = ang_of(tail, head2)
    diff = ang1 - ang2
    # return diff % (2*np.pi)
    if diff > np.pi:
        return diff - 2 * np.pi
    if diff < -np.pi:
        return 2 * np.pi + diff
    return diff
