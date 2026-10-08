import inspect
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from run_evaluation import write_outputs
from src.alarms import ON_DELAY_HOURS, annunciate
from src.analyze_scada import PERCENTILE, apply_reference, detect
from src.evaluate import (
    BASELINE, CALIBRATION_SEEDS, EVALUATION_SEEDS, METHODS, ON_DELAYS, PERCENTILES, PRIMARY,
    aggregate, bootstrap, by_severity, choose_operating_point, evaluate, score,
)
from src.generate_synthetic_scada import SEED, simulate

REPORTS = Path(__file__).resolve().parents[1] / "reports"


def year(events, false_alarms=0, normal_hours=1000, normal_alarm_hours=0):
    return {"events": [{"severity": severity, "ramp_hours": 72, "detected": lead is not None, "lead_hours": lead}
                       for severity, lead in events],
            "false_alarms": false_alarms, "normal_hours": normal_hours, "normal_alarm_hours": normal_alarm_hours}


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.times = pd.Series(pd.date_range("2025-06-25", periods=600, freq="h"))
        self.truth = {"reference_end_exclusive": "2025-06-30T00:00:00",
                      "events": [{"ramp_start": "2025-07-05T00:00:00", "trip_time": "2025-07-08T00:00:00",
                                  "shutdown_hours": 24, "ramp_hours": 72, "severity": .8}]}
        self.eligible = np.ones(600, dtype=bool)

    def state(self, *spans):
        flags = np.zeros(600, dtype=bool)
        for start, hours in spans:
            first = self.times[self.times == pd.Timestamp(start)].index[0]
            flags[first:first + hours] = True
        return flags

    def test_detection_lead_and_false_alarms(self):
        state = self.state(("2025-06-27T00:00", 3),    # before the reference ends: not counted
                           ("2025-07-02T10:00", 4),    # normal operation: one false alarm
                           ("2025-07-07T14:00", 2),    # inside the ramp, 10 h before the trip
                           ("2025-07-08T05:00", 3))    # during the trip stop: neither hit nor false alarm
        result = score(state, self.eligible, self.times, self.truth)
        self.assertEqual(result["events"], [{"severity": .8, "ramp_hours": 72, "detected": True, "lead_hours": 10.0}])
        self.assertEqual(result["false_alarms"], 1)
        self.assertEqual(result["normal_alarm_hours"], 4)
        # 600 h minus 120 h of reference, 72 h of ramp and 24 h of stop.
        self.assertEqual(result["normal_hours"], 384)

    def test_always_and_never_detectors(self):
        always = score(np.ones(600, dtype=bool), self.eligible, self.times, self.truth)
        never = score(np.zeros(600, dtype=bool), self.eligible, self.times, self.truth)
        self.assertEqual(always["events"][0]["lead_hours"], 72.0)
        self.assertEqual(always["normal_alarm_hours"], always["normal_hours"])
        self.assertFalse(never["events"][0]["detected"])
        self.assertEqual((never["false_alarms"], never["normal_alarm_hours"]), (0, 0))

    def test_labels_change_the_score_but_never_the_alarms(self):
        for function in (apply_reference, annunciate, detect):
            self.assertFalse({"truth", "events"} & set(inspect.signature(function).parameters))
        state = self.state(("2025-07-07T14:00", 2))
        moved = json.loads(json.dumps(self.truth))
        moved["events"][0].update(ramp_start="2025-07-10T00:00:00", trip_time="2025-07-13T00:00:00")
        self.assertTrue(score(state, self.eligible, self.times, self.truth)["events"][0]["detected"])
        relabelled = score(state, self.eligible, self.times, moved)
        self.assertFalse(relabelled["events"][0]["detected"])
        self.assertEqual(relabelled["false_alarms"], 1)


