"""Reglas simples IOTA (IOTA Simple Rules) para masas anexiales.

Las reglas simples clasifican una masa anexial a partir de la presencia de
hallazgos benignos (B) y malignos (M):

* Benigno: al menos un hallazgo B y ningún hallazgo M.
* Maligno: al menos un hallazgo M y ningún hallazgo B.
* Inconcluso: cualquier otra combinación (incluida la ausencia de hallazgos).

Referencia principal:
    Timmerman D, et al. Simple ultrasound-based rules for the diagnosis of
    ovarian cancer. Ultrasound Obstet Gynecol. 2008;31(6):681-690.
    doi:10.1002/uog.5365

    Timmerman D, et al. Terms, definitions and measurements to describe the
    sonographic features of adnexal tumors: a consensus opinion from the
    International Ovarian Tumor Analysis (IOTA) group. Ultrasound Obstet
    Gynecol. 2000;16(5):500-505.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

CLASSIFICATION_BENIGN = "Benigno"
CLASSIFICATION_MALIGNANT = "Maligno"
CLASSIFICATION_INCONCLUSIVE = "Inconclusivo / Indeterminado"

# Los diccionarios conservan el orden oficial B1-B5 y M1-M5. Las etiquetas se
# usan tanto en la interfaz como en el informe PDF.
BENIGN_FEATURE_LABELS: dict[str, str] = {
    "B1": "Quiste unilocular",
    "B2": "Componente sólido < 7 mm",
    "B3": "Sombras acústicas",
    "B4": "Tumor multilocular liso < 100 mm",
    "B5": "Sin flujo Doppler color (puntuación 1)",
}

MALIGNANT_FEATURE_LABELS: dict[str, str] = {
    "M1": "Tumor sólido irregular",
    "M2": "Ascitis",
    "M3": "Al menos 4 proyecciones papilares",
    "M4": "Tumor multilocular sólido irregular >= 100 mm",
    "M5": "Flujo Doppler color muy intenso (puntuación 4)",
}


@dataclass(frozen=True)
class SimpleRulesResult:
    """Resultado estructurado de la aplicación de las reglas simples IOTA."""

    benign_features: tuple[str, ...]
    malignant_features: tuple[str, ...]

    @property
    def benign_count(self) -> int:
        return len(self.benign_features)

    @property
    def malignant_count(self) -> int:
        return len(self.malignant_features)

    @property
    def classification(self) -> str:
        if self.benign_count > 0 and self.malignant_count == 0:
            return CLASSIFICATION_BENIGN
        if self.malignant_count > 0 and self.benign_count == 0:
            return CLASSIFICATION_MALIGNANT
        return CLASSIFICATION_INCONCLUSIVE

    @property
    def is_benign(self) -> bool:
        return self.classification == CLASSIFICATION_BENIGN

    @property
    def is_malignant(self) -> bool:
        return self.classification == CLASSIFICATION_MALIGNANT

    @property
    def is_conclusive(self) -> bool:
        return self.is_benign or self.is_malignant

    @property
    def summary(self) -> str:
        return (
            f"{self.classification}: {self.benign_count} hallazgo(s) B y "
            f"{self.malignant_count} hallazgo(s) M."
        )


def _validate_flags(flags: Mapping[str, bool], known: Mapping[str, str], name: str) -> None:
    if not isinstance(flags, Mapping):
        raise TypeError(f"'{name}' debe ser un diccionario de hallazgos.")

    unknown = sorted(set(flags) - set(known))
    if unknown:
        raise ValueError(
            f"Hallazgo(s) desconocido(s) en '{name}': {', '.join(unknown)}. "
            f"Valores permitidos: {', '.join(known)}."
        )

    invalid = [code for code, value in flags.items() if not isinstance(value, bool)]
    if invalid:
        raise TypeError(
            f"Los valores de '{name}' deben ser booleanos. "
            f"Hallazgo(s) con tipo inválido: {', '.join(sorted(invalid))}."
        )


def evaluate_simple_rules(
    benign: Mapping[str, bool] | None = None,
    malignant: Mapping[str, bool] | None = None,
) -> SimpleRulesResult:
    """Aplica las reglas simples IOTA.

    Args:
        benign: Diccionario con claves B1-B5 y valores booleanos. Las claves
            ausentes se consideran ``False``.
        malignant: Diccionario con claves M1-M5 y valores booleanos. Las claves
            ausentes se consideran ``False``.

    Returns:
        ``SimpleRulesResult`` con los hallazgos presentes y la clasificación.

    Raises:
        TypeError: Si los valores no son booleanos o los argumentos no son
            diccionarios.
        ValueError: Si se recibe una clave de hallazgo desconocida.
    """

    benign_flags = {} if benign is None else benign
    malignant_flags = {} if malignant is None else malignant

    _validate_flags(benign_flags, BENIGN_FEATURE_LABELS, "benign")
    _validate_flags(malignant_flags, MALIGNANT_FEATURE_LABELS, "malignant")

    benign_features = tuple(
        code for code in BENIGN_FEATURE_LABELS if benign_flags.get(code, False)
    )
    malignant_features = tuple(
        code for code in MALIGNANT_FEATURE_LABELS if malignant_flags.get(code, False)
    )

    return SimpleRulesResult(
        benign_features=benign_features,
        malignant_features=malignant_features,
    )


__all__ = [
    "BENIGN_FEATURE_LABELS",
    "MALIGNANT_FEATURE_LABELS",
    "CLASSIFICATION_BENIGN",
    "CLASSIFICATION_MALIGNANT",
    "CLASSIFICATION_INCONCLUSIVE",
    "SimpleRulesResult",
    "evaluate_simple_rules",
]
