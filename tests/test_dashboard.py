import json
from pathlib import Path
import tempfile
import unittest

from export_dashboard import build_payload, export
from run_pipeline import run


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        run(cls.root, figures=False)
        cls.payload = export(cls.root, cls.root / "web.json")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_event_timelines_match_python_scoring(self):
        truth = json.loads((self.root / "data/synthetic_scenario.json").read_text(encoding="utf-8"))
        self.assertEqual(self.payload["schema_version"], 2)
        self.assertEqual([e["trip_time"] for e in self.payload["events"]], [e["trip_time"] for e in truth["events"]])
        self.assertNotIn("events", self.payload["summary"])
        for event in self.payload["events"]:
            hours = [row["hours_to_trip"] for row in event["timeline"]]
            self.assertEqual(max(hours), -1)
            self.assertGreaterEqual(min(hours), -event["ramp_hours"] - 24)
            ramp = [row for row in event["timeline"] if row["hours_to_trip"] >= -event["ramp_hours"]]
            self.assertEqual(sum(row["alarm_high"] for row in ramp), event["alarm_high_hours"])
            self.assertEqual(sum(row["eligible"] for row in ramp), event["eligible_hours"])
            if event["detected"]:
                first = min(row["hours_to_trip"] for row in ramp if row["alarm_high"])
                self.assertEqual(-first, event["lead_hours"])

    def test_coverage_sensor_and_conservation(self):
        coverage = self.payload["coverage"]
        self.assertEqual(len(coverage), 365)
        self.assertEqual(sum(r["preserved"] for r in coverage), self.payload["quality"]["measurements"])
        self.assertEqual(sum(r["selected"] for r in coverage), self.payload["summary"]["selected_measurements"])
        self.assertTrue(all(r["eligible"] <= r["selected"] for r in coverage))
        self.assertEqual(sum(r["sensor_flat"] for r in self.payload["sensor"]["rows"]), 18)
        # 365 RAW files, the scenario, two interim tables, processed and five report tables.
        self.assertEqual(len(self.payload["provenance"]["source_sha256"]), 374)
        self.assertEqual(self.payload["signal_count"], 20)
        self.assertEqual([row["tag"] for row in self.payload["tags"]][:3], ["G1_P", "G1_Q", "G1_IA"])
        self.assertGreater(len(self.payload["relationships"]["pre_event"]), 0)

    def test_export_deterministic_and_finite(self):
        export(self.root, self.root / "other.json")
        original = (self.root / "web.json").read_bytes()
        self.assertEqual(original, (self.root / "other.json").read_bytes())
        decoded = json.loads(original, parse_constant=lambda value: self.fail(value))
        for row in decoded["relationships"]["reference"]:
            self.assertGreater(row["phase_current_a"], 0)
            self.assertGreater(row["active_power_kw"], 0)

    def test_untrusted_manifest_rejected(self):
        manifest = self.root / "data/synthetic_scenario.json"
        before = manifest.read_bytes()
        try:
            truth = json.loads(before)
            truth["synthetic_only"] = False
            manifest.write_text(json.dumps(truth), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "synthetic scenario"):
                build_payload(self.root)
        finally:
            manifest.write_bytes(before)

    def test_modified_processed_values_rejected(self):
        processed = self.root / "data/processed/scada.csv"
        before = processed.read_bytes()
        try:
            truth = json.loads((self.root / "data/synthetic_scenario.json").read_text(encoding="utf-8"))
            held = f"{truth['frozen_sensor']['value']:.4f}".encode()
            processed.write_bytes(before.replace(held, b"99.9999", 1))
            with self.assertRaisesRegex(ValueError, "differs from synthetic regeneration"):
                build_payload(self.root)
        finally:
            processed.write_bytes(before)
