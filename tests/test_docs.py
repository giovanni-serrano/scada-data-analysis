import json
from pathlib import Path
import re
import unittest

from src.common import spanish

PROJECT = Path(__file__).resolve().parents[1]


class ReadmeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (PROJECT / "README.md").read_text(encoding="utf-8")
        cls.evaluation = json.loads((PROJECT / "reports/evaluation_summary.json").read_text(encoding="utf-8"))

    def test_numbers_come_from_the_evaluation_summary(self):
        results = self.evaluation["evaluation"]
        for method in ("load_ambient", "load", "none"):
            row = results[method]
            low, high = row["ci95"]["detection_rate"]
            self.assertIn(f"{spanish(100 * row['detection_rate'], 0)} %** [" if method == "load_ambient"
                          else f"{spanish(100 * row['detection_rate'], 0)} % [", self.readme)
            self.assertIn(f"[{spanish(100 * low, 0)}; {spanish(100 * high, 0)}]", self.readme)
            self.assertIn(spanish(row["false_alarms_per_1000h"]), self.readme)
            self.assertIn(f"{spanish(row['lead_hours_median'], 0)} h [", self.readme)
        chosen = self.evaluation["operating_point"]
        calibration = next(row for row in self.evaluation["calibration"]
                           if (row["percentile"], row["on_delay_hours"]) == (chosen["percentile"], chosen["on_delay_hours"]))
        self.assertIn(f"el {spanish(100 * calibration['detection_rate'], 0)} %", self.readme)
        self.assertIn(f"({results['load_ambient']['events']} episodios)", self.readme)

    def test_structure_test_count_and_links(self):
        suite = unittest.defaultTestLoader.discover(str(PROJECT / "tests"), top_level_dir=str(PROJECT))
        stated = int(re.search(r"\*\*(\d+) pruebas\*\*", self.readme).group(1))
        self.assertEqual(stated, suite.countTestCases())
        for heading in ("El problema", "Qué hice", "Qué encontré", "Qué aprendí", "Limitaciones", "Cómo reproducirlo"):
            self.assertIn(f"## {heading}", self.readme)
        # One limitations box, and no leftovers from the first version.
        self.assertEqual(len(re.findall(r"^> ", self.readme, flags=re.M)), 1)
        for outdated in ("2042", "50 Hz", "etiqueta didáctica", "muestra comprensión"):
            self.assertNotIn(outdated, self.readme)
        self.assertLess(len(self.readme.splitlines()), 80)
        for target in re.findall(r"\]\((?!https?://)([^)#]+)\)", self.readme):
            self.assertTrue((PROJECT / target).exists(), target)


if __name__ == "__main__":
    unittest.main()
