"""Pruebas automatizadas de los modelos clínicos y del informe PDF.

Ejecución:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest
from datetime import datetime

from utils.adnex_model import (
    CATEGORY_KEYS,
    MALIGNANT_CATEGORIES,
    calculate_adnex,
    calculate_solid_proportion,
)
from utils.case_model import (
    SIDE_LEFT,
    SIDE_OPTIONS,
    SIDE_RIGHT,
    SIDE_UNSPECIFIED,
    build_case_data,
)
from utils.pdf_generator import generate_pdf_report
from utils.simple_rules import (
    CLASSIFICATION_BENIGN,
    CLASSIFICATION_INCONCLUSIVE,
    CLASSIFICATION_MALIGNANT,
    evaluate_simple_rules,
)


class SimpleRulesTests(unittest.TestCase):
    def test_benign_when_only_benign_features(self) -> None:
        result = evaluate_simple_rules({"B1": True, "B3": True}, {})

        self.assertEqual(result.classification, CLASSIFICATION_BENIGN)
        self.assertTrue(result.is_benign)
        self.assertTrue(result.is_conclusive)
        self.assertEqual(result.benign_features, ("B1", "B3"))
        self.assertEqual(result.benign_count, 2)
        self.assertEqual(result.malignant_count, 0)

    def test_malignant_when_only_malignant_features(self) -> None:
        result = evaluate_simple_rules({}, {"M2": True})

        self.assertEqual(result.classification, CLASSIFICATION_MALIGNANT)
        self.assertTrue(result.is_malignant)
        self.assertTrue(result.is_conclusive)
        self.assertEqual(result.malignant_features, ("M2",))

    def test_inconclusive_when_both_feature_sets_present(self) -> None:
        result = evaluate_simple_rules({"B1": True}, {"M1": True})

        self.assertEqual(result.classification, CLASSIFICATION_INCONCLUSIVE)
        self.assertFalse(result.is_conclusive)
        self.assertFalse(result.is_benign)
        self.assertFalse(result.is_malignant)

    def test_inconclusive_when_no_features_present(self) -> None:
        result = evaluate_simple_rules()

        self.assertEqual(result.classification, CLASSIFICATION_INCONCLUSIVE)
        self.assertFalse(result.is_conclusive)
        self.assertEqual(result.benign_count, 0)
        self.assertEqual(result.malignant_count, 0)

    def test_unknown_feature_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            evaluate_simple_rules({"B6": True}, {})
        with self.assertRaises(ValueError):
            evaluate_simple_rules({}, {"M9": True})

    def test_non_boolean_value_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            evaluate_simple_rules({"B1": 1}, {})  # type: ignore[dict-item]


class ADNEXPublishedCasesTests(unittest.TestCase):
    """Casos publicados en la guía práctica del modelo ADNEX."""

    def assert_probabilities(
        self,
        result,
        expected: dict[str, float],
        tolerance: float = 0.001,
    ) -> None:
        for key, value in expected.items():
            self.assertAlmostEqual(
                result.probabilities[key],
                value,
                delta=tolerance,
                msg=f"Categoría {key}",
            )

    def test_published_case_1_with_ca125(self) -> None:
        result = calculate_adnex(
            age=59,
            ca125=153,
            mdl=59,
            pst=1.0,
            tcl=0,
            nps=0,
            sha=0,
            asc=1,
            onc=1,
        )

        self.assertTrue(result.used_ca125)
        self.assert_probabilities(
            result,
            {
                "benign": 0.047,
                "borderline": 0.016,
                "stage_i": 0.046,
                "stage_ii_iv": 0.679,
                "metastatic": 0.212,
            },
        )
        self.assertAlmostEqual(result.malignancy, 0.953, delta=0.001)
        self.assertEqual(result.malignancy_percentage, 95.3)

    def test_published_case_2_with_ca125(self) -> None:
        result = calculate_adnex(
            age=48,
            ca125=22,
            mdl=66,
            pst=27 / 66,
            tcl=0,
            nps=1,
            sha=0,
            asc=0,
            onc=1,
        )

        self.assertTrue(result.used_ca125)
        self.assert_probabilities(
            result,
            {
                "benign": 0.591,
                "borderline": 0.187,
                "stage_i": 0.133,
                "stage_ii_iv": 0.059,
                "metastatic": 0.030,
            },
        )
        self.assertAlmostEqual(result.malignancy, 0.409, delta=0.001)
        self.assertEqual(result.malignancy_percentage, 40.9)

    def test_percentages_are_coherent_and_sum_to_100(self) -> None:
        results = [
            calculate_adnex(
                age=59,
                ca125=153,
                mdl=59,
                pst=1.0,
                tcl=0,
                nps=0,
                sha=0,
                asc=1,
                onc=1,
            ),
            calculate_adnex(
                age=48,
                ca125=22,
                mdl=66,
                pst=27 / 66,
                tcl=0,
                nps=1,
                sha=0,
                asc=0,
                onc=1,
            ),
            calculate_adnex(age=35, mdl=30, pst=0.0, ca125=None),
        ]

        for result in results:
            percentages = result.percentages
            self.assertEqual(round(sum(percentages.values()), 1), 100.0)
            malignant_sum = round(
                sum(percentages[key] for key in MALIGNANT_CATEGORIES), 1
            )
            self.assertEqual(result.malignancy_percentage, malignant_sum)
            self.assertEqual(
                result.malignancy_percentage,
                round(100.0 - percentages["benign"], 1),
            )


class ADNEXInputHandlingTests(unittest.TestCase):
    base_inputs = {
        "age": 50,
        "mdl": 50.0,
        "pst": 0.2,
        "tcl": 0,
        "nps": 0,
        "sha": 0,
        "asc": 0,
        "onc": 0,
        "ca125": 35.0,
    }

    def test_missing_or_non_positive_ca125_uses_without_ca125_equations(self) -> None:
        without_none = calculate_adnex(**{**self.base_inputs, "ca125": None})
        without_zero = calculate_adnex(**{**self.base_inputs, "ca125": 0})
        without_negative = calculate_adnex(**{**self.base_inputs, "ca125": -10})

        for result in (without_none, without_zero, without_negative):
            self.assertFalse(result.used_ca125)
            self.assertIsNone(result.inputs["ca125"])

        for key in CATEGORY_KEYS:
            self.assertAlmostEqual(
                without_none.probabilities[key],
                without_zero.probabilities[key],
                places=12,
            )
            self.assertAlmostEqual(
                without_none.probabilities[key],
                without_negative.probabilities[key],
                places=12,
            )

    def test_nps_is_capped_at_four(self) -> None:
        four = calculate_adnex(**{**self.base_inputs, "nps": 4})
        nine = calculate_adnex(**{**self.base_inputs, "nps": 9})

        self.assertEqual(nine.inputs["nps"], 4.0)
        for key in CATEGORY_KEYS:
            self.assertAlmostEqual(
                four.probabilities[key],
                nine.probabilities[key],
                places=12,
            )

    def test_invalid_clinical_values_are_rejected(self) -> None:
        invalid_cases = [
            {"age": 17},
            {"age": 101},
            {"mdl": 0},
            {"mdl": -5},
            {"pst": -0.01},
            {"pst": 1.01},
            {"tcl": 2},
            {"sha": 0.5},
            {"asc": -1},
            {"onc": 3},
            {"nps": -1},
            {"nps": 2.5},
        ]

        for invalid in invalid_cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    calculate_adnex(**{**self.base_inputs, **invalid})

    def test_non_numeric_values_are_rejected(self) -> None:
        with self.assertRaises(TypeError):
            calculate_adnex(**{**self.base_inputs, "age": "50"})
        with self.assertRaises(TypeError):
            calculate_adnex(**{**self.base_inputs, "ca125": "35"})
        with self.assertRaises(TypeError):
            calculate_adnex(**{**self.base_inputs, "age": True})


class SolidProportionTests(unittest.TestCase):
    """Proporción de tejido sólido a partir de las medidas en milímetros."""

    def test_ratio_of_solid_component_over_lesion_diameter(self) -> None:
        self.assertAlmostEqual(
            calculate_solid_proportion(66.0, 27.0), 27.0 / 66.0, places=12
        )
        self.assertAlmostEqual(
            calculate_solid_proportion(59.0, 59.0), 1.0, places=12
        )
        self.assertAlmostEqual(
            calculate_solid_proportion(50.0, 0.0), 0.0, places=12
        )

    def test_proportion_is_capped_at_one(self) -> None:
        self.assertEqual(calculate_solid_proportion(40.0, 55.0), 1.0)

    def test_invalid_measurements_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            calculate_solid_proportion(0.0, 10.0)
        with self.assertRaises(ValueError):
            calculate_solid_proportion(50.0, -1.0)
        with self.assertRaises(TypeError):
            calculate_solid_proportion("50", 10.0)

    def test_proportion_feeds_the_adnex_model(self) -> None:
        pst = calculate_solid_proportion(66.0, 27.0)
        result = calculate_adnex(
            age=48,
            ca125=22,
            mdl=66,
            pst=pst,
            tcl=0,
            nps=1,
            sha=0,
            asc=0,
            onc=1,
        )

        self.assertAlmostEqual(result.inputs["pst"], 27.0 / 66.0, places=12)
        self.assertAlmostEqual(result.probabilities["benign"], 0.591, delta=0.001)


class CaseDataTests(unittest.TestCase):
    """Datos del caso anonimizado."""

    def test_valid_case_is_built(self) -> None:
        case = build_case_data(
            identifier="  CASO-2026-001  ",
            age=59,
            study_date=datetime(2026, 1, 15).date(),
            side=SIDE_LEFT,
            notes="Lesión quística multilocular.",
        )

        self.assertEqual(case.identifier, "CASO-2026-001")
        self.assertEqual(case.age, 59)
        self.assertEqual(case.side, SIDE_LEFT)
        self.assertTrue(case.has_notes)

    def test_side_options_are_the_expected_clinical_ones(self) -> None:
        self.assertEqual(
            SIDE_OPTIONS, (SIDE_UNSPECIFIED, SIDE_LEFT, SIDE_RIGHT)
        )

    def test_invalid_case_values_are_rejected(self) -> None:
        base = {
            "identifier": "X",
            "age": 50,
            "study_date": datetime(2026, 1, 15).date(),
            "side": SIDE_UNSPECIFIED,
            "notes": "",
        }

        invalid_cases = [
            {"age": 17},
            {"age": 101},
            {"side": "Derecha"},
            {"study_date": datetime(2999, 1, 1).date()},
        ]

        for invalid in invalid_cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    build_case_data(**{**base, **invalid})

    def test_empty_identifier_is_reported(self) -> None:
        case = build_case_data(
            identifier="   ",
            age=50,
            study_date=datetime(2026, 1, 15).date(),
            side=SIDE_UNSPECIFIED,
        )

        self.assertEqual(case.identifier, "")
        self.assertEqual(case.display_identifier, "Sin identificador")
        self.assertFalse(case.has_notes)


class PDFReportTests(unittest.TestCase):
    def _case_data(self) -> object:
        return build_case_data(
            identifier="CASO-2026-001",
            age=59,
            study_date=datetime(2026, 1, 15).date(),
            side=SIDE_UNSPECIFIED,
            notes="Lesión anexial derecha.",
        )

    def test_pdf_with_adnex_is_generated_in_memory(self) -> None:
        simple_rules = evaluate_simple_rules({"B1": True}, {"M1": True})
        adnex = calculate_adnex(
            age=59,
            ca125=153,
            mdl=59,
            pst=1.0,
            tcl=0,
            nps=0,
            sha=0,
            asc=1,
            onc=1,
        )

        pdf = generate_pdf_report(
            case_data=self._case_data(),
            simple_rules=simple_rules,
            adnex=adnex,
            adnex_requested=True,
            evaluation_date=datetime(2026, 1, 15, 10, 30),
        )

        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 3000)

    def test_pdf_without_adnex_is_generated(self) -> None:
        simple_rules = evaluate_simple_rules({"B1": True}, {})

        pdf = generate_pdf_report(
            case_data=self._case_data(),
            simple_rules=simple_rules,
            adnex=None,
            adnex_requested=False,
            evaluation_date=datetime(2026, 1, 15, 10, 30),
        )

        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 3000)

    def test_pdf_without_simple_rules_is_generated(self) -> None:
        pdf = generate_pdf_report(
            case_data=self._case_data(),
            simple_rules=None,
            adnex=None,
            adnex_requested=True,
            evaluation_date=datetime(2026, 1, 15, 10, 30),
        )

        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 3000)


if __name__ == "__main__":
    unittest.main()
