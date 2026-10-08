import json
from pathlib import Path
import re
import unittest

from src.common import spanish

PROJECT = Path(__file__).resolve().parents[1]
# Wording that would tie the project to a real plant or incident.
REAL_CASE_PHRASES = ("familiarización", "fallo real", "primer acercamiento", "el informe", "de la planta",
                     "no puedo publicar", "parecidos, pero no iguales", "en el rotor y", "se dañara el generador",
                     "material privado")


class ReadmeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (PROJECT / "README.md").read_text(encoding="utf-8")
        cls.methodology = (PROJECT / "METODOLOGIA.md").read_text(encoding="utf-8")
        cls.evaluation = json.loads((PROJECT / "reports/evaluation_summary.json").read_text(encoding="utf-8"))

    def test_numbers_come_from_the_evaluation_summary(self):
        results, protocol = self.evaluation["evaluation"], self.evaluation["protocol"]
        primary, fixed = results["load_ambient"], results["none"]
        percent = lambda value: spanish(100 * value, 0)
        # README: the three plain-language results and what they were measured on.
        for text in (f"{len(protocol['evaluation_seeds'])} simulaciones de un año ({primary['events']} degradaciones)",
                     f"Avisó en {percent(primary['detection_rate'])} de cada 100 degradaciones",
                     f"Un umbral fijo avisó en {percent(fixed['detection_rate'])} de cada 100",
                     f"{spanish(primary['false_alarms_per_1000h'])} falsas alarmas por cada 1000 h",
                     f"unas {spanish(primary['false_alarms_per_1000h'] * 8.76, 0)} al año",
                     f"{spanish(primary['lead_hours_median'], 0)} h o más antes del disparo",
                     f"el {percent(primary['by_severity'][0]['detection_rate'])} % de las más leves",
                     f"el {percent(primary['by_severity'][-1]['detection_rate'])} % de las más fuertes",
                     f"Ajusté la alarma con {len(protocol['calibration_seeds'])} simulaciones de un año y la medí una sola vez en otras {len(protocol['evaluation_seeds'])}"):
            self.assertIn(text, self.readme)
        # Methodology: the full table with intervals, the comparison and the calibration figure.
        for row in results.values():
            ci = row["ci95"]
            self.assertIn(f"| {percent(row['detection_rate'])} % [{percent(ci['detection_rate'][0])}; {percent(ci['detection_rate'][1])}] "
                          f"| {row['detected']}/{row['events']} "
                          f"| {spanish(row['false_alarms_per_1000h'])} [{spanish(ci['false_alarms_per_1000h'][0])}; {spanish(ci['false_alarms_per_1000h'][1])}] "
                          f"| {spanish(row['lead_hours_median'], 0)} h [{spanish(ci['lead_hours_median'][0], 0)}; {spanish(ci['lead_hours_median'][1], 0)}] "
                          f"| {spanish(row['lead_hours_p10'], 0)}–{spanish(row['lead_hours_p90'], 0)} h |", self.methodology)
        gap = self.evaluation["primary_minus_baseline"]
        low, high = gap["ci95"]["detection_rate"]
        self.assertIn(f"detecta {percent(gap['detection_rate'])} puntos más que el umbral fijo (IC 95 %: {percent(low)} a {percent(high)})",
                      self.methodology)
        self.assertIn(", ".join(f"{percent(band['detection_rate'])} %" for band in primary["by_severity"][:-1])
                      + f" y {percent(primary['by_severity'][-1]['detection_rate'])} %", self.methodology)
        chosen = self.evaluation["operating_point"]
        calibration = next(row for row in self.evaluation["calibration"]
                           if (row["percentile"], row["on_delay_hours"]) == (chosen["percentile"], chosen["on_delay_hours"]))
        self.assertIn(f"detectaba el {percent(calibration['detection_rate'])} %", self.methodology)
        self.assertIn(f"hasta el {percent(primary['detection_rate'])} %", self.methodology)
        self.assertIn(f"**percentil {chosen['percentile']} con {chosen['on_delay_hours']} h**", self.methodology)
        self.assertIn(f"remuestrear* simulaciones completas {protocol['bootstrap_resamples']} veces", self.methodology)
        self.assertIn(f"Por eso se usan {len(protocol['evaluation_seeds'])} simulaciones de un año para medir ({primary['events']} fallas en total)",
                      self.methodology)
        deadband = protocol["deadband"]
        self.assertIn(f"baja {spanish(deadband['winding_rise_c'], 1)} °C (elevación térmica) o {spanish(deadband['current_spread_pct'], 1)} puntos",
                      self.methodology)

    def test_structure_test_count_and_links(self):
        suite = unittest.defaultTestLoader.discover(str(PROJECT / "tests"), top_level_dir=str(PROJECT))
        stated = int(re.search(r"\*\*(\d+) pruebas\*\*", self.readme).group(1))
        self.assertEqual(stated, suite.countTestCases())
        headings = re.findall(r"^## (.+)$", self.readme, flags=re.M)
        self.assertEqual(headings[:7], ["El problema", "Por qué es difícil", "Qué hice", "Qué encontré",
                                        "Limitaciones", "Qué sigue", "Para profundizar"])
        # The case study reads in about two minutes; the jargon lives in the methodology glossary.
        story = self.readme.split("## Para profundizar")[0]
        self.assertLess(len(re.findall(r"\w+", story)), 560)
        for term in ("percentil", "ic 95", "bootstrap", "remuestreo", "calibración"):
            self.assertNotIn(term, story.lower())
            self.assertIn(term, self.methodology.lower())
        self.assertIn("## Glosario", self.methodology)
        # One limitations box, and no leftovers from earlier versions.
        self.assertEqual(len(re.findall(r"^> ", self.readme, flags=re.M)), 1)
        for outdated in ("2042", "50 Hz", "etiqueta didáctica", "muestra comprensión"):
            self.assertNotIn(outdated, self.readme + self.methodology)
        # A general framing only: nothing may point to a specific plant, incident or report.
        reports = "".join((PROJECT / "reports" / name).read_text(encoding="utf-8") for name in ("verification.md", "evaluation.md"))
        for phrase in REAL_CASE_PHRASES:
            self.assertNotIn(phrase, (self.readme + self.methodology + reports).lower())
        self.assertNotIn("años simulados", self.readme + self.methodology + reports)
        self.assertLess(len(self.readme.splitlines()), 80)
        for document in ("README.md", "METODOLOGIA.md"):
            text = (PROJECT / document).read_text(encoding="utf-8")
            for target in re.findall(r"\]\((?!https?://)([^)#]+)\)", text):
                self.assertTrue((PROJECT / target).exists(), f"{document}: {target}")


if __name__ == "__main__":
    unittest.main()
