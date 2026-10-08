import unittest

import numpy as np
import pandas as pd

from src.alarms import ALARM_POINTS, alarm_kpis, annunciate, episodes, latch, sustained
from src.analyze_scada import apply_reference, derive, detect
from src.generate_synthetic_scada import selected_measurements, simulate


def hourly(count, skip=()):
    """Consecutive hours, optionally leaving out some positions to create gaps."""
    stamps = pd.date_range("2025-03-01", periods=count + len(skip), freq="h")
    return pd.Series([stamp for index, stamp in enumerate(stamps) if index not in skip])


class LatchTests(unittest.TestCase):
    def test_on_delay_needs_consecutive_hours(self):
        above = [False, True, True, True, True, False, True, True, False]
        state = latch(above, above, hourly(9), on_delay=3)
        self.assertEqual(state.tolist(), [False, False, False, True, True, False, False, False, False])

    def test_without_deadband_latch_equals_persistence_rule(self):
        rng = np.random.default_rng(3)
        times = hourly(400, skip=(50, 51, 200))
        for on_delay in (2, 3, 4):
            above = rng.random(400) < .7
            self.assertEqual(latch(above, above, times, on_delay=on_delay).tolist(),
                             sustained(pd.Series(above), times, on_delay).tolist())

    def test_deadband_holds_the_alarm_through_small_dips(self):
        values = np.array([11, 11, 11, 9.5, 11, 11, 11, 9.5, 11, 11, 11, 8, 8])
        times, above = hourly(len(values)), values > 10
        plain = latch(above, above, times, on_delay=3)
        held = latch(above, values > 10 - 1, times, on_delay=3)
        self.assertEqual(len(episodes(plain, times)), 3)
        self.assertEqual(len(episodes(held, times)), 1)
        # It still clears once the value drops below threshold minus deadband.
        self.assertEqual(held.tolist(), [False, False] + [True] * 9 + [False, False])

    def test_deadband_never_adds_activations(self):
        rng = np.random.default_rng(11)
        times = hourly(2000)
        for _ in range(5):
            values = np.cumsum(rng.normal(0, .5, 2000)) % 4 + 8
            above = values > 10
            plain, held = latch(above, above, times), latch(above, values > 9.3, times)
            self.assertTrue(np.all(held[plain]))
            self.assertLessEqual(len(episodes(held, times)), len(episodes(plain, times)))

    def test_off_delay_tolerates_one_hour_below(self):
        above = [True, True, True, False, True, False, False, True]
        state = latch(above, above, hourly(8), on_delay=3, off_delay=2)
        self.assertEqual(state.tolist(), [False, False, True, True, True, True, False, False])

    def test_gap_clears_alarm_and_restarts_the_count(self):
        above = [True] * 8
        state = latch(above, above, hourly(8, skip=(4,)), on_delay=3)
        self.assertEqual(state.tolist(), [False, False, True, True, False, False, True, True])


