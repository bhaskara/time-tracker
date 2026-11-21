"""Tests for break caps, day boundaries, daily totals and current status."""

from datetime import date, datetime, timedelta

from timetracker.core.accounting import (
    DaySummary,
    total_days,
    week_start,
    weekly_totals,
    break_cap,
    contiguous_work_before,
    current_status,
    day_bounds,
    day_of,
    day_summary,
)
from timetracker.core.model import Session, SessionType

from .conftest import TZ, at, brk, dis, m, work

DAY = date(2026, 11, 11)


def test_contiguous_chain_sums_back_to_back_work(rules):
    """Two work sessions separated by a small gap chain together."""
    sessions = (work(0, 25), work(27, 52))
    assert contiguous_work_before(sessions, at(52), rules) == m(50)


def test_contiguous_chain_stops_at_large_gap(rules):
    """An untracked gap over the limit breaks the chain."""
    sessions = (work(0, 25), work(31, 56))
    assert contiguous_work_before(sessions, at(56), rules) == m(25)


def test_contiguous_chain_stops_at_break_and_distraction(rules):
    """Breaks and distractions reset the chain."""
    assert contiguous_work_before((work(0, 50), brk(50, 60), work(60, 80)), at(80), rules) == m(20)
    assert contiguous_work_before((work(0, 50), dis(50, 53), work(53, 63)), at(63), rules) == m(10)


def test_contiguous_chain_zero_when_gap_before_at(rules):
    """Work that ended long before the reference point earns nothing."""
    assert contiguous_work_before((work(0, 50),), at(60), rules) == m(0)


def test_break_cap_is_twenty_percent(rules):
    """50 minutes of work earns a 10 minute break."""
    b = brk(50, None)
    assert break_cap((work(0, 50), b), b, rules) == m(10)


def test_break_cap_limited_to_fifteen_minutes(rules):
    """Long work stretches still earn at most 15 minutes."""
    b = brk(120, None)
    assert break_cap((work(0, 120, planned=120), b), b, rules) == m(15)


def test_break_cap_zero_without_work(rules):
    """A break with no preceding work has no credit."""
    b = brk(0, None)
    assert break_cap((b,), b, rules) == m(0)


def test_summary_work_then_break_within_cap(rules):
    """50 min work + 10 min break counts as 60 min."""
    s = day_summary((work(0, 50), brk(50, 60)), DAY, at(100), rules)
    assert (s.work, s.break_credit, s.counted) == (m(50), m(10), m(60))


def test_summary_break_clipped_to_cap(rules):
    """A recorded break longer than its cap is only credited up to the cap."""
    s = day_summary((work(0, 50), brk(50, 75)), DAY, at(100), rules)
    assert s.counted == m(60)


def test_summary_distraction_adds_fixed_cost(rules):
    """10 min work then 3 min distraction: 10 min work, 13 min distraction."""
    s = day_summary((work(0, 10), dis(10, 13)), DAY, at(100), rules)
    assert (s.work, s.distraction) == (m(10), m(13))


def test_summary_overrun_counts_as_work(rules):
    """Time past the planned end still counts."""
    s = day_summary((work(0, 40, planned=25),), DAY, at(100), rules)
    assert s.work == m(40)


def test_summary_counts_active_session_up_to_now(rules):
    """An active session contributes its elapsed time."""
    s = day_summary((work(0, None),), DAY, at(12), rules)
    assert s.work == m(12)


def test_summary_progress_and_target(rules):
    """Progress is counted time over the target; default target is 8 h."""
    sessions = (work(0, 120, planned=120),)
    assert day_summary(sessions, DAY, at(200), rules).progress == 0.25
    assert day_summary(sessions, DAY, at(200), rules, target=timedelta(hours=4)).progress == 0.5


def test_day_boundary_at_2am(rules):
    """1:59 AM belongs to the previous day, 2:00 AM to the new one."""
    assert day_of(datetime(2026, 11, 12, 1, 59, tzinfo=TZ), rules) == DAY
    assert day_of(datetime(2026, 11, 12, 2, 0, tzinfo=TZ), rules) == date(2026, 11, 12)
    lo, hi = day_bounds(DAY, rules)
    assert lo == datetime(2026, 11, 11, 2, 0, tzinfo=TZ)
    assert hi == datetime(2026, 11, 12, 2, 0, tzinfo=TZ)


