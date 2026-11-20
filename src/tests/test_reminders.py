from datetime import datetime

from src.services.reminders import build_intervals, build_message, collect_due


def sched(date, *pairs):
    return {date: {"shutdowns": [{"from": f, "to": t} for f, t in pairs]}}


class TestBuildIntervals:
    def test_midnight_end_is_next_day(self):
        [(start, end)] = build_intervals(sched("20.11.2026", ("22:30", "00:00")))
        assert start == datetime(2026, 11, 20, 22, 30)
        assert end == datetime(2026, 11, 21, 0, 0)

    def test_touching_shutdowns_are_merged(self):
        intervals = build_intervals(sched("20.11.2026", ("15:30", "19:00"), ("19:00", "21:00")))
        assert intervals == [(datetime(2026, 11, 20, 15, 30), datetime(2026, 11, 20, 21, 0))]

    def test_merged_across_midnight(self):
        schedule = {**sched("20.11.2026", ("22:30", "00:00")), **sched("21.11.2026", ("00:00", "02:00"))}
        assert build_intervals(schedule) == [(datetime(2026, 11, 20, 22, 30), datetime(2026, 11, 21, 2, 0))]

    def test_separate_shutdowns_stay_separate(self):
        assert len(build_intervals(sched("20.11.2026", ("08:30", "12:00"), ("13:30", "15:30")))) == 2

    def test_bad_data_is_skipped(self):
        assert build_intervals({"bad-date": {"shutdowns": [{"from": "1", "to": "2"}]}}) == []


class TestCollectDue:
    intervals = {"1.1": [(datetime(2026, 11, 20, 15, 30), datetime(2026, 11, 20, 19, 0))]}

    def due(self, now, off=(), on=(), queues=("1.1",)):
        return collect_due(now, {1: {"off": set(off), "on": set(on)}}, {1: set(queues)}, self.intervals)

    def test_off_reminder_exactly_on_time(self):
        due = self.due(datetime(2026, 11, 20, 15, 15, 5), off=[15])
        assert list(due) == [(1, "off", datetime(2026, 11, 20, 15, 30), 15)]

    def test_on_reminder(self):
        due = self.due(datetime(2026, 11, 20, 18, 0, 5), on=[60])
        assert list(due) == [(1, "on", datetime(2026, 11, 20, 19, 0), 60)]

    def test_not_yet(self):
        assert self.due(datetime(2026, 11, 20, 15, 14), off=[15]) == {}

    def test_too_late_is_dropped(self):
        # 3+ minutes after the reminder time - user would get a wrong "in 15 min"
        assert self.due(datetime(2026, 11, 20, 15, 18), off=[15]) == {}

    def test_kinds_are_independent(self):
        assert self.due(datetime(2026, 11, 20, 15, 15, 5), on=[15]) == {}

    def test_unsubscribed_queue_ignored(self):
        assert self.due(datetime(2026, 11, 20, 15, 15, 5), off=[15], queues=("2.2",)) == {}

    def test_same_outage_in_several_queues_is_one_message(self):
        intervals = {q: self.intervals["1.1"] for q in ("1.1", "5.1")}
        due = collect_due(datetime(2026, 11, 20, 15, 15, 5), {1: {"off": {15}, "on": set()}},
                          {1: {"1.1", "5.1"}}, intervals)
        assert len(due) == 1
        [items] = due.values()
        assert sorted(q for q, _ in items) == ["1.1", "5.1"]


class TestBuildMessage:
    def test_off_message(self):
        interval = (datetime(2026, 11, 20, 15, 30), datetime(2026, 11, 20, 19, 0))
        text = build_message("off", 15, interval[0], [("5.1", interval), ("1.1", interval)])
        assert "Через 15 хв вимкнуть світло</b> (о 15:30)" in text
        assert "Черги 1.1, 5.1 · 15:30 - 19:00 – (<i>на 3 год 30 хв</i>)" in text

    def test_on_message_hour(self):
        interval = (datetime(2026, 11, 20, 22, 30), datetime(2026, 11, 21, 0, 0))
        text = build_message("on", 60, interval[1], [("1.2", interval)])
        assert "Через 1 год увімкнуть світло</b> (о 00:00)" in text
        assert "🟢 Черга 1.2 · 22:30 - 00:00" in text