class StatisticsTests(unittest.TestCase):
    def test_aggregate_point_estimates(self):
        stats = aggregate([year([(.9, 30.0), (.2, None)], false_alarms=1, normal_alarm_hours=5),
                           year([(.6, 10.0)], false_alarms=2, normal_hours=3000)])
        self.assertEqual((stats["events"], stats["detected"]), (3, 2))
        self.assertAlmostEqual(stats["detection_rate"], 2 / 3)
        self.assertEqual(stats["false_alarms_per_1000h"], .75)
        self.assertEqual(stats["normal_time_in_alarm_pct"], .125)
        self.assertEqual(stats["lead_hours_median"], 20.0)

    def test_bootstrap_is_deterministic_and_brackets_the_estimate(self):
        rng = np.random.default_rng(0)
        years = [year([(.5, float(rng.integers(5, 60))) if rng.random() < .7 else (.5, None) for _ in range(3)],
                      false_alarms=int(rng.integers(0, 3))) for _ in range(40)]
        first, second = bootstrap(years, resamples=300), bootstrap(years, resamples=300)
        self.assertEqual(first, second)
        stats = aggregate(years)
        for key in ("detection_rate", "false_alarms_per_1000h", "lead_hours_median"):
            self.assertLessEqual(first[key][0], stats[key])
            self.assertGreaterEqual(first[key][1], stats[key])
        # A detector compared with itself has a paired difference of exactly zero.
        self.assertEqual(bootstrap(years, other=years, resamples=50)["detection_rate"], [0.0, 0.0])

    def test_severity_bins_cover_every_event(self):
        rows = by_severity([year([(.15, None), (.36, 5.0), (.74, 8.0), (1.0, 9.0)])])
        self.assertEqual([row["events"] for row in rows], [1, 1, 1, 1])
        self.assertEqual([row["detection_rate"] for row in rows], [0, 1, 1, 1])

    def test_operating_point_rule(self):
        hit, miss = year([(.9, 20.0)]), year([(.9, None)])
        noisy = year([(.9, 40.0)], false_alarms=5)
        table = {(PRIMARY, 95, 2): [noisy, noisy], (PRIMARY, 99, 2): [hit, hit], (PRIMARY, 99, 3): [hit, miss],
                 (BASELINE, 95, 2): [hit, hit]}
        # The noisy setting detects everything but breaks the false-alarm budget.
        self.assertEqual(choose_operating_point(table), (99, 2))
        with self.assertRaisesRegex(ValueError, "budget"):
            choose_operating_point({(PRIMARY, 95, 2): [noisy]})


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Small run that stays inside the calibration range: the evaluation seeds are not touched by tests.
        cls.calibration, cls.held_out = [1000, 1001], [1002, 1003, 1004, 1005]
        cls.summary = evaluate(cls.calibration, cls.held_out, resamples=100)

    def test_seed_sets_are_separate(self):
        self.assertEqual((len(CALIBRATION_SEEDS), len(EVALUATION_SEEDS)), (20, 100))
        self.assertFalse(set(CALIBRATION_SEEDS) & set(EVALUATION_SEEDS))
        self.assertNotIn(SEED, CALIBRATION_SEEDS + EVALUATION_SEEDS)
        with self.assertRaisesRegex(ValueError, "overlap"):
            evaluate([1000, 1001], [1001, 1002])

    def test_summary_structure_and_counts(self):
        summary = self.summary
        point = summary["operating_point"]
        self.assertIn(point["percentile"], PERCENTILES)
        self.assertIn(point["on_delay_hours"], ON_DELAYS)
        self.assertEqual(list(summary["evaluation"]), METHODS)
        self.assertEqual(len(summary["sensitivity"]), 2 * len(PERCENTILES) * len(ON_DELAYS))
        events = sum(len(simulate(seed)[1]["events"]) for seed in self.held_out)
        for row in summary["evaluation"].values():
            self.assertEqual(row["events"], events)
            self.assertTrue(0 <= row["detection_rate"] <= 1)
            self.assertEqual(sum(part["events"] for part in row["by_severity"]), events)
        primary = summary["evaluation"][PRIMARY]
        self.assertEqual(len(summary["lead_hours"]), primary["detected"])
        self.assertAlmostEqual(summary["primary_minus_baseline"]["detection_rate"],
                               primary["detection_rate"] - summary["evaluation"][BASELINE]["detection_rate"])
        review = summary["alarm_review"]
        self.assertLessEqual(review["with_deadband"]["activations"], review["without_deadband"]["activations"])

    def test_evaluation_is_reproducible_and_writes_its_report(self):
        again = evaluate(self.calibration, self.held_out, resamples=100)
        self.assertEqual(json.dumps(self.summary), json.dumps(again))
        with tempfile.TemporaryDirectory() as tmp:
            write_outputs(tmp, self.summary, with_figures=False)
            written = json.loads((Path(tmp) / "reports/evaluation_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(written, json.loads(json.dumps(self.summary)))
            text = (Path(tmp) / "reports/evaluation.md").read_text(encoding="utf-8")
            self.assertIn(f"P{self.summary['operating_point']['percentile']}", text)
            self.assertTrue((Path(tmp) / "reports/evaluation_sensitivity.csv").exists())

    def test_published_operating_point_matches_code_defaults(self):
        published = json.loads((REPORTS / "evaluation_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(published["protocol"]["calibration_seeds"], CALIBRATION_SEEDS)
        self.assertEqual(published["protocol"]["evaluation_seeds"], EVALUATION_SEEDS)
        self.assertEqual(published["operating_point"], {"percentile": PERCENTILE, "on_delay_hours": ON_DELAY_HOURS})


if __name__ == "__main__":
    unittest.main()
