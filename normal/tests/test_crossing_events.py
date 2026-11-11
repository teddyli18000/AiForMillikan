import math

import pandas as pd
import pytest

from millikan_ai.normal.tracking import crossing_events


def track(ys, states=None):
    states = states or ["tracking"] * len(ys)
    return pd.DataFrame([
        {"source_frame": i, "x": 40.0 if y is not None else math.nan,
         "y": float(y) if y is not None else math.nan,
         "pred_x": 40.0, "pred_y": 50.0 if y is None else float(y),
         "detected": y is not None, "state": state,
         "blocked_by_grid": state == "missing"}
        for i, (y, state) in enumerate(zip(ys, states))
    ])


def events(ys, states=None, lines=None, fps=30):
    return crossing_events(track(ys, states), {"grid_lines_y": lines or [50]}, fps)


def test_occlusion_and_geometric_crossing_are_one_review():
    result = events([40, 44, None, 49, 51, None, 54, 56, 60],
                    ["tracking", "tracking", "missing", "reacquired", "tracking",
                     "missing", "reacquired", "tracking", "tracking"])
    assert len(result) == 1
    assert result[0]["start_frame"] == 1
    assert result[0]["end_frame"] == 7
    assert result[0]["kind"] == "grid_line_crossing"


def test_line_centre_jitter_and_exact_line_hits_count_once():
    result = events([40, 46, 50, 51, 49, 50, 52, 56, 60])
    assert len(result) == 1
    assert (result[0]["start_frame"], result[0]["end_frame"]) == (0, 7)


def test_touching_line_and_returning_without_occlusion_is_not_crossing():
    assert events([40, 47, 50, 49, 43, 40]) == []


def test_returning_after_clearing_line_is_a_separate_crossing_even_when_fast():
    result = events([40, 60, 40], fps=60)
    assert len(result) == 2
    assert [event["event_id"] for event in result] == ["crossing_001", "crossing_002"]


def test_different_lines_are_not_merged_by_time():
    result = events([40, 60, 80], lines=[50, 70], fps=60)
    assert [event["grid_line_y_px"] for event in result] == [50, 70]


def test_two_losses_during_same_line_visit_are_reviewed_together_without_crossing():
    result = events([40, 48, None, 49, 48, None, 47, 40],
                    ["tracking", "tracking", "missing", "reacquired", "tracking",
                     "missing", "reacquired", "tracking"])
    assert len(result) == 1
    assert result[0]["kind"] == "grid_crossing_or_reacquire"


def test_unfinished_line_visit_keeps_identity_review():
    result = events([40, 48, None, 49, None],
                    ["tracking", "tracking", "missing", "reacquired", "missing"])
    assert len(result) == 1
    assert result[0]["end_frame"] == 4


@pytest.mark.parametrize("lines", [[], [100]])
def test_identity_loss_away_from_grid_is_preserved(lines):
    result = crossing_events(track([10, None, 12, 14],
                                   ["tracking", "missing", "reacquired", "tracking"]),
                             {"grid_lines_y": lines}, 30)
    assert len(result) == 1
    assert result[0]["start_frame"] == 1
    assert result[0]["end_frame"] == 2


def test_empty_track_has_no_events():
    assert crossing_events(pd.DataFrame(), {"grid_lines_y": [50]}, 30) == []
