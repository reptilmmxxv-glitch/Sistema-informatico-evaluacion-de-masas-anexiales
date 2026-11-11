"""Interfaz Streamlit de la Calculadora IOTA.

Aplicación de apoyo a la decisión clínica (CDSS) para masas anexiales que
combina las IOTA Simple Rules con el modelo ADNEX.

Estructura de la interfaz:

1. Cabecera con el aviso legal obligatorio.
2. Datos del caso (identificador anonimizado, edad, fecha del estudio
   ecográfico, lado y notas de hallazgos ecográficos).
3. Paso 1 · IOTA Simple Rules (reglas B y reglas M).
4. Paso 2 · IOTA ADNEX, opcional y dependiente del interruptor
   "Aplicar modelo ADNEX". El modelo alternativo sin CA-125 se activa
   automáticamente cuando no se incluye el CA-125 sérico.
5. Informe consolidado descargable en PDF.

Las medidas de la lesión se introducen en milímetros, con las etiquetas del
estándar clínico: "Diámetro máximo de la lesión (mm)" y "Diámetro máximo
del componente sólido (mm)". La proporción de tejido sólido (``pst``) se
calcula internamente como componente_sólido / diámetro_lesión.

La aplicación no almacena datos en disco ni solicita identificadores del
paciente. El informe PDF se genera en memoria para su descarga.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from utils import SYSTEM_LABEL, SYSTEM_NAME, SYSTEM_SHORT_NAME
from utils.adnex_model import (
    CATEGORY_KEYS,
    CATEGORY_LABELS,
    calculate_adnex,
    calculate_solid_proportion,
)
from utils.case_model import (
    MAX_AGE,
    MAX_IDENTIFIER_LENGTH,
    MAX_NOTES_LENGTH,
    MIN_AGE,
    SIDE_OPTIONS,
    CaseData,
    build_case_data,
)
from utils.pdf_generator import generate_pdf_report
from utils.simple_rules import (
    BENIGN_FEATURE_LABELS,
    MALIGNANT_FEATURE_LABELS,
    evaluate_simple_rules,
)

APP_TITLE = "Calculadora IOTA · Apoyo a la Decisión Clínica"

LEGAL_NOTICE = (
    "Herramienta de apoyo a la decisión clínica (CDSS). No constituye un "
    "diagnóstico médico ni una recomendación terapéutica. Los resultados son "
    "estimaciones probabilísticas y deben interpretarse por un profesional "
    "sanitario cualificado junto con la historia clínica, la exploración, las "
    "pruebas de imagen y el juicio clínico. La decisión final corresponde "
    "exclusivamente al equipo clínico responsable."
)

LABEL_LESION_DIAMETER = "Diámetro máximo de la lesión (mm)"
LABEL_SOLID_DIAMETER = "Diámetro máximo del componente sólido (mm)"

_STATE_DEFAULTS: dict[str, object] = {
    "generation": 0,
    "sr_result": None,
    "sr_flags": None,
    "adnex_result": None,
    "adnex_inputs": None,
    "adnex_requested": False,
    "evaluation_date": None,
}
_STATE_KEYS = set(_STATE_DEFAULTS)

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        div[data-testid="stMetric"] {
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 0.6rem;
            padding: 0.7rem 0.9rem;
        }
        div[data-testid="stMetricLabel"] p { font-size: 0.82rem; }
        .siema-leyenda {
            border-left: 4px solid #B45309;
            background: #FEF3C7;
            color: #78350F;
            padding: 0.75rem 1rem;
            border-radius: 0.4rem;
            font-size: 0.92rem;
            margin-bottom: 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state() -> None:
    for key, value in _STATE_DEFAULTS.items():
        st.session_state.setdefault(key, value)


def _key(name: str) -> str:
    """Clave de widget dependiente de la generación de la sesión.

    Al limpiar la sesión se incrementa la generación, de modo que los
    widgets se recrean con identificadores nuevos y sus valores por defecto,
    en lugar de conservar los valores anteriores.
    """

    return f"siema_g{int(st.session_state.get('generation', 0))}_{name}"


def _reset_session() -> None:
    """Callback de limpieza total: borra resultados y valores de la sesión."""

    for key in list(st.session_state.keys()):
        if key.startswith("siema_"):
            del st.session_state[key]
    for key, value in _STATE_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["generation"] = int(st.session_state.get("generation", 0)) + 1


def _feature_markdown(codes: tuple[str, ...], labels: dict[str, str]) -> str:
    if not codes:
        return "_Ninguno_"
    return "\n".join(f"- **{code}** · {labels[code]}" for code in codes)


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"## {SYSTEM_SHORT_NAME}")
        st.caption(SYSTEM_NAME)
        st.caption(SYSTEM_LABEL)

        st.divider()
        st.markdown("**Flujo clínico**")
        st.markdown(
            "1. Registre los datos del caso.\n"
            "2. Aplique las IOTA Simple Rules (reglas B y M).\n"
            "3. Active el modelo ADNEX si las reglas son inconclusas.\n"
            "4. Descargue el informe consolidado en PDF."
        )

        st.divider()
        st.button(
            "Limpiar sesión / Nueva evaluación",
            use_container_width=True,
            type="primary",
            key=_key("reset_sidebar"),
            on_click=_reset_session,
        )

        st.divider()
        with st.expander("Referencias oficiales", expanded=False):
            st.markdown(
                "- Timmerman D, et al. *BMJ*. 2010;341:c6839. "
                "[doi:10.1136/bmj.c6839](https://doi.org/10.1136/bmj.c6839)\n"
                "- Van Calster B, et al. *BMJ*. 2014;349:g5920. "
                "[doi:10.1136/bmj.g5920](https://doi.org/10.1136/bmj.g5920)\n"
                "- Van Calster B, et al. *BMJ*. 2020;370:m2614. "
                "[doi:10.1136/bmj.m2614](https://doi.org/10.1136/bmj.m2614)\n"
                "- Van Calster B, et al. *Facts Views Vis Obgyn*. "
                "2015;7(1):32-41. [PMC4402441]"
                "(https://pmc.ncbi.nlm.nih.gov/articles/PMC4402441/)\n"
                "- Barreñada L, et al. *BMJ Med*. 2024;3(1):e000817. "
                "[doi:10.1136/bmjmed-2023-000817]"
                "(https://doi.org/10.1136/bmjmed-2023-000817)"
            )

        st.divider()
        st.caption(
            "Herramienta de apoyo a la decisión clínica. No sustituye el "
            "diagnóstico ni el juicio del profesional sanitario."
        )


# ---------------------------------------------------------------------------
# Cabecera y datos del caso
# ---------------------------------------------------------------------------


def _render_header() -> None:
    st.title(APP_TITLE)
    st.markdown(
        f"**{SYSTEM_NAME}** · {SYSTEM_LABEL}  \n"
        "IOTA Simple Rules y modelo ADNEX para masas anexiales."
    )
    st.markdown(
        f"<div class='siema-leyenda'><b>Aviso legal.</b> {LEGAL_NOTICE}</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "No introduzca nombres, documentos de identidad ni números de historia "
        "clínica. Utilice únicamente un identificador anonimizado."
    )


def _render_case_section() -> dict[str, object]:
    """Renderiza los datos del caso y devuelve los valores introducidos."""

    st.subheader("Datos del caso")
    st.caption(
        "Datos anonimizados del caso. El identificador debe ser un código "
        "libre que no permita identificar a la paciente."
    )

    col_left, col_middle, col_right = st.columns([1, 1, 1.4])

    with col_left:
        identifier = st.text_input(
            "Identificador (anonimizado)",
            value="",
            max_chars=MAX_IDENTIFIER_LENGTH,
            placeholder="p. ej. CASO-2026-001",
            help="Código anonimizado del caso. No incluya datos personales.",
            key=_key("identifier"),
        )
        age = st.number_input(
            "Edad (años)",
            min_value=MIN_AGE,
            max_value=MAX_AGE,
            value=45,
            step=1,
            key=_key("age"),
        )

    with col_middle:
        study_date = st.date_input(
            "Fecha del estudio ecográfico",
            value=date.today(),
            max_value=date.today(),
            key=_key("study_date"),
        )
        side = st.selectbox(
            "Lado",
            SIDE_OPTIONS,
            index=0,
            key=_key("side"),
        )

    with col_right:
        notes = st.text_area(
            "Notas / hallazgos ecográficos",
            value="",
            height=132,
            max_chars=MAX_NOTES_LENGTH,
            placeholder=(
                "Descripción de la lesión, contenido, paredes, Doppler, "
                "localización, etc."
            ),
            key=_key("notes"),
        )

    return {
        "identifier": identifier,
        "age": age,
        "study_date": study_date,
        "side": side,
        "notes": notes,
    }


def _build_case_data(values: dict[str, object]) -> CaseData | None:
    try:
        return build_case_data(
            identifier=values.get("identifier", ""),
            age=values.get("age"),
            study_date=values.get("study_date"),
            side=values.get("side"),
            notes=values.get("notes", ""),
        )
    except ValueError as exc:
        st.error(f"Revise los datos del caso: {exc}")
        return None


# ---------------------------------------------------------------------------
# Paso 1 · IOTA Simple Rules
# ---------------------------------------------------------------------------


def _render_simple_rules_section() -> None:
    st.subheader("Paso 1 · IOTA Simple Rules")
    st.caption("Marque todos los hallazgos ecográficos presentes.")

    benign_col, malignant_col = st.columns(2)
    benign_flags: dict[str, bool] = {}
    malignant_flags: dict[str, bool] = {}

    with benign_col:
        st.markdown("**Reglas B (benignas)**")
        for code, label in BENIGN_FEATURE_LABELS.items():
            benign_flags[code] = st.checkbox(
                f"{code} · {label}",
                key=_key(code),
            )

    with malignant_col:
        st.markdown("**Reglas M (malignas)**")
        for code, label in MALIGNANT_FEATURE_LABELS.items():
            malignant_flags[code] = st.checkbox(
                f"{code} · {label}",
                key=_key(code),
            )

    if st.button(
        "Evaluar Simple Rules",
        type="primary",
        use_container_width=True,
        key=_key("evaluate_simple_rules"),
    ):
        try:
            result = evaluate_simple_rules(benign_flags, malignant_flags)
        except (TypeError, ValueError) as exc:
            st.error(f"No se pudieron aplicar las IOTA Simple Rules: {exc}")
            return
        st.session_state.sr_result = result
        st.session_state.sr_flags = (dict(benign_flags), dict(malignant_flags))
        st.session_state.evaluation_date = datetime.now()

    result = st.session_state.sr_result
    if result is None:
        st.caption(
            "Sin resultado: pulse «Evaluar Simple Rules» para clasificar la "
            "masa anexial."
        )
        return

    if result.is_benign:
        st.success(
            "**Clasificación: Benigno.** Al menos un criterio B y ningún criterio M."
        )
    elif result.is_malignant:
        st.error(
            "**Clasificación: Maligno.** Al menos un criterio M y ningún criterio B."
        )
    else:
        st.warning(
            "**Clasificación: Inconclusivo / Indeterminado.** La combinación de "
            "criterios B y M no permite una clasificación concluyente."
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Criterios B presentes", result.benign_count)
    col2.metric("Criterios M presentes", result.malignant_count)
    col3.metric(
        "Resultado",
        "Concluyente" if result.is_conclusive else "No concluyente",
    )

    if not result.is_conclusive:
        st.info(
            "Las reglas simples son inconclusivas: active el paso 2 para "
            "completar la estimación de riesgo con el modelo ADNEX."
        )

    with st.expander("Hallazgos seleccionados", expanded=True):
        col_b, col_m = st.columns(2)
        with col_b:
            st.markdown("**Reglas B**")
            st.markdown(
                _feature_markdown(result.benign_features, BENIGN_FEATURE_LABELS)
            )
        with col_m:
            st.markdown("**Reglas M**")
            st.markdown(
                _feature_markdown(result.malignant_features, MALIGNANT_FEATURE_LABELS)
            )


# ---------------------------------------------------------------------------
# Paso 2 · IOTA ADNEX
# ---------------------------------------------------------------------------


def _render_adnex_section(case_values: dict[str, object]) -> None:
    st.subheader("Paso 2 · IOTA ADNEX (opcional)")
    st.caption(
        "El modelo ADNEX estima el riesgo de malignidad y se activa de forma "
        "independiente del resultado de las reglas simples."
    )

    apply_adnex = st.checkbox(
        "Aplicar modelo ADNEX",
        key=_key("apply_adnex"),
    )
    st.session_state.adnex_requested = bool(apply_adnex)

    if not apply_adnex:
        st.caption(
            "Modelo ADNEX desactivado. El informe se generará únicamente con "
            "los datos del caso y el resultado de las IOTA Simple Rules."
        )
        return

    include_ca125 = st.checkbox(
        "Incluir CA-125 sérico",
        key=_key("include_ca125"),
        help=(
            "Si no se incluye, el motor ADNEX utiliza automáticamente las "
            "ecuaciones validadas sin CA-125."
        ),
    )

    defaults = st.session_state.get("adnex_inputs") or {}
    age = int(case_values.get("age", 45))

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Medidas de la lesión**")
        mdl = st.number_input(
            LABEL_LESION_DIAMETER,
            min_value=1.0,
            max_value=500.0,
            value=float(defaults.get("mdl", 50.0)),
            step=1.0,
            format="%.1f",
            key=_key("mdl"),
        )
        solid_diameter = st.number_input(
            LABEL_SOLID_DIAMETER,
            min_value=0.0,
            max_value=500.0,
            value=float(defaults.get("solid_diameter", 0.0)),
            step=1.0,
            format="%.1f",
            help=(
                "La proporción de tejido sólido se calcula automáticamente como "
                "componente_sólido / diámetro_lesión."
            ),
            key=_key("solid_diameter"),
        )
        if include_ca125:
            ca125 = st.number_input(
                "CA-125 sérico (U/mL)",
                min_value=0.0,
                max_value=100000.0,
                value=float(defaults.get("ca125") or 0.0),
                step=1.0,
                format="%.1f",
                help="Introduzca 0 si el resultado no está disponible.",
                key=_key("ca125"),
            )
        else:
            ca125 = None

    with col_b:
        st.markdown("**Variables clínicas y ecográficas**")
        tcl = st.checkbox(
            "Más de 10 lóculos quísticos",
            key=_key("tcl"),
        )
        nps = st.number_input(
            "N° de proyecciones papilares",
            min_value=0,
            max_value=4,
            value=int(defaults.get("nps", 0)),
            step=1,
            help="El valor 4 representa cuatro o más proyecciones papilares.",
            key=_key("nps"),
        )
        sha = st.checkbox(
            "Sombras acústicas",
            key=_key("sha"),
        )
        asc = st.checkbox(
            "Ascitis",
            key=_key("asc"),
        )
        onc = st.checkbox(
            "Ecografía en centro oncológico especializado",
            key=_key("onc"),
        )

    if st.button(
        "Calcular ADNEX",
        type="primary",
        use_container_width=True,
        key=_key("calculate_adnex"),
    ):
        try:
            pst = calculate_solid_proportion(float(mdl), float(solid_diameter))
        except (TypeError, ValueError) as exc:
            st.error(f"No se pudo calcular la proporción de tejido sólido: {exc}")
            return

        try:
            result = calculate_adnex(
                age=age,
                mdl=float(mdl),
                pst=pst,
                tcl=tcl,
                nps=nps,
                sha=sha,
                asc=asc,
                onc=onc,
                ca125=ca125 if ca125 and ca125 > 0 else None,
            )
        except (TypeError, ValueError) as exc:
            st.error(f"No se pudo calcular el modelo ADNEX: {exc}")
            return

        st.session_state.adnex_result = result
        st.session_state.adnex_inputs = {
            "age": age,
            "mdl": float(mdl),
            "solid_diameter": float(solid_diameter),
            "pst": pst,
            "tcl": bool(tcl),
            "nps": int(nps),
            "sha": bool(sha),
            "asc": bool(asc),
            "onc": bool(onc),
            "ca125": float(ca125) if ca125 else None,
        }
        st.session_state.evaluation_date = datetime.now()

    _render_adnex_result()


def _render_adnex_result() -> None:
    result = st.session_state.adnex_result
    if result is None:
        return

    st.markdown("**Resultado del modelo ADNEX**")

    col_metric, col_caption = st.columns([1, 2])
    col_metric.metric(
        "Riesgo de malignidad",
        f"{result.malignancy_percentage:.1f} %",
    )
    with col_caption:
        st.markdown(
            "El riesgo de malignidad es la suma de tumor borderline, carcinoma "
            "invasivo en estadio I, carcinoma invasivo en estadio II-IV y "
            "enfermedad metastásica."
        )
        if result.used_ca125:
            ca125_value = result.inputs.get("ca125")
            st.caption(
                f"Ecuaciones con CA-125 · CA-125 = {float(ca125_value):.1f} U/mL"
            )
        else:
            st.caption("Ecuaciones sin CA-125 (modelo alternativo).")

    rows = []
    for key in CATEGORY_KEYS:
        rows.append(
            {
                "Categoría": CATEGORY_LABELS[key],
                "Probabilidad": f"{result.percentages[key]:.1f} %",
                "Naturaleza": "Benigna" if key == "benign" else "Maligna",
            }
        )
    st.table(rows)

    st.caption(
        "Los porcentajes se ajustan por el método del mayor resto para que las "
        "cinco categorías sumen exactamente 100.0 %."
    )

    with st.expander("Detalle técnico del cálculo", expanded=False):
        mdl_value = float(result.inputs["mdl"])
        pst_value = float(result.inputs["pst"])
        solid_value = st.session_state.adnex_inputs.get("solid_diameter")
        if solid_value is None:
            solid_value = pst_value * mdl_value

        variables = [
            ("Edad", f"{float(result.inputs['age']):.0f} años"),
            ("Diámetro máximo de la lesión", f"{mdl_value:.1f} mm"),
            ("Diámetro máximo del componente sólido", f"{solid_value:.1f} mm"),
            ("Proporción de tejido sólido", f"{pst_value * 100:.0f} %"),
            (
                "Más de 10 lóculos quísticos",
                "Sí" if result.inputs["tcl"] else "No",
            ),
            (
                "Proyecciones papilares",
                f"{float(result.inputs['nps']):.0f}",
            ),
            ("Sombras acústicas", "Sí" if result.inputs["sha"] else "No"),
            ("Ascitis", "Sí" if result.inputs["asc"] else "No"),
            (
                "Ecografía en centro oncológico especializado",
                "Sí" if result.inputs["onc"] else "No",
            ),
        ]
        if result.used_ca125:
            variables.append(
                ("CA-125", f"{float(result.inputs['ca125']):.1f} U/mL")
            )
        else:
            variables.append(("CA-125", "No incluido"))

        st.markdown("**Variables del modelo**")
        st.table(
            [{"Variable": name, "Valor": value} for name, value in variables]
        )

        z1, z2, z3, z4 = result.z_scores
        st.markdown(
            "**Puntuaciones z**\n\n"
            f"- **Ecuaciones:** {result.equation_set_label}\n"
            f"- **z1 (borderline):** {z1:.4f}\n"
            f"- **z2 (estadio I):** {z2:.4f}\n"
            f"- **z3 (estadio II-IV):** {z3:.4f}\n"
            f"- **z4 (metastásica):** {z4:.4f}\n"
            "- **Categoría de referencia:** benigno (z0 = 0)"
        )


# ---------------------------------------------------------------------------
# Informe consolidado
# ---------------------------------------------------------------------------


def _render_report_section(case_data: CaseData | None) -> None:
    st.subheader("Informe consolidado")
    st.caption(
        "Informe PDF generado íntegramente en memoria, con los datos "
        "anonimizados del caso, el resultado de las reglas simples, el "
        "desglose de riesgo ADNEX y el aviso legal obligatorio."
    )

    if case_data is None:
        st.warning("Complete los datos del caso para generar el informe.")
        return

    simple_rules = st.session_state.sr_result
    adnex = st.session_state.adnex_result
    adnex_requested = bool(st.session_state.get("adnex_requested"))
    evaluation_date = st.session_state.evaluation_date or datetime.now()

    if simple_rules is None:
        st.info(
            "Aún no se ha evaluado el paso 1. El informe se generará con los "
            "datos del caso y sin clasificación de las reglas simples."
        )
    if adnex_requested and adnex is None:
        st.info(
            "El modelo ADNEX está activo pero todavía no se ha calculado. "
            "El informe se generará sin el desglose de riesgo ADNEX."
        )

    pdf_bytes = generate_pdf_report(
        case_data=case_data,
        simple_rules=simple_rules,
        adnex=adnex,
        adnex_requested=adnex_requested,
        evaluation_date=evaluation_date,
    )
    file_name = f"Calculadora_IOTA_informe_{evaluation_date:%Y%m%d_%H%M}.pdf"

    st.download_button(
        "Descargar informe PDF",
        data=pdf_bytes,
        file_name=file_name,
        mime="application/pdf",
        use_container_width=True,
        type="primary",
        key=_key("download_report"),
    )


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------


def main() -> None:
    _init_state()
    _render_sidebar()
    _render_header()

    case_values = _render_case_section()
    case_data = _build_case_data(case_values)

    st.divider()
    _render_simple_rules_section()

    st.divider()
    _render_adnex_section(case_values)

    st.divider()
    _render_report_section(case_data)

    st.divider()
    st.caption(
        "Aviso CDSS: herramienta de apoyo a la decisión clínica. No constituye "
        "diagnóstico ni recomendación terapéutica; la decisión final "
        "corresponde al profesional sanitario responsable."
    )


if __name__ == "__main__":
    main()
