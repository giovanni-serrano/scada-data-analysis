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

    def test_exact_windows_counts_and_numeric_summary(self):
        for hours, alerts in [(72, 31), (24, 21), (6, 6)]:
            rows = [r for r in self.payload["timeline"] if -hours <= r["hours_to_event"] < 0]
            period = next(p for p in self.payload["summary"]["periods"] if p["period"] == f"pre_event_{hours}h")
            self.assertEqual(len(rows), hours)
            self.assertEqual(sum(r["eligible"] for r in rows), period["eligible_hours"])
            self.assertEqual(sum(r["persistent_alert"] for r in rows), alerts)
            self.assertEqual(alerts, period["persistent_alert_hours"])
        self.assertEqual(self.payload["summary"]["lead_hours"], 34)
        self.assertEqual(max(r["hours_to_event"] for r in rows), -1)

    def test_coverage_sensor_and_conservation(self):
        coverage = self.payload["coverage"]
        self.assertEqual(len(coverage), 365)
        self.assertEqual(sum(r["preserved"] for r in coverage), 8754)
        self.assertEqual(sum(r["selected"] for r in coverage), 8740)
        self.assertTrue(all(r["eligible"] <= r["selected"] for r in coverage))
        self.assertEqual(sum(r["sensor_flat"] for r in self.payload["sensor"]["rows"]), 18)
        self.assertEqual(len(self.payload["provenance"]["source_sha256"]), 373)
        self.assertEqual(self.payload["signal_count"], 20)
        self.assertEqual(len(self.payload["relationships"]["pre_event"]), 72)

    def test_export_deterministic_and_finite(self):
        export(self.root, self.root / "other.json")
        original = (self.root / "web.json").read_bytes()
        self.assertEqual(original, (self.root / "other.json").read_bytes())
        decoded = json.loads(original, parse_constant=lambda value: self.fail(value))
        for row in decoded["relationships"]["reference"]:
            self.assertGreater(row["phase_current_a"], 0)
            self.assertGreater(row["active_power_kw"], 0)
        # Stopped observations retain undefined relative dispersion as null.
        self.assertTrue(any(r["current_spread_pct"] is None for r in decoded["timeline"]))

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
            processed.write_bytes(before.replace(b"74.2500", b"75.2500", 1))
            with self.assertRaisesRegex(ValueError, "differs from synthetic regeneration"):
                build_payload(self.root)
        finally:
            processed.write_bytes(before)
