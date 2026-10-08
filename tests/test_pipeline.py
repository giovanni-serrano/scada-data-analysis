import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from run_pipeline import run
from src.analyze_scada import apply_reference, derive, flat_sensor, sustained
from src.build_processed import build, logical_time
from src.common import RAW_FIELDS, SIGNALS, TAG_CATALOG, TAGS, TRIP_MESSAGE, digest
from src.file_inventory import inventory, verify
from src.generate_synthetic_scada import (
    COMMUNICATION_HOURS, DUPLICATE_HOURS, EARLY_HOURS, EVENT_COUNT, FULL_CURRENT_SPREAD_DELTA_PCT,
    FULL_WINDING_DELTA_C, HOURS, MIN_EVENT_GAP_HOURS, MISSING_HOURS, NOMINAL_HZ, RAMP_HOURS,
    REFERENCE_HOURS, SEVERITY, generate, selected_measurements, simulate,
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
        cls.truth = generate(cls.root)
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
        expected = (HOURS - len(MISSING_HOURS) + len(DUPLICATE_HOURS) + len(COMMUNICATION_HOURS)
                    + len(self.truth["events"]))
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
        self.assertEqual(len(events), len(COMMUNICATION_HOURS) + len(self.truth["events"]))
        for row in events:
            self.assertTrue(all(row[key] == "" for key in TAGS))
            self.assertEqual(row["requires_review"], "True")
        anchors = [r["timestamp"] for r in events if r["event_message"] == TRIP_MESSAGE]
        self.assertEqual(anchors, [e["trip_time"] for e in self.truth["events"]])

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
        self.assertEqual(str(logical_time("2025-04-03T12:59:56")), "2025-04-03 12:59:56")
        self.assertEqual(str(logical_time("2025-04-03T12:59:57")), "2025-04-03 13:00:00")

    def test_events_scored_against_truth(self):
        scored = self.analysis["events"]
        self.assertEqual([e["trip_time"] for e in scored], [e["trip_time"] for e in self.truth["events"]])
        self.assertEqual(self.analysis["events_detected"], sum(e["detected"] for e in scored))
        for event in scored:
            self.assertLessEqual(event["eligible_hours"], event["ramp_hours"])
            self.assertEqual(event["detected"], event["persistent_alert_hours"] > 0)
            if event["detected"]:
                # The first alert lies inside the ramp, never at or after the trip.
                self.assertGreater(event["lead_hours"], 0)
                self.assertLessEqual(event["lead_hours"], event["ramp_hours"])
            else:
                self.assertIsNone(event["lead_hours"])
        periods = {p["period"]: p for p in self.analysis["periods"]}
        self.assertEqual(set(periods), {"reference", "normal_operation"})
        self.assertLess(periods["normal_operation"]["available_hours"],
                        HOURS - REFERENCE_HOURS - sum(e["ramp_hours"] for e in scored))
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
        times = pd.Series(pd.to_datetime(["2025-01-01T01:00", "2025-01-01T02:00", "2025-01-01T04:00", "2025-01-01T05:00", "2025-01-01T06:00"]))
        flags = sustained(pd.Series([True] * 5), times)
        self.assertEqual(flags.tolist(), [False, False, False, False, True])
        frozen = flat_sensor(pd.Series([12.] * 5), times, minimum=3)
        self.assertEqual(frozen.tolist(), [False, False, True, True, True])

    def test_malformed_numbers_rejected_and_inventory_tampering_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "data/raw"
            raw.mkdir(parents=True)
            path = raw / "history_2025-01-01.csv"
            row = dict.fromkeys(TAGS, "1.00")
            row.update(date="2025-01-01", time="01:00:00", record_type="measurement", event_message="")
            row[TAGS[0]] = "invalid"
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
                "start": "2025-01-01", "reference_end_exclusive": "2025-06-30T00:00:00",
                "events": [{"trip_time": "2025-11-18T20:00:00"}]}), encoding="utf-8")
            pd.DataFrame(columns=["record_type", "event_message", "logical_hour"]).to_csv(root / "data/processed/scada.csv", index=False)
            from src.analyze_scada import analyze
            with self.assertRaisesRegex(ValueError, "event anchor"):
                analyze(root, figures=False)


