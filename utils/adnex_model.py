"""Modelo ADNEX (Assessment of Different NEoplasias in the adneXa).

Implementación de las ecuaciones multinomiales oficiales publicadas por el
grupo IOTA. El modelo estima la probabilidad de cinco categorías:

1. Tumor benigno.
2. Tumor borderline (limítrofe).
3. Carcinoma invasivo en estadio I.
4. Carcinoma invasivo en estadio II-IV.
5. Enfermedad metastásica.

El Riesgo de Malignidad (RM) es la suma de las cuatro categorías malignas
(borderline, estadio I, estadio II-IV y metastásica).

Fuentes de los coeficientes:
    Van Calster B, et al. A risk model for the diagnosis of ovarian cancer
    (ADNEX model). BMJ. 2014;349:g5920. doi:10.1136/bmj.g5920 (Apéndice D).

    Van Calster B, et al. Validation of the ADNEX model with and without
    CA-125. BMJ. 2020;370:m2614. doi:10.1136/bmj.m2614 (apéndice web,
    ecuaciones sin CA-125).

La categoría "número de proyecciones papilares" se codifica de 0 a 4, donde
4 representa "cuatro o más" proyecciones. Valores superiores se limitan a 4.
La proporción de tejido sólido (``pst``) se expresa como fracción de 0 a 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

CATEGORY_KEYS: tuple[str, ...] = (
    "benign",
    "borderline",
    "stage_i",
    "stage_ii_iv",
    "metastatic",
)

CATEGORY_LABELS: dict[str, str] = {
    "benign": "Benigno",
    "borderline": "Tumor borderline (limítrofe)",
    "stage_i": "Carcinoma invasivo estadio I",
    "stage_ii_iv": "Carcinoma invasivo estadio II-IV",
    "metastatic": "Enfermedad metastásica",
}

MALIGNANT_CATEGORIES: tuple[str, ...] = (
    "borderline",
    "stage_i",
    "stage_ii_iv",
    "metastatic",
)


@dataclass(frozen=True)
class ADNEXResult:
    """Resultado del modelo ADNEX con probabilidades y datos de auditoría."""

    probabilities: Mapping[str, float]
    z_scores: tuple[float, float, float, float]
    inputs: Mapping[str, float | None]
    used_ca125: bool

    @property
    def malignancy(self) -> float:
        """Riesgo de malignidad como probabilidad entre 0 y 1."""
        return sum(self.probabilities[key] for key in MALIGNANT_CATEGORIES)

    @property
    def percentages(self) -> dict[str, float]:
        """Porcentajes redondeados a un decimal que suman exactamente 100.0."""
        units = _allocate_percentage_units(
            [self.probabilities[key] for key in CATEGORY_KEYS]
        )
        return {
            key: unit / 10.0 for key, unit in zip(CATEGORY_KEYS, units)
        }

    @property
    def malignancy_percentage(self) -> float:
        """Riesgo de malignidad coherente con los porcentajes por categoría."""
        return round(100.0 - self.percentages["benign"], 1)

    @property
    def equation_set_label(self) -> str:
        return "Con CA-125" if self.used_ca125 else "Sin CA-125"

    def probability(self, category: str) -> float:
        return self.probabilities[category]

    def percentage(self, category: str) -> float:
        return self.percentages[category]


def _as_finite_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"'{name}' debe ser un número.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"'{name}' debe ser un número finito.")
    return number


def _as_flag(value: object, name: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)) and float(value) in (0.0, 1.0):
        return int(value)
    raise ValueError(f"'{name}' debe valer 0 o 1.")


def _validate_inputs(
    *,
    age: object,
    mdl: object,
    pst: object,
    tcl: object,
    nps: object,
    sha: object,
    asc: object,
    onc: object,
    ca125: object,
) -> tuple[float, float, float, int, int, int, int, int, float | None]:
    age_value = _as_finite_float(age, "age")
    if not 18.0 <= age_value <= 100.0:
        raise ValueError("'age' debe estar entre 18 y 100 años.")

    mdl_value = _as_finite_float(mdl, "mdl")
    if mdl_value <= 0.0:
        raise ValueError("'mdl' (diámetro máximo de la lesión) debe ser > 0 mm.")

    pst_value = _as_finite_float(pst, "pst")
    if not 0.0 <= pst_value <= 1.0:
        raise ValueError("'pst' (proporción de tejido sólido) debe estar entre 0 y 1.")

    tcl_value = _as_flag(tcl, "tcl")
    sha_value = _as_flag(sha, "sha")
    asc_value = _as_flag(asc, "asc")
    onc_value = _as_flag(onc, "onc")

    nps_value = _as_finite_float(nps, "nps")
    if not nps_value.is_integer():
        raise ValueError("'nps' debe ser un número entero de proyecciones papilares.")
    if nps_value < 0.0:
        raise ValueError("'nps' no puede ser negativo.")
    # El modelo agrupa "cuatro o más" proyecciones papilares en una sola
    # categoría; por ello el valor se limita superiormente a 4.
    nps_value_int = min(int(nps_value), 4)

    ca125_value: float | None
    if ca125 is None:
        ca125_value = None
    else:
        ca125_value = _as_finite_float(ca125, "ca125")
        # Un valor no disponible o no positivo activa las ecuaciones sin CA-125.
        if ca125_value <= 0.0:
            ca125_value = None

    return (
        age_value,
        mdl_value,
        pst_value,
        tcl_value,
        nps_value_int,
        sha_value,
        asc_value,
        onc_value,
        ca125_value,
    )


def _z_scores_with_ca125(
    *,
    age: float,
    log2_mdl: float,
    log2_ca125: float,
    pst: float,
    tcl: int,
    nps: int,
    sha: int,
    asc: int,
    onc: int,
) -> tuple[float, float, float, float]:
    pst2 = pst * pst

    z1 = (
        -7.577663
        + 0.004506 * age
        + 0.111642 * log2_ca125
        + 0.372046 * log2_mdl
        + 6.967853 * pst
        - 5.65588 * pst2
        + 1.375079 * tcl
        + 0.604238 * nps
        - 2.04157 * sha
        + 0.971061 * asc
        + 0.953043 * onc
    )
    z2 = (
        -12.276041
        + 0.017260 * age
        + 0.197249 * log2_ca125
        + 0.873530 * log2_mdl
        + 9.583053 * pst
        - 5.83319 * pst2
        + 0.791873 * tcl
        + 0.400369 * nps
        - 1.87763 * sha
        + 0.452731 * asc
        + 0.452484 * onc
    )
    z3 = (
        -14.915830
        + 0.051239 * age
        + 0.765456 * log2_ca125
        + 0.430477 * log2_mdl
        + 10.37696 * pst
        - 5.70975 * pst2
        + 0.273692 * tcl
        + 0.389874 * nps
        - 2.35516 * sha
        + 1.348408 * asc
        + 0.459021 * onc
    )
    z4 = (
        -11.909267
        + 0.033601 * age
        + 0.276166 * log2_ca125
        + 0.449025 * log2_mdl
        + 6.644939 * pst
        - 2.30330 * pst2
        + 0.899980 * tcl
        + 0.215645 * nps
        - 2.49845 * sha
        + 1.636407 * asc
        + 0.808887 * onc
    )

    return (z1, z2, z3, z4)


def _z_scores_without_ca125(
    *,
    age: float,
    log2_mdl: float,
    pst: float,
    tcl: int,
    nps: int,
    sha: int,
    asc: int,
    onc: int,
) -> tuple[float, float, float, float]:
    pst2 = pst * pst

    z1 = (
        -7.412534
        + 0.003489 * age
        + 0.430701 * log2_mdl
        + 7.117925 * pst
        - 5.74135 * pst2
        + 1.343699 * tcl
        + 0.607211 * nps
        - 2.11885 * sha
        + 1.167767 * asc
        + 0.983227 * onc
    )
    z2 = (
        -12.201607
        + 0.017607 * age
        + 0.98728 * log2_mdl
        + 10.07145 * pst
        - 6.17742 * pst2
        + 0.763081 * tcl
        + 0.410449 * nps
        - 1.98073 * sha
        + 0.77054 * asc
        + 0.543677 * onc
    )
    z3 = (
        -12.826207
        + 0.045172 * age
        + 0.759002 * log2_mdl
        + 11.83296 * pst
        - 6.64336 * pst2
        + 0.316444 * tcl
        + 0.390959 * nps
        - 2.94082 * sha
        + 2.691276 * asc
        + 0.929483 * onc
    )
    z4 = (
        -11.424379
        + 0.033407 * age
        + 0.560396 * log2_mdl
        + 7.264105 * pst
        - 2.77392 * pst2
        + 0.983394 * tcl
        + 0.199164 * nps
        - 2.63702 * sha
        + 2.185574 * asc
        + 0.906249 * onc
    )

    return (z1, z2, z3, z4)


def _softmax_five(z_scores: tuple[float, float, float, float]) -> dict[str, float]:
    """Softmax estable para la categoría de referencia (benigno, z0 = 0)."""

    logits = (0.0, *z_scores)
    maximum = max(logits)
    exponentials = [math.exp(value - maximum) for value in logits]
    total = sum(exponentials)
    probabilities = [value / total for value in exponentials]

    return dict(zip(CATEGORY_KEYS, probabilities))


def _allocate_percentage_units(
    probabilities: list[float], decimals: int = 1
) -> list[int]:
    """Reparte unidades porcentuales con el método del mayor resto.

    Garantiza que la suma de los porcentajes publicados sea exactamente
    100.0 (o 100 con la precisión solicitada), evitando inconsistencias por
    redondeo independiente de cada categoría.
    """

    total_units = 100 * (10**decimals)
    raw_units = [max(probability, 0.0) * total_units for probability in probabilities]
    units = [int(math.floor(value)) for value in raw_units]

    remaining = total_units - sum(units)
    if remaining > 0:
        # A mayor resto, mayor prioridad. El índice desempata de forma estable.
        order = sorted(
            range(len(raw_units)),
            key=lambda index: (raw_units[index] - units[index], -index),
            reverse=True,
        )
        for index in order[:remaining]:
            units[index] += 1

    return units


def calculate_adnex(
    *,
    age: float,
    mdl: float,
    pst: float,
    tcl: int = 0,
    nps: int = 0,
    sha: int = 0,
    asc: int = 0,
    onc: int = 0,
    ca125: float | None = None,
) -> ADNEXResult:
    """Calcula las probabilidades del modelo ADNEX.

    Args:
        age: Edad de la paciente en años (18-100).
        mdl: Mayor diámetro de la lesión en milímetros (> 0).
        pst: Proporción de tejido sólido, de 0 a 1. Se obtiene con
            :func:`calculate_solid_proportion` a partir del mayor diámetro del
            componente sólido y del mayor diámetro de la lesión.
        tcl: Más de 10 lóculos (0/1).
        nps: Número de proyecciones papilares. Se limita a 4 ("4 o más").
        sha: Sombras acústicas (0/1).
        asc: Ascitis (0/1).
        onc: Evaluación en centro oncológico (0/1).
        ca125: CA-125 sérico en U/mL. ``None`` o un valor <= 0 activa las
            ecuaciones sin CA-125.

    Returns:
        ``ADNEXResult`` con probabilidades, porcentajes coherentes, puntuaciones
        z y los datos normalizados utilizados.

    Raises:
        TypeError: Si un valor numérico tiene un tipo inválido.
        ValueError: Si un valor está fuera del rango clínicamente definido.
    """

    (
        age_value,
        mdl_value,
        pst_value,
        tcl_value,
        nps_value,
        sha_value,
        asc_value,
        onc_value,
        ca125_value,
    ) = _validate_inputs(
        age=age,
        mdl=mdl,
        pst=pst,
        tcl=tcl,
        nps=nps,
        sha=sha,
        asc=asc,
        onc=onc,
        ca125=ca125,
    )

    log2_mdl = math.log2(mdl_value)

    if ca125_value is None:
        z_scores = _z_scores_without_ca125(
            age=age_value,
            log2_mdl=log2_mdl,
            pst=pst_value,
            tcl=tcl_value,
            nps=nps_value,
            sha=sha_value,
            asc=asc_value,
            onc=onc_value,
        )
    else:
        z_scores = _z_scores_with_ca125(
            age=age_value,
            log2_mdl=log2_mdl,
            log2_ca125=math.log2(ca125_value),
            pst=pst_value,
            tcl=tcl_value,
            nps=nps_value,
            sha=sha_value,
            asc=asc_value,
            onc=onc_value,
        )

    probabilities = _softmax_five(z_scores)

    return ADNEXResult(
        probabilities=probabilities,
        z_scores=z_scores,
        inputs={
            "age": age_value,
            "mdl": mdl_value,
            "pst": pst_value,
            "tcl": float(tcl_value),
            "nps": float(nps_value),
            "sha": float(sha_value),
            "asc": float(asc_value),
            "onc": float(onc_value),
            "ca125": ca125_value,
        },
        used_ca125=ca125_value is not None,
    )


def calculate_solid_proportion(
    lesion_diameter: float,
    solid_diameter: float,
) -> float:
    """Calcula la proporción de tejido sólido (``pst``).

    La proporción de tejido sólido se define, tal como en la calculadora
    oficial de IOTA, como el cociente entre el mayor diámetro del componente
    sólido y el mayor diámetro de la lesión.

    Args:
        lesion_diameter: Mayor diámetro de la lesión en milímetros (> 0).
        solid_diameter: Mayor diámetro del componente sólido en milímetros
            (>= 0).

    Returns:
        La proporción como fracción de 0 a 1. Si el componente sólido supera
        el diámetro de la lesión (medición inconsistente), se limita a 1.

    Raises:
        TypeError: Si algún valor no es numérico.
        ValueError: Si el diámetro de la lesión no es positivo o el
            componente sólido es negativo.
    """

    mdl_value = _as_finite_float(lesion_diameter, "lesion_diameter")
    if mdl_value <= 0.0:
        raise ValueError(
            "'lesion_diameter' (mayor diámetro de la lesión) debe ser > 0 mm."
        )

    solid_value = _as_finite_float(solid_diameter, "solid_diameter")
    if solid_value < 0.0:
        raise ValueError(
            "'solid_diameter' (mayor diámetro del componente sólido) no puede "
            "ser negativo."
        )

    return min(solid_value / mdl_value, 1.0)


__all__ = [
    "ADNEXResult",
    "CATEGORY_KEYS",
    "CATEGORY_LABELS",
    "MALIGNANT_CATEGORIES",
    "calculate_adnex",
    "calculate_solid_proportion",
]
