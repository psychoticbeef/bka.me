import os
import unittest
from datetime import datetime
from unittest.mock import patch

import yaml

from scrape_stations import BERLIN_TZ, calculate_time_window, get_run_dates


class TimeWindowTests(unittest.TestCase):
    config = {"time_range": {"start": 8, "end": 18}}

    def window(self, now, days_back):
        with patch.dict(os.environ, {"DAYS_BACK": str(days_back)}):
            target, weekday = get_run_dates(now)
            start, end = calculate_time_window(self.config, target, now)
        return target, weekday, start, end

    def test_today_before_start_has_no_completed_hours(self):
        now = datetime(2026, 10, 8, 1, 15, tzinfo=BERLIN_TZ)
        _, _, start, end = self.window(now, 0)
        self.assertGreater(start, end)

    def test_today_at_start_has_no_completed_hours(self):
        now = datetime(2026, 10, 8, 8, 30, tzinfo=BERLIN_TZ)
        _, _, start, end = self.window(now, 0)
        self.assertEqual(start, end)

    def test_today_only_includes_completed_hours(self):
        now = datetime(2026, 10, 8, 14, 15, tzinfo=BERLIN_TZ)
        _, _, start, end = self.window(now, 0)
        self.assertEqual((start.hour, end.hour, end.minute), (8, 14, 0))

    def test_today_after_end_uses_full_window(self):
        now = datetime(2026, 10, 8, 20, 15, tzinfo=BERLIN_TZ)
        _, _, start, end = self.window(now, 0)
        self.assertEqual((start.hour, end.hour), (8, 18))

    def test_yesterday_uses_full_window_even_early_in_morning(self):
        now = datetime(2026, 10, 8, 1, 15, tzinfo=BERLIN_TZ)
        target, weekday, start, end = self.window(now, 1)
        self.assertEqual(target.strftime("%Y-%m-%d"), "2026-10-07")
        self.assertEqual(weekday, 2)
        self.assertEqual((start.hour, end.hour), (8, 18))
        self.assertEqual(start.date(), target.date())
        self.assertEqual(end.date(), target.date())

    def test_sunday_schedule_is_used_on_monday_run(self):
        now = datetime(2026, 10, 12, 8, 37, tzinfo=BERLIN_TZ)
        with open("stations.yaml", encoding="utf-8") as f:
            stations = yaml.safe_load(f)
        with patch.dict(os.environ, {"DAYS_BACK": "1"}):
            target, weekday = get_run_dates(now)
            swr1 = next(config for config in stations if config["name"] == "SWR1")
            start, end = calculate_time_window(swr1, target, now)
        self.assertEqual(weekday, 6)
        self.assertIn(weekday, swr1["schedule"])
        self.assertEqual((start.hour, end.hour), (11, 16))

    def test_previous_day_across_dst_changes(self):
        for month, day in [(3, 30), (10, 26)]:
            with self.subTest(month=month):
                now = datetime(2026, month, day, 8, 37, tzinfo=BERLIN_TZ)
                target, weekday, start, end = self.window(now, 1)
                self.assertEqual(target.day, day - 1)
                self.assertEqual(weekday, 6)
                self.assertEqual((start.hour, end.hour), (8, 18))
                self.assertEqual(start.utcoffset(), end.utcoffset())


if __name__ == "__main__":
    unittest.main()
