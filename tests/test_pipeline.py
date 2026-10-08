import csv
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from run_pipeline import run
from src.analyze_scada import apply_reference, derive, flat_sensor, sustained
from src.build_processed import build, logical_time
from src.common import RAW_FIELDS, SIGNALS, digest
from src.file_inventory import inventory, verify
from src.generate_synthetic_scada import (
    COMMUNICATION_HOURS, DUPLICATE_HOURS, EARLY_HOURS, HOURS,
    MISSING_HOURS, SYNTHETIC_EVENT_TIME, generate,
)
from src.read_scada_csv import read_records


def read_csv(path, delimiter=","):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        generate(cls.root)
        cls.before = {p.name: digest(p) for p in (cls.root / "data/raw").glob("*.csv")}
        inventory(cls.root)
        read_records(cls.root)
        cls.quality = build(cls.root)
        from src.analyze_scada import analyze
        cls.analysis = analyze(cls.root, figures=False)
        cls.interim = read_csv(cls.root / "data/interim/records.csv")
        cls.processed = read_csv(cls.root / "data/processed/scada.csv")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_generation_reproducible_bytes(self):
        with tempfile.TemporaryDirectory() as other:
            generate(other)
            hashes = {p.name: digest(p) for p in (Path(other) / "data/raw").glob("*.csv")}
            self.assertEqual(self.before, hashes)
            self.assertEqual((self.root / "data/synthetic_scenario.json").read_bytes(),
                             (Path(other) / "data/synthetic_scenario.json").read_bytes())

    def test_raw_immutable_through_analysis(self):
        after = {p.name: digest(p) for p in (self.root / "data/raw").glob("*.csv")}
        self.assertEqual(self.before, after)
        self.assertEqual(len(verify(self.root)), 365)

    def test_every_row_and_original_cell_preserved(self):
        expected = HOURS - len(MISSING_HOURS) + len(DUPLICATE_HOURS) + len(COMMUNICATION_HOURS) + 1
        self.assertEqual(len(self.interim), expected)
        self.assertEqual(len(self.processed), expected)
        for original, processed in zip(self.interim, self.processed):
            self.assertTrue(all(processed[key] == value for key, value in original.items()))

    def test_physical_provenance_and_parsing(self):
        by_source = {}
        for row in self.interim:
            source = row["source_file"]
            if source not in by_source:
                by_source[source] = read_csv(self.root / source, delimiter=";")
            raw = by_source[source][int(row["source_line"]) - 2]
            self.assertEqual({key: row[key] for key in RAW_FIELDS}, raw)
            self.assertEqual(row["timestamp"], row["date"] + "T" + row["time"])

    def test_events_are_retained_without_measurement_values(self):
        events = [r for r in self.processed if r["record_type"] == "event"]
        self.assertEqual(len(events), len(COMMUNICATION_HOURS) + 1)
        for row in events:
            self.assertTrue(all(row[key] == "" for key in SIGNALS))
            self.assertEqual(row["requires_review"], "True")
        anchor = [r for r in events if r["event_message"] == "synthetic_shutdown"]
        self.assertEqual(anchor[0]["timestamp"], SYNTHETIC_EVENT_TIME.isoformat())

    def test_conflicting_alternatives_not_deduplicated(self):
        flagged = [r for r in self.processed if r["logical_hour_multiple"] == "True"]
        self.assertEqual(len(flagged), 2 * len(DUPLICATE_HOURS))
        self.assertTrue(all(r["logical_hour_conflict"] == "True" for r in flagged))
        self.assertTrue(all(r["logical_hour_count"] == "2" for r in flagged))
        self.assertEqual(self.quality["measurement_hours"], HOURS - len(MISSING_HOURS))

    def test_near_hour_correction_and_midnight_boundary(self):
        shifted = [r for r in self.processed if r["offset_seconds"] == "-2"]
        self.assertEqual(len(shifted), len(EARLY_HOURS))
        boundary = [r for r in shifted if r["date_mismatch"] == "True"]
        self.assertEqual(len(boundary), 1)
        self.assertEqual(boundary[0]["date_requires_review"], "False")
        self.assertEqual(str(logical_time("2042-04-03T12:59:56")), "2042-04-03 12:59:56")
        self.assertEqual(str(logical_time("2042-04-03T12:59:57")), "2042-04-03 13:00:00")

    def test_injected_change_and_window_coverage(self):
        self.assertTrue(self.analysis["synthetic_change_detected"])
        self.assertGreater(self.analysis["lead_hours"], 0)
        self.assertLessEqual(self.analysis["lead_hours"], 72)
        periods = {p["period"]: p for p in self.analysis["periods"]}
        for hours in (72, 24, 6):
            part = periods[f"pre_event_{hours}h"]
            self.assertEqual(part["eligible_hours"], hours)
            self.assertGreater(part["persistent_alert_hours"], 0)
        self.assertGreater(periods["pre_event_6h"]["winding_rise_c_residual_median"],
                           periods["pre_event_72h"]["winding_rise_c_residual_median"])
        self.assertEqual(periods["normal_holdout"]["persistent_alert_hours"], 0)
        self.assertEqual(self.analysis["sensor_flat_hours"], 18)

    def test_future_values_cannot_change_reference(self):
        frame = pd.read_csv(self.root / "data/processed/scada.csv")
        selected = frame[(frame.record_type == "measurement") & ~frame.requires_review]
        derived = derive(selected)
        cutoff = pd.Timestamp(self.analysis["reference_end_exclusive"])
        _, original = apply_reference(derived, cutoff)
        derived.loc[derived.t >= cutoff, "winding_rise_c"] = 700
        _, changed = apply_reference(derived, cutoff)
        self.assertEqual(original, changed)

    def test_reexecution_does_not_overwrite_existing_data(self):
        with self.assertRaises(FileExistsError):
            run(self.root, figures=False)
        self.assertEqual(self.before, {p.name: digest(p) for p in (self.root / "data/raw").glob("*.csv")})