class PriorityAndKpiTests(unittest.TestCase):
    def frame(self, thermal, current):
        count = len(thermal)
        d = pd.DataFrame({"t": hourly(count), "eligible": True,
                          "winding_rise_c": thermal, "winding_rise_c_threshold": 30.0,
                          "current_spread_pct": current, "current_spread_pct_threshold": 3.0})
        for metric in ("winding_rise_c", "current_spread_pct"):
            d[metric + "_high"] = d.eligible & d[metric].gt(d[metric + "_threshold"])
        d["joint_high"] = d.winding_rise_c_high & d.current_spread_pct_high
        return d

    def test_priority_escalates_when_both_indicators_alarm(self):
        thermal = [25] * 2 + [32] * 10 + [25] * 4
        current = [1] * 6 + [4] * 6 + [1] * 4
        out = annunciate(self.frame(thermal, current), on_delay=3)
        # Thermal alone from its third high hour; joint from the third hour both are high.
        self.assertEqual(out.priority.tolist(), [0] * 4 + [1] * 4 + [2] * 4 + [0] * 4)
        self.assertEqual(out.alarm_high.sum(), 4)

    def test_ineligible_hours_cannot_alarm(self):
        d = self.frame([32] * 8, [4] * 8)
        d["eligible"] = False
        for metric in ("winding_rise_c", "current_spread_pct"):
            d[metric + "_high"] = False
        d["joint_high"] = False
        self.assertEqual(annunciate(d).priority.sum(), 0)

    def test_episode_durations_and_repeats(self):
        state = [False, True, True, False, False, True] + [True] * 30 + [False] * 20 + [True, False]
        rows = episodes(state, hourly(len(state)))
        self.assertEqual([row["duration_hours"] for row in rows], [2, 31, 1])
        self.assertEqual([row["hours_since_clear"] for row in rows], [None, 2, 20])

    def test_kpis_count_fleeting_stale_and_rates(self):
        count = 500
        thermal = np.full(count, 25.0)
        thermal[10:15] = 32      # one 3 h alarm after the on-delay (hours 12-14)
        thermal[100:140] = 32    # one stale alarm (38 h active)
        thermal[143:147] = 32    # back within 6 h of the clear: a repeat, and fleeting
        out = annunciate(self.frame(thermal, np.full(count, 1.0)), on_delay=3, deadband={"winding_rise_c": 0, "current_spread_pct": 0})
        kpis = alarm_kpis(out)
        point = kpis["points"][0]
        self.assertEqual(point["tag"], ALARM_POINTS[0][0])
        self.assertEqual((point["activations"], point["stale"], point["fleeting"], point["repeats"]), (3, 1, 1, 1))
        self.assertEqual(point["activations_per_1000h"], 6.0)
        self.assertEqual(kpis["activations_by_priority"], {"baja": 3, "alta": 0})
        # A mask counts only activations that start inside it.
        self.assertEqual(alarm_kpis(out, out.index < 50)["activations"], 1)


class ConditioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frame, cls.truth = simulate()
        cls.derived = derive(selected_measurements(frame))
        cls.cutoff = pd.Timestamp(cls.truth["reference_end_exclusive"])

    def test_baseline_is_one_fixed_threshold(self):
        out, cells = apply_reference(self.derived, self.cutoff, conditioning="none")
        self.assertEqual(len(cells), 1)
        self.assertEqual(out.winding_rise_c_threshold.nunique(), 1)
        by_load, load_cells = apply_reference(self.derived, self.cutoff, conditioning="load")
        both, both_cells = apply_reference(self.derived, self.cutoff)
        self.assertTrue(1 < len(load_cells) < len(both_cells))
        # Winding rise grows with load, so a load-conditioned threshold must vary a lot.
        self.assertGreater(by_load.winding_rise_c_threshold.max() - by_load.winding_rise_c_threshold.min(), 10)

    def test_higher_percentile_never_lowers_a_threshold(self):
        thresholds = [apply_reference(self.derived, self.cutoff, percentile=p)[0].winding_rise_c_threshold
                      for p in (95, 99, 99.5)]
        valid = thresholds[0].notna()
        self.assertTrue((thresholds[0][valid] <= thresholds[1][valid]).all())
        self.assertTrue((thresholds[1][valid] <= thresholds[2][valid]).all())

    def test_detector_output_ignores_what_happens_after_the_cutoff(self):
        first, _ = detect(self.derived, self.cutoff)
        changed = self.derived.copy()
        changed.loc[changed.t >= self.cutoff, "current_spread_pct"] += 50
        second, _ = detect(changed, self.cutoff)
        self.assertTrue(first.winding_rise_c_threshold.equals(second.winding_rise_c_threshold))
        self.assertTrue(first.current_spread_pct_threshold.equals(second.current_spread_pct_threshold))


if __name__ == "__main__":
    unittest.main()
