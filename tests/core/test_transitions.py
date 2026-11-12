"""Tests for starting and ending sessions and the history invariants."""

from dataclasses import replace

import pytest

from timetracker.core.transitions import (
    close_expired_breaks,
    end_session,
    place_session,
    start_session,
    validate,
)

from .conftest import at, brk, dis, work


def test_validate_rejects_overlap():
    """Overlapping sessions are invalid."""
    with pytest.raises(ValueError, match="starts before"):
        validate((work(0, 25), work(20, 40)))


def test_validate_rejects_active_in_middle():
    """Only the last session may be active."""
    with pytest.raises(ValueError, match="still active"):
        validate((work(0, None), work(30, 40)))


def test_validate_rejects_duplicate_ids():
    """Ids must be unique."""
    with pytest.raises(ValueError, match="duplicate"):
        validate((work(0, 10, sid="x"), work(10, 20, sid="x")))


def test_start_from_idle_appends(rules):
    """Starting with nothing active just appends."""
    first = work(0, 25)
    result = start_session((first,), work(30, None), rules)
    assert result == (first, work(30, None))


def test_start_ends_active_session(rules):
    """Starting a distraction ends the active work session at that moment."""
    result = start_session((work(0, None),), dis(10, None), rules)
    assert result == (work(0, 10), dis(10, None))


def test_start_does_not_mutate_input(rules):
    """The input history is left as it was."""
    history = (work(0, None),)
    start_session(history, dis(10, None), rules)
    assert history == (work(0, None),)


def test_start_after_expired_break_ends_break_at_cap(rules):
    """A break left open past its cap is recorded as ending at the cap."""
    history = (work(0, 50), brk(50, None))
    result = start_session(history, work(90, None), rules)
    assert result == (work(0, 50), brk(50, 60), work(90, None))


def test_start_during_break_ends_it_early(rules):
    """Starting work before the cap ends the break at that moment."""
    history = (work(0, 50), brk(50, None))
    result = start_session(history, work(55, None), rules)
    assert result[1] == brk(50, 55)


def test_break_without_credit_expires_immediately(rules):
    """A break with no preceding work is recorded with zero length."""
    history = start_session((), brk(0, None), rules)
    assert close_expired_breaks(history, at(0), rules) == (brk(0, 0),)


def test_start_rejects_session_with_end(rules):
    """Only open sessions can be started."""
    with pytest.raises(ValueError, match="must not have an end"):
        start_session((), work(0, 5), rules)


def test_backdated_start_trims_finished_session(rules):
    """A start time inside an earlier finished session cuts that session there."""
    assert start_session((work(0, 25),), dis(20, None), rules) == (work(0, 20), dis(20, None))


def test_backdated_start_trims_active_session(rules):
    """Backdating into the active session ends it at the backdated time."""
    assert start_session((work(0, None),), dis(15, None), rules) == (work(0, 15), dis(15, None))


def test_backdated_start_cannot_cover_whole_session(rules):
    """Backdating to before a whole later session is refused, naming it."""
    with pytest.raises(ValueError, match="completely cover the work session 'task'"):
        start_session((work(0, 25),), dis(-5, None), rules)


def test_place_trims_both_neighbours(rules):
    """A placed session trims the end of the one before and the start of the one after."""
    result = place_session((work(0, 25), work(30, 60)), dis(20, 35))
    assert result == (work(0, 20), dis(20, 35), replace(work(30, 60), start=at(35)))


def test_place_splits_surrounding_session(rules):
    """A session placed inside another splits it into before and after parts."""
    result = place_session((work(0, 60),), dis(20, 30), split_id="tail")
    assert result == (work(0, 20), dis(20, 30), replace(work(0, 60), id="tail", start=at(30)))


def test_place_splits_active_session(rules):
    """Splitting an active session leaves the second half active."""
    result = place_session((work(0, None),), dis(20, 30), split_id="tail")
    assert result[0] == work(0, 20) and result[2].is_active and result[2].start == at(30)


def test_place_split_needs_an_id():
    """A split without an id for the second half is refused."""
    with pytest.raises(ValueError, match="split"):
        place_session((work(0, 60),), dis(20, 30))


def test_place_refuses_to_cover_a_session():
    """A placed session may not swallow another whole."""
    with pytest.raises(ValueError, match="completely cover"):
        place_session((work(0, 10), work(10, 20, sid="mid"), work(20, 30)), dis(5, 25))


def test_place_into_free_gap_changes_nothing_else():
    """Placing into an empty gap leaves the neighbours untouched."""
    assert place_session((work(0, 10), work(30, 40)), dis(15, 20)) == (
        work(0, 10),
        dis(15, 20),
        work(30, 40),
    )


def test_place_active_session_must_be_last():
    """An active session cannot be placed before later sessions."""
    with pytest.raises(ValueError):
        place_session((work(0, 10), work(30, 40)), dis(15, None))


def test_end_session(rules):
    """Ending sets the end of the active session."""
    assert end_session((work(0, None),), at(30)) == (work(0, 30),)


def test_end_without_active_raises():
    """Ending with nothing active is an error."""
    with pytest.raises(ValueError, match="no active session"):
        end_session((work(0, 25),), at(30))


def test_end_before_start_raises():
    """The end cannot precede the start."""
    with pytest.raises(ValueError, match="precedes"):
        end_session((work(10, None),), at(5))