def test_summary_splits_session_spanning_boundary(rules):
    """A session crossing 2 AM contributes to each day only its part in that day."""
    s = Session(
        id="late",
        type=SessionType.WORK,
        start=datetime(2026, 11, 12, 1, 30, tzinfo=TZ),
        end=datetime(2026, 11, 12, 2, 20, tzinfo=TZ),
        planned=m(50),
    )
    now = datetime(2026, 11, 12, 9, 0, tzinfo=TZ)
    assert day_summary((s,), DAY, now, rules).work == m(30)
    assert day_summary((s,), date(2026, 11, 12), now, rules).work == m(20)


def test_summary_distraction_cost_charged_to_start_day(rules):
    """The fixed distraction cost lands on the day the distraction started."""
    s = Session(
        id="d",
        type=SessionType.DISTRACTION,
        start=datetime(2026, 11, 12, 1, 55, tzinfo=TZ),
        end=datetime(2026, 11, 12, 2, 5, tzinfo=TZ),
    )
    now = datetime(2026, 11, 12, 9, 0, tzinfo=TZ)
    assert day_summary((s,), DAY, now, rules).distraction == m(15)
    assert day_summary((s,), date(2026, 11, 12), now, rules).distraction == m(5)


def test_status_idle(rules):
    """No sessions, or only finished ones, means idle."""
    assert current_status((), at(0), rules).active is None
    assert current_status((work(0, 25),), at(30), rules).active is None


def test_status_work_remaining_and_overrun(rules):
    """Remaining time counts down and goes negative in overrun."""
    sessions = (work(0, None, planned=25),)
    st = current_status(sessions, at(10), rules)
    assert (st.elapsed, st.remaining, st.overrun) == (m(10), m(15), False)
    st = current_status(sessions, at(32), rules)
    assert (st.remaining, st.overrun) == (m(-7), True)


def test_status_break_counts_down_to_cap_then_idle(rules):
    """A break shows time left to its cap and is no longer active after it."""
    sessions = (work(0, 50), brk(50, None))
    assert current_status(sessions, at(54), rules).remaining == m(6)
    assert current_status(sessions, at(60), rules).active is None


def test_status_distraction_has_no_remaining(rules):
    """Distractions are open-ended."""
    st = current_status((dis(0, None),), at(4), rules)
    assert (st.elapsed, st.remaining) == (m(4), None)


def _summary(day: date, work_min: float, break_min: float = 0, distraction_min: float = 0):
    """Day summary with the given minutes."""
    return DaySummary(day, m(work_min), m(break_min), m(distraction_min), timedelta(hours=8))


def test_week_start_is_monday():
    """Any day maps to the Monday of its week."""
    assert week_start(date(2026, 11, 11)) == date(2026, 11, 9)
    assert week_start(date(2026, 11, 9)) == date(2026, 11, 9)
    assert week_start(date(2026, 11, 15)) == date(2026, 11, 9)


def test_total_days_sums_and_counts_worked_days():
    """Totals add up and only days with counted time are 'worked'."""
    total = total_days(
        [_summary(date(2026, 11, 9), 120, 20, 15), _summary(date(2026, 11, 10), 0, 0, 30)]
    )
    assert (total.start, total.end) == (date(2026, 11, 9), date(2026, 11, 10))
    assert (total.work, total.break_credit, total.counted) == (m(120), m(20), m(140))
    assert (total.distraction, total.days_worked) == (m(45), 1)


def test_weekly_totals_groups_by_calendar_week():
    """Days are grouped Monday to Sunday."""
    days = [_summary(date(2026, 11, 8), 60), _summary(date(2026, 11, 9), 30), _summary(date(2026, 11, 15), 45)]
    weeks = weekly_totals(days)
    assert [(w.start, w.end, w.work) for w in weeks] == [
        (date(2026, 11, 8), date(2026, 11, 8), m(60)),
        (date(2026, 11, 9), date(2026, 11, 15), m(75)),
    ]