class EdgeTests(unittest.TestCase):
    def test_persistence_and_freeze_never_bridge_gaps(self):
        times = pd.Series(pd.to_datetime(["2042-01-01T01:00", "2042-01-01T02:00", "2042-01-01T04:00", "2042-01-01T05:00", "2042-01-01T06:00"]))
        flags = sustained(pd.Series([True] * 5), times)
        self.assertEqual(flags.tolist(), [False, False, False, False, True])
        frozen = flat_sensor(pd.Series([12.] * 5), times, minimum=3)
        self.assertEqual(frozen.tolist(), [False, False, True, True, True])

    def test_malformed_numbers_rejected_and_inventory_tampering_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "data/raw"
            raw.mkdir(parents=True)
            path = raw / "history_2042-01-01.csv"
            row = dict.fromkeys(SIGNALS, "1.00")
            row.update(date="2042-01-01", time="01:00:00", record_type="measurement", event_message="")
            row[SIGNALS[0]] = "invalid"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS, delimiter=";")
                writer.writeheader()
                writer.writerow(row)
            inventory(root)
            with self.assertRaisesRegex(ValueError, "Invalid number"):
                read_records(root)
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "RAW bytes changed"):
                verify(root)

    def test_missing_event_anchor_fails_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/processed").mkdir(parents=True)
            (root / "data/synthetic_scenario.json").write_text(json.dumps({
                "start": "2042-01-01", "current_ramp_start": "2042-11-14T20:00:00",
                "synthetic_event_time": "2042-11-18T20:00:00"}), encoding="utf-8")
            pd.DataFrame(columns=["record_type", "event_message", "logical_hour"]).to_csv(root / "data/processed/scada.csv", index=False)
            from src.analyze_scada import analyze
            with self.assertRaisesRegex(ValueError, "event anchor"):
                analyze(root, figures=False)


if __name__ == "__main__":
    unittest.main()
