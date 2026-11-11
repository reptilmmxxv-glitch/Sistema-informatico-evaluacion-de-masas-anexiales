"""Generación del informe PDF consolidado de la Calculadora IOTA.

El informe se construye íntegramente en memoria (``BytesIO``) para evitar la
escritura de datos clínicos en disco. Incluye:

1. Datos anonimizados del caso (identificador, edad, fecha del estudio
   ecográfico, lado y notas de hallazgos ecográficos).
2. Resultado de las IOTA Simple Rules con el desglose de criterios B y M.
3. Desglose de riesgo del modelo ADNEX, cuando se ha calculado, con la
   puntuación z de cada categoría y el riesgo de malignidad.
4. Referencias oficiales.
5. Aviso obligatorio de apoyo a la decisión clínica (CDSS).

No se admiten ni se incluyen nombres, documentos de identidad, números de
historia clínica ni otros identificadores del paciente.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Mapping
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from utils import (
    SYSTEM_LABEL,
    SYSTEM_NAME,
    SYSTEM_RELEASE,
    SYSTEM_VERSION,
)
from utils.adnex_model import (
    ADNEXResult,
    CATEGORY_KEYS,
    CATEGORY_LABELS,
    MALIGNANT_CATEGORIES,
)
from utils.case_model import CaseData
from utils.simple_rules import (
    BENIGN_FEATURE_LABELS,
    MALIGNANT_FEATURE_LABELS,
    SimpleRulesResult,
)

PAGE_WIDTH = A4[0]
LEFT_MARGIN = 18 * mm
RIGHT_MARGIN = 18 * mm
TOP_MARGIN = 18 * mm
BOTTOM_MARGIN = 20 * mm
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN

NAVY = colors.HexColor("#123B5E")
TEAL = colors.HexColor("#0F766E")
TEXT = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#475569")
LIGHT = colors.HexColor("#F1F5F9")
BORDER = colors.HexColor("#CBD5E1")
ALERT_BG = colors.HexColor("#FEF3C7")
ALERT_BORDER = colors.HexColor("#B45309")
DANGER_BG = colors.HexColor("#FEF2F2")
DANGER_BORDER = colors.HexColor("#B91C1C")

_BASE_STYLES = getSampleStyleSheet()

STYLE_BRAND = ParagraphStyle(
    "SIEMA_Brand",
    parent=_BASE_STYLES["Title"],
    fontName="Helvetica-Bold",
    fontSize=22,
    leading=25,
    textColor=NAVY,
    alignment=TA_LEFT,
    spaceAfter=0,
)
STYLE_SYSTEM_NAME = ParagraphStyle(
    "SIEMA_SystemName",
    parent=_BASE_STYLES["BodyText"],
    fontName="Helvetica",
    fontSize=8.5,
    leading=11,
    textColor=MUTED,
    spaceAfter=0,
)
STYLE_TITLE = ParagraphStyle(
    "SIEMA_ReportTitle",
    parent=_BASE_STYLES["Heading1"],
    fontName="Helvetica-Bold",
    fontSize=16,
    leading=20,
    textColor=NAVY,
    spaceBefore=0,
    spaceAfter=3,
)
STYLE_SUBTITLE = ParagraphStyle(
    "SIEMA_Subtitle",
    parent=_BASE_STYLES["BodyText"],
    fontName="Helvetica",
    fontSize=9,
    leading=12,
    textColor=MUTED,
    spaceAfter=0,
)
STYLE_SECTION = ParagraphStyle(
    "SIEMA_Section",
    parent=_BASE_STYLES["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=11.5,
    leading=14,
    textColor=NAVY,
    spaceBefore=10,
    spaceAfter=5,
)
STYLE_BODY = ParagraphStyle(
    "SIEMA_Body",
    parent=_BASE_STYLES["BodyText"],
    fontSize=9,
    leading=12.5,
    textColor=TEXT,
    spaceAfter=4,
)
STYLE_SMALL = ParagraphStyle(
    "SIEMA_Small",
    parent=STYLE_BODY,
    fontSize=8,
    leading=10.5,
    textColor=MUTED,
)
STYLE_TABLE_HEADER = ParagraphStyle(
    "SIEMA_TableHeader",
    parent=STYLE_BODY,
    fontName="Helvetica-Bold",
    fontSize=8.2,
    leading=10,
    textColor=colors.white,
    spaceAfter=0,
)
STYLE_TABLE_CELL = ParagraphStyle(
    "SIEMA_TableCell",
    parent=STYLE_BODY,
    fontSize=8.4,
    leading=10.5,
    spaceAfter=0,
)
STYLE_TABLE_LABEL = ParagraphStyle(
    "SIEMA_TableLabel",
    parent=STYLE_TABLE_CELL,
    fontName="Helvetica-Bold",
)
STYLE_ALERT = ParagraphStyle(
    "SIEMA_Alert",
    parent=STYLE_BODY,
    fontSize=8.8,
    leading=12,
    textColor=colors.HexColor("#78350F"),
    spaceAfter=0,
)
STYLE_DISCLAIMER = ParagraphStyle(
    "SIEMA_Disclaimer",
    parent=STYLE_BODY,
    fontSize=8.6,
    leading=12,
    textColor=colors.HexColor("#7F1D1D"),
    spaceAfter=0,
)


def _format_date(value: datetime) -> str:
    return value.strftime("%d/%m/%Y a las %H:%M")


def _format_number(value: object, decimals: int, suffix: str = "") -> str:
    if value is None:
        return "No disponible"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "No disponible"
    if number <= 0 and suffix == " U/mL":
        return "No disponible"
    return f"{number:.{decimals}f}{suffix}"


def _format_yes_no(value: object) -> str:
    return "Sí" if bool(value) else "No"


def _kv_table(rows: list[tuple[str, str]], label_width: float = 52 * mm) -> Table:
    data = [
        [
            Paragraph(escape(label), STYLE_TABLE_LABEL),
            Paragraph(escape(value), STYLE_TABLE_CELL),
        ]
        for label, value in rows
    ]
    table = Table(data, colWidths=[label_width, CONTENT_WIDTH - label_width])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _data_table(
    header: tuple[str, ...],
    rows: list[tuple[str | Paragraph, ...]],
    widths: tuple[float, ...],
    highlight_row: int | None = None,
) -> Table:
    data: list[list[Paragraph]] = [
        [Paragraph(escape(cell), STYLE_TABLE_HEADER) for cell in header]
    ]
    for row in rows:
        cells: list[Paragraph] = []
        for cell in row:
            if isinstance(cell, Paragraph):
                cells.append(cell)
            else:
                cells.append(Paragraph(escape(cell), STYLE_TABLE_CELL))
        data.append(cells)

    table = Table(data, colWidths=list(widths), repeatRows=1)
    styles = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if highlight_row is not None:
        styles.extend(
            [
                (
                    "BACKGROUND",
                    (0, highlight_row),
                    (-1, highlight_row),
                    colors.HexColor("#E2E8F0"),
                ),
                ("LINEABOVE", (0, highlight_row), (-1, highlight_row), 0.9, NAVY),
            ]
        )
    table.setStyle(TableStyle(styles))
    return table


def _boxed(flowable: Paragraph, background: colors.Color, border: colors.Color) -> Table:
    table = Table([[flowable]], colWidths=[CONTENT_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.9, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _feature_list(codes: tuple[str, ...], labels: Mapping[str, str]) -> str:
    if not codes:
        return "Ninguno"
    return "<br/>".join(
        f"• <b>{escape(code)}</b> - {escape(labels[code])}" for code in codes
    )


def _draw_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(LEFT_MARGIN, 15 * mm, PAGE_WIDTH - RIGHT_MARGIN, 15 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        LEFT_MARGIN,
        10.5 * mm,
        f"{SYSTEM_LABEL} · Documento generado automáticamente · Datos anonimizados",
    )
    canvas.drawRightString(
        PAGE_WIDTH - RIGHT_MARGIN,
        10.5 * mm,
        f"Página {doc.page}",
    )
    canvas.restoreState()


def _case_rows(case_data: CaseData) -> list[tuple[str, str]]:
    rows = [
        ("Identificador (anonimizado)", case_data.display_identifier),
        ("Edad", f"{case_data.age} años"),
        ("Fecha del estudio ecográfico", case_data.study_date.strftime("%d/%m/%Y")),
        ("Lado", case_data.side),
    ]
    if case_data.has_notes:
        rows.append(("Notas / hallazgos ecográficos", case_data.notes))
    return rows


def generate_pdf_report(
    *,
    case_data: CaseData,
    simple_rules: SimpleRulesResult | None = None,
    adnex: ADNEXResult | None = None,
    adnex_requested: bool = False,
    evaluation_date: datetime | None = None,
) -> bytes:
    """Construye el informe PDF consolidado y devuelve sus bytes.

    Args:
        case_data: Datos anonimizados del caso (identificador, edad, fecha del
            estudio ecográfico, lado y notas).
        simple_rules: Resultado de las IOTA Simple Rules, si se evaluaron.
        adnex: Resultado del modelo ADNEX, si se calculó.
        adnex_requested: Indica si el modelo ADNEX estaba activo. Permite
            distinguir "no solicitado" de "solicitado y no calculado".
        evaluation_date: Fecha de la evaluación. Si se omite, se usa la fecha
            y hora actuales.

    Returns:
        Contenido binario del PDF listo para su descarga.
    """

    report_date = evaluation_date or datetime.now()
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title="Informe de evaluación de masa anexial",
        author=SYSTEM_NAME,
        subject="Apoyo a la decisión clínica en masas anexiales",
        creator=SYSTEM_LABEL,
    )

    story: list[object] = []

    # Encabezado institucional.
    story.append(Paragraph("SIEMA", STYLE_BRAND))
    story.append(Paragraph(escape(SYSTEM_NAME), STYLE_SYSTEM_NAME))
    story.append(Spacer(1, 3 * mm))
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.1,
            color=TEAL,
            spaceBefore=0,
            spaceAfter=5 * mm,
        )
    )
    story.append(
        Paragraph("Calculadora IOTA · Apoyo a la Decisión Clínica", STYLE_TITLE)
    )
    story.append(
        Paragraph(
            "Documento anonimizado de apoyo a la decisión clínica (CDSS)",
            STYLE_SUBTITLE,
        )
    )
    story.append(Spacer(1, 4 * mm))

    models_applied = "IOTA Simple Rules"
    if simple_rules is not None and adnex is not None:
        models_applied = "IOTA Simple Rules + ADNEX"
    elif simple_rules is None and adnex is not None:
        models_applied = "ADNEX"

    story.append(
        _kv_table(
            [
                ("Fecha de la evaluación", _format_date(report_date)),
                ("Sistema", SYSTEM_LABEL),
                ("Versión", f"{SYSTEM_VERSION} ({SYSTEM_RELEASE})"),
                ("Modelos aplicados", models_applied),
            ],
            label_width=48 * mm,
        )
    )
    story.append(Spacer(1, 4 * mm))

    story.append(
        _boxed(
            Paragraph(
                "<b>Aviso legal.</b> Esta herramienta de apoyo a la decisión "
                "clínica no constituye un diagnóstico médico ni una "
                "recomendación terapéutica. Los resultados son estimaciones "
                "probabilísticas y deben interpretarse por un profesional "
                "sanitario cualificado y en el contexto clínico.",
                STYLE_ALERT,
            ),
            ALERT_BG,
            ALERT_BORDER,
        )
    )

    # 1. Datos del caso.
    story.append(Paragraph("1. Datos del caso", STYLE_SECTION))
    story.append(_kv_table(_case_rows(case_data)))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "Este informe no contiene nombre, documento de identidad, número de "
            "historia clínica ni otros datos identificativos del paciente.",
            STYLE_SMALL,
        )
    )

    # 2. IOTA Simple Rules.
    story.append(Paragraph("2. Paso 1: IOTA Simple Rules", STYLE_SECTION))
    if simple_rules is None:
        story.append(
            Paragraph(
                "No se evaluaron las reglas simples en esta sesión.",
                STYLE_BODY,
            )
        )
    else:
        story.append(
            _data_table(
                ("Clasificación", "Hallazgos B", "Hallazgos M"),
                [
                    (
                        simple_rules.classification,
                        str(simple_rules.benign_count),
                        str(simple_rules.malignant_count),
                    )
                ],
                (CONTENT_WIDTH * 0.56, CONTENT_WIDTH * 0.22, CONTENT_WIDTH * 0.22),
            )
        )
        story.append(Spacer(1, 3 * mm))
        story.append(
            _data_table(
                ("Criterios B presentes", "Criterios M presentes"),
                [
                    (
                        Paragraph(
                            _feature_list(
                                simple_rules.benign_features, BENIGN_FEATURE_LABELS
                            ),
                            STYLE_TABLE_CELL,
                        ),
                        Paragraph(
                            _feature_list(
                                simple_rules.malignant_features,
                                MALIGNANT_FEATURE_LABELS,
                            ),
                            STYLE_TABLE_CELL,
                        ),
                    )
                ],
                (CONTENT_WIDTH / 2, CONTENT_WIDTH / 2),
            )
        )
        story.append(Spacer(1, 2 * mm))
        story.append(
            Paragraph(
                "Regla aplicada: benigno si existe al menos un criterio B y "
                "ningún criterio M; maligno si existe al menos un criterio M y "
                "ningún criterio B; en cualquier otro caso, inconcluso / "
                "indeterminado.",
                STYLE_SMALL,
            )
        )

    # 3. Modelo ADNEX.
    story.append(Paragraph("3. Paso 2: modelo ADNEX", STYLE_SECTION))
    if adnex is None:
        if not adnex_requested:
            reason = (
                "El modelo ADNEX no fue solicitado en esta evaluación."
            )
        else:
            reason = (
                "El modelo ADNEX fue solicitado, pero no llegó a calcularse en "
                "esta evaluación."
            )
        story.append(
            Paragraph(f"No se realizó el modelo ADNEX. {escape(reason)}", STYLE_BODY)
        )
    else:
        ca125_text = (
            _format_number(adnex.inputs.get("ca125"), 1, " U/mL")
            if adnex.used_ca125
            else "No incluido (ecuaciones sin CA-125)"
        )
        story.append(
            Paragraph(
                f"Ecuaciones utilizadas: <b>{escape(adnex.equation_set_label)}</b>. "
                f"CA-125: {escape(ca125_text)}.",
                STYLE_BODY,
            )
        )

        mdl_value = float(adnex.inputs.get("mdl", 0.0))
        pst_value = float(adnex.inputs.get("pst", 0.0))
        solid_diameter = mdl_value * pst_value

        story.append(
            _kv_table(
                [
                    ("Edad", _format_number(adnex.inputs.get("age"), 0, " años")),
                    (
                        "Diámetro máximo de la lesión",
                        _format_number(mdl_value, 1, " mm"),
                    ),
                    (
                        "Diámetro máximo del componente sólido",
                        _format_number(solid_diameter, 1, " mm"),
                    ),
                    (
                        "Proporción de tejido sólido",
                        _format_number(pst_value * 100.0, 0, " %"),
                    ),
                    (
                        "Más de 10 lóculos quísticos",
                        _format_yes_no(adnex.inputs.get("tcl")),
                    ),
                    (
                        "Proyecciones papilares (4 = 4 o más)",
                        _format_number(adnex.inputs.get("nps"), 0),
                    ),
                    (
                        "Sombras acústicas",
                        _format_yes_no(adnex.inputs.get("sha")),
                    ),
                    ("Ascitis", _format_yes_no(adnex.inputs.get("asc"))),
                    (
                        "Ecografía en centro oncológico especializado",
                        _format_yes_no(adnex.inputs.get("onc")),
                    ),
                    ("CA-125 sérico", ca125_text),
                ],
                label_width=70 * mm,
            )
        )
        story.append(Spacer(1, 3 * mm))

        percentage_rows: list[tuple[str, str, str]] = []
        for key in CATEGORY_KEYS:
            percentage_rows.append(
                (
                    CATEGORY_LABELS[key],
                    f"{adnex.percentages[key]:.1f} %",
                    "Maligno" if key in MALIGNANT_CATEGORIES else "Benigno",
                )
            )
        percentage_rows.append(
            (
                "Riesgo de malignidad (RM)",
                f"{adnex.malignancy_percentage:.1f} %",
                "Suma de las cuatro categorías malignas",
            )
        )

        probability_table = _data_table(
            ("Categoría", "Probabilidad", "Naturaleza"),
            percentage_rows,
            (CONTENT_WIDTH * 0.50, CONTENT_WIDTH * 0.17, CONTENT_WIDTH * 0.33),
            highlight_row=6,
        )
        story.append(probability_table)
        story.append(Spacer(1, 2 * mm))
        story.append(
            Paragraph(
                "El riesgo de malignidad es la suma de tumor borderline, "
                "carcinoma invasivo en estadio I, carcinoma invasivo en estadio "
                "II-IV y enfermedad metastásica. Los porcentajes se han ajustado "
                "para que el total de las cinco categorías sea exactamente 100.0 %.",
                STYLE_SMALL,
            )
        )

        z1, z2, z3, z4 = adnex.z_scores
        story.append(
            Paragraph(
                "Trazabilidad del cálculo: "
                f"z1 = {z1:.4f}; z2 = {z2:.4f}; z3 = {z3:.4f}; z4 = {z4:.4f}. "
                "Categoría de referencia: benigno (z0 = 0).",
                STYLE_SMALL,
            )
        )

    # 4. Referencias.
    story.append(Paragraph("4. Referencias", STYLE_SECTION))
    references = [
        "Timmerman D, et al. Simple ultrasound rules to distinguish between "
        "benign and malignant adnexal masses before surgery: prospective "
        "validation by IOTA group. BMJ. 2010;341:c6839. "
        "doi:10.1136/bmj.c6839.",
        "Van Calster B, et al. Evaluating the risk of ovarian cancer before "
        "surgery using the ADNEX model to differentiate between benign, "
        "borderline, early and advanced stage invasive, and secondary "
        "metastatic tumours: prospective multicentre diagnostic study. BMJ. "
        "2014;349:g5920. doi:10.1136/bmj.g5920.",
        "Van Calster B, et al. Validation of models to diagnose ovarian cancer "
        "in patients managed surgically or conservatively: multicentre cohort "
        "study. BMJ. 2020;370:m2614. doi:10.1136/bmj.m2614.",
        "Van Calster B, et al. Practical guidance for applying the ADNEX model "
        "from the IOTA group to discriminate between different subtypes of "
        "adnexal tumors. Facts Views Vis Obgyn. 2015;7(1):32-41. PMC4402441.",
        "Barreñada L, et al. ADNEX risk prediction model for diagnosis of "
        "ovarian cancer: systematic review and meta-analysis of external "
        "validation studies. BMJ Med. 2024;3(1):e000817. "
        "doi:10.1136/bmjmed-2023-000817.",
    ]
    for reference in references:
        story.append(Paragraph(f"• {escape(reference)}", STYLE_SMALL))

    # 5. Aviso obligatorio.
    story.append(Paragraph("5. Limitaciones y aviso de apoyo a la decisión", STYLE_SECTION))
    disclaimer = (
        "<b>AVISO IMPORTANTE - APOYO A LA DECISIÓN CLÍNICA (CDSS).</b> "
        "Este informe ha sido generado por un sistema informático de apoyo a la "
        "decisión clínica y no constituye un diagnóstico médico ni una "
        "recomendación terapéutica. Los resultados son estimaciones "
        "probabilísticas basadas en los modelos IOTA Simple Rules y ADNEX y "
        "deben interpretarse junto con la historia clínica, la exploración "
        "física, las pruebas de imagen y el juicio de un profesional sanitario "
        "cualificado. Ningún valor de este informe debe utilizarse de forma "
        "aislada para adoptar decisiones clínicas. El diagnóstico definitivo "
        "requiere estudio histopatológico cuando esté indicado. La decisión "
        "final corresponde exclusivamente al equipo clínico responsable."
    )
    story.append(_boxed(Paragraph(disclaimer, STYLE_DISCLAIMER), DANGER_BG, DANGER_BORDER))

    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()


__all__ = ["generate_pdf_report"]
