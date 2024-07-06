from typing import TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from geosolver.numerical.geometries import PointNum


def ang_of(tail: "PointNum", head: "PointNum") -> float:
    vector = head - tail
    arctan = np.arctan2(vector.y, vector.x) % (2 * np.pi)
    return arctan


def ang_between(tail: "PointNum", head1: "PointNum", head2: "PointNum") -> float:
    """
    the slid angle from tail->head1 to tail->head2 controlled between [-np.pi, np.pi)
    """
    ang1 = ang_of(tail, head1)
    ang2 = ang_of(tail, head2)
    diff = ang2 - ang1
    return diff % (2 * np.pi)