class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.truth = simulate()
        cls.derived = derive(selected_measurements(cls.frame))
        cls.reference = cls.derived[(cls.derived.t < pd.Timestamp(cls.truth["reference_end_exclusive"]))
                                    & cls.derived.steady_generation]

    def test_tag_catalog_is_complete_and_unique(self):
        self.assertEqual(len(TAG_CATALOG), 20)
        self.assertEqual(len(set(TAGS)), 20)
        self.assertEqual(len(set(SIGNALS)), 20)
        self.assertEqual(RAW_FIELDS[4:], TAGS)
        self.assertTrue(all(tag == tag.upper() and unit and description for tag, _, unit, description in TAG_CATALOG))
        self.assertEqual(list(self.frame.columns), ["logical_hour", *SIGNALS])

    def test_sixty_hertz_and_calendar_year(self):
        self.assertEqual(self.truth["nominal_frequency_hz"], 60)
        generating = self.derived[self.derived.state == "generating"]
        self.assertAlmostEqual(generating.frequency_hz.mean(), NOMINAL_HZ, delta=.01)
        self.assertTrue(generating.frequency_hz.between(59.8, 60.2).all())
        self.assertEqual(self.frame.logical_hour.iloc[0], "2025-01-01T00:00:00")
        self.assertEqual(self.frame.logical_hour.iloc[-1], "2025-12-31T23:00:00")

    def test_phase_unbalance_and_noise_are_realistic(self):
        ref = self.reference
        self.assertTrue(.5 < ref.current_spread_pct.median() < 2.5)
        self.assertLess(ref.current_spread_pct.quantile(.99), 5)
        self.assertTrue(.2 < ref.voltage_spread_pct.median() < 1.5)
        # Each phase reading scatters around the ideal three-phase relation instead of sitting on it.
        ideal = np.hypot(ref.active_power_kw, ref.reactive_power_kvar) * 1000 / (np.sqrt(3) * ref.mean_voltage_v)
        for phase in "abc":
            deviation = ref[f"phase_current_{phase}"] / ideal - 1
            self.assertTrue(.003 < deviation.std() < .02)
        # Power factor and voltage vary, so current is not a fixed multiple of active power.
        ratio = ref.mean_current_a / ref.active_power_kw
        self.assertGreater(ratio.std() / ratio.mean(), .01)

    def test_pressure_head_falls_with_load(self):
        generating = self.derived[self.derived.state == "generating"]
        self.assertLess(generating.penstock_pressure_m.corr(generating.active_power_kw), -.8)
        self.assertTrue(self.derived.penstock_pressure_m.between(95, 113).all())

    def test_events_are_random_spaced_and_after_reference(self):
        trips = set()
        for seed in range(1, 13):
            events = simulate(seed)[1]["events"]
            self.assertTrue(EVENT_COUNT[0] <= len(events) <= EVENT_COUNT[1])
            previous_restart = None
            for event in events:
                start, trip = pd.Timestamp(event["ramp_start"]), pd.Timestamp(event["trip_time"])
                self.assertGreaterEqual(start, pd.Timestamp(self.truth["reference_end_exclusive"]))
                self.assertEqual(trip - start, pd.Timedelta(hours=event["ramp_hours"]))
                self.assertTrue(RAMP_HOURS[0] <= event["ramp_hours"] <= RAMP_HOURS[1])
                self.assertTrue(SEVERITY[0] <= event["severity"] <= SEVERITY[1])
                for key, full in [("winding_rise_delta_c", FULL_WINDING_DELTA_C),
                                  ("current_spread_delta_pct", FULL_CURRENT_SPREAD_DELTA_PCT)]:
                    self.assertTrue(.8 <= event[key] / (event["severity"] * full) <= 1.2)
                if previous_restart is not None:
                    self.assertGreaterEqual(start - previous_restart, pd.Timedelta(hours=MIN_EVENT_GAP_HOURS))
                previous_restart = trip + pd.Timedelta(hours=event["shutdown_hours"])
                trips.add(event["trip_time"])
        self.assertGreater(len(trips), 20)
        self.assertEqual(simulate(5)[1], simulate(5)[1])

    def test_in_memory_simulation_matches_written_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate(root)
            inventory(root)
            read_records(root)
            build(root)
            processed = pd.read_csv(root / "data/processed/scada.csv")
        kept = processed[(processed.record_type == "measurement") & ~processed.requires_review]
        expected = selected_measurements(self.frame)
        self.assertEqual(kept.logical_hour.tolist(), expected.logical_hour.tolist())
        # Files keep four decimals; the in-memory values are unrounded.
        np.testing.assert_allclose(kept[TAGS].to_numpy(), expected[SIGNALS].to_numpy(), rtol=0, atol=5.1e-5)


if __name__ == "__main__":
    unittest.main()
