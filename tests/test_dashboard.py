import json
from pathlib import Path
import re
import tempfile
import unittest

from export_dashboard import build_payload, export, verified_evaluation
from run_evaluation import write_outputs
from run_pipeline import run
from src.evaluate import evaluate
from tests.test_docs import OVERCLAIM_PHRASES, REAL_CASE_PHRASES

PROJECT = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        run(cls.root, figures=False)
        # A small evaluation inside the calibration range keeps the test fast and the evaluation seeds untouched.
        cls.evaluation = evaluate([1000, 1001], [1002, 1003, 1004, 1005], resamples=100)
        write_outputs(cls.root, cls.evaluation, with_figures=False)
        cls.payload = export(cls.root, cls.root / "web.json", verify_evaluation=False)

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
                self.assertTrue(all(row["priority"] == 2 for row in ramp if row["alarm_high"]))

    def test_coverage_sensor_and_conservation(self):
        coverage = self.payload["coverage"]
        self.assertEqual(len(coverage), 365)
        self.assertEqual(sum(r["preserved"] for r in coverage), self.payload["quality"]["measurements"])
        self.assertEqual(sum(r["selected"] for r in coverage), self.payload["summary"]["selected_measurements"])
        self.assertTrue(all(r["eligible"] <= r["selected"] for r in coverage))
        self.assertEqual(sum(r["sensor_flat"] for r in self.payload["sensor"]["rows"]), 18)
        # 365 RAW files, the scenario, two interim tables, processed, five report tables and the evaluation summary.
        self.assertEqual(len(self.payload["provenance"]["source_sha256"]), 375)
        self.assertEqual(self.payload["signal_count"], 20)
        self.assertEqual([row["tag"] for row in self.payload["tags"]][:3], ["G1_P", "G1_Q", "G1_IA"])
        self.assertGreater(len(self.payload["relationships"]["pre_event"]), 0)

    def test_evaluation_block_and_alarm_list(self):
        self.assertEqual(self.payload["evaluation"], json.loads(json.dumps(self.evaluation)))
        self.assertEqual([point["tag"] for point in self.payload["alarm_points"]], ["G1_TW_HI", "G1_IUNB_HI", "G1_DEG_HH"])
        self.assertEqual([point["tag"] for point in self.payload["summary"]["alarms"]["after_reference"]["points"]],
                         [point["tag"] for point in self.payload["alarm_points"]])
        self.assertFalse(self.payload["provenance"]["evaluation_recomputed"])

    def test_evaluation_summary_is_recomputed_and_tampering_rejected(self):
        path = self.root / "reports/evaluation_summary.json"
        before = path.read_bytes()
        verified_evaluation(self.root, rerun=True)
        try:
            altered = json.loads(before)
            altered["evaluation"]["load_ambient"]["detection_rate"] = 1.0
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from regeneration"):
                verified_evaluation(self.root, rerun=True)
        finally:
            path.write_bytes(before)

    def test_export_deterministic_and_finite(self):
        export(self.root, self.root / "other.json", verify_evaluation=False)
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
                build_payload(self.root, verify_evaluation=False)
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
                build_payload(self.root, verify_evaluation=False)
        finally:
            processed.write_bytes(before)


class PublishedSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (PROJECT / "docs/index.html").read_text(encoding="utf-8")
        cls.script = (PROJECT / "docs/app.js").read_text(encoding="utf-8")
        cls.published = json.loads((PROJECT / "docs/assets/dashboard-data.json").read_text(encoding="utf-8"))

    def test_texts_are_current_and_scope_is_stated_once(self):
        for text in (self.html, self.script):
            for outdated in ("2042", "50 Hz", "ficticio", "etiqueta didáctica"):
                self.assertNotIn(outdated, text)
            for hedge in ("no demuestra", "no acredita", "no prueba", "no constituye"):
                self.assertNotIn(hedge, text)
            for phrase in REAL_CASE_PHRASES + OVERCLAIM_PHRASES + ("años simulados",):
                self.assertNotIn(phrase, text.lower())
        self.assertEqual(self.html.count("scope-note"), 1)
        self.assertLessEqual(self.html.lower().count("sintétic"), 3)
        self.assertIn("60 Hz", self.html)
        self.assertEqual(self.html.count('role="tab"'), 6)
        # The summary tab holds placeholders only: every result it shows is computed by app.js from the published JSON.
        summary = self.html[self.html.index('<section id="resumen"'):self.html.index('<section id="variables"')]
        visible = re.sub(r"<[^>]+>", " ", summary)
        primary = self.published["evaluation"]["evaluation"]["load_ambient"]
        fixed = self.published["evaluation"]["evaluation"]["none"]
        for figure in (f"{round(100 * primary['detection_rate'])} de cada", f"{round(100 * fixed['detection_rate'])} de cada",
                       f"{primary['false_alarms_per_1000h']:.2f}".replace(".", ","), f"{primary['lead_hours_median']:.0f} h",
                       str(primary["events"]), f"{round(100 * primary['by_severity'][0]['detection_rate'])} %"):
            self.assertNotIn(figure, visible)
        self.assertIn("mismo tipo que busca el detector", visible)
        for target in ("result-detection", "result-false", "result-lead", "result-basis", "findings-detail"):
            self.assertRegex(summary, rf'id="{target}"[^>]*>—<')
            self.assertIn(f'$("{target}")', self.script)
        for field in ("primary.detection_rate", "fixed.detection_rate", "primary.false_alarms_per_1000h", "primary.lead_hours_median",
                      "primary.events", "bands[0].detection_rate"):
            self.assertIn(field, self.script)

    def test_every_element_the_script_fills_exists(self):
        declared = set(re.findall(r'id="([^"]+)"', self.html))
        used = set(re.findall(r'\$\("([a-z0-9-]+)"\)', self.script))
        self.assertGreater(len(used), 30)
        self.assertFalse(used - declared)
        for target in re.findall(r'data-(?:chart|reset|zoom)="([^"]+)"', self.html):
            self.assertIn(target, declared)

    def test_published_data_matches_the_reports(self):
        reports = PROJECT / "reports"
        evaluation = json.loads((reports / "evaluation_summary.json").read_text(encoding="utf-8"))
        analysis = json.loads((reports / "analysis_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(self.published["schema_version"], 2)
        self.assertEqual(self.published["evaluation"], evaluation)
        self.assertTrue(self.published["provenance"]["evaluation_recomputed"])
        self.assertEqual(self.published["summary"], {key: value for key, value in analysis.items() if key != "events"})
        self.assertEqual([event["lead_hours"] for event in self.published["events"]],
                         [event["lead_hours"] for event in analysis["events"]])
