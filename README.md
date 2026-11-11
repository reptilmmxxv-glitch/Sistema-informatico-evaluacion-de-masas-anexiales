# SIEMA — Calculadora IOTA para evaluación de masas anexiales

Aplicación de apoyo a la decisión clínica (CDSS) para la evaluación de masas
anexiales mediante **IOTA Simple Rules** y el **modelo ADNEX**, implementada en
Python con Streamlit.

El sistema guía la evaluación en una única pantalla, reutiliza los datos ya
introducidos y genera un informe PDF consolidado y anonimizado con los
resultados, el desglose de riesgo, la fecha, la versión del sistema y el aviso
obligatorio de apoyo a la decisión clínica.

> **Aviso:** esta herramienta no constituye un diagnóstico médico ni una
> recomendación terapéutica. Los resultados son estimaciones probabilísticas y
> deben interpretarse por un profesional sanitario cualificado, junto con la
> historia clínica, la exploración, las pruebas de imagen y el estudio
> histopatológico cuando esté indicado. La decisión final corresponde al equipo
> clínico responsable.

---

## Interfaz

### Cabecera

- Título **«Calculadora IOTA · Apoyo a la Decisión Clínica»**.
- Aviso legal obligatorio de soporte a la decisión (no diagnóstico).
- Aviso de anonimización: no se introducen nombres ni identificadores.

### Datos del caso

| Campo | Tipo | Notas |
| --- | --- | --- |
| Identificador (anonimizado) | Texto | Código libre del caso, máximo 64 caracteres |
| Edad (años) | Número | 18–100 |
| Fecha del estudio ecográfico | Fecha | No puede ser futura |
| Lado | Selector | No especificado / Izquierdo / Derecho |
| Notas / hallazgos ecográficos | Texto | Descripción libre, máximo 1200 caracteres |

### Paso 1 · IOTA Simple Rules

- Dos columnas: **Reglas B (benignas)** (B1–B5) y **Reglas M (malignas)**
  (M1–M5).
- Botón **«Evaluar Simple Rules»** con la clasificación resultante:
  - **Benigno:** al menos un criterio B y ningún criterio M.
  - **Maligno:** al menos un criterio M y ningún criterio B.
  - **Inconclusivo / Indeterminado:** cualquier otra combinación, incluida la
    ausencia de hallazgos.

### Paso 2 · IOTA ADNEX (opcional)

- Casilla **«Aplicar modelo ADNEX»**: habilita todo el bloque.
- Casilla **«Incluir CA-125 sérico»**: al marcarse aparece el campo de CA-125;
  al desmarcarse el motor usa automáticamente las ecuaciones sin CA-125.
- Medidas de la lesión, en milímetros:
  - **Diámetro máximo de la lesión (mm)** (`mdl`).
  - **Diámetro máximo del componente sólido (mm)**, con cálculo interno
    automático de la proporción sólida `pst = componente_sólido / diámetro_lesión`.
- Variables clínicas y ecográficas: **Más de 10 lóculos quísticos** (`tcl`),
  **N° de proyecciones papilares** (`nps`, saturado a 4), **Sombras acústicas**
  (`sha`), **Ascitis** (`asc`) y **Ecografía en centro oncológico
  especializado** (`onc`).
- Botón **«Calcular ADNEX»**: muestra el riesgo de malignidad, el desglose de
  las cinco categorías y el detalle técnico (variables y puntuaciones z).

### Informe consolidado

- Sección inferior con **«Descargar informe PDF»**. El PDF se genera en
  memoria (`BytesIO`), sin escribir datos en disco, e incluye:
  1. Datos anonimizados del caso.
  2. Resultado de las IOTA Simple Rules con el desglose de criterios B y M.
  3. Desglose de riesgo ADNEX con el riesgo de malignidad y las
     puntuaciones z (cuando se ha calculado).
  4. Referencias oficiales.
  5. Advertencia legal de apoyo a la decisión clínica.

### Barra lateral

- Flujo clínico guiado en cuatro pasos.
- Botón **«Limpiar sesión / Nueva evaluación»**: borra resultados y valores
  de la sesión por completo.
- Enlaces a las referencias oficiales de IOTA y del modelo ADNEX.

---

## Estructura del proyecto

```text
calculadora_modelo_iota/
├── app.py                      # Interfaz Streamlit y flujo de evaluación
├── requirements.txt            # Dependencias del proyecto
├── README.md
├── .gitignore
├── utils/
│   ├── __init__.py             # Metadatos y versión del sistema
│   ├── simple_rules.py         # IOTA Simple Rules
│   ├── adnex_model.py          # Ecuaciones y cálculo del modelo ADNEX
│   ├── case_model.py           # Datos anonimizados del caso
│   └── pdf_generator.py        # Informe PDF consolidado
└── tests/
    └── test_models.py          # Pruebas de modelos, caso y PDF
```

---

## Requisitos e instalación

- Python 3.10 o superior (probado con Python 3.12).
- Dependencias: `streamlit`, `pandas`, `numpy`, `reportlab`.

```bash
python -m venv venv
```

En Windows:

```powershell
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

En macOS/Linux:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

---

## Ejecución

```bash
streamlit run app.py
```

Streamlit mostrará en la terminal la dirección local de la aplicación (por
defecto, `http://localhost:8501`).

---

## Pruebas

```bash
python -m unittest discover -s tests -v
```

Las pruebas incluyen:

- Clasificación correcta con criterios B, criterios M, ambos o ninguno.
- Rechazo de hallazgos desconocidos y valores no booleanos.
- Reproducción de los dos casos clínicos publicados en la guía práctica de
  ADNEX:
  - Caso 1: benigno 4.7 %, borderline 1.6 %, estadio I 4.6 %,
    estadio II-IV 67.9 %, metastásico 21.2 %, RM 95.3 %.
  - Caso 2: benigno 59.1 %, borderline 18.7 %, estadio I 13.3 %,
    estadio II-IV 5.9 %, metastásico 3.0 %, RM 40.9 %.
- Coherencia de porcentajes y del Riesgo de Malignidad.
- Activación de las ecuaciones sin CA-125 cuando el valor es `None` o `<= 0`.
- Limitación de las proyecciones papilares a 4.
- Validación de rangos clínicos.
- Validación de los datos del caso (edad, lado, fecha no futura,
  identificador anonimizado).
- Cálculo de la proporción de tejido sólido a partir de los dos diámetros en
  milímetros, con limitación al 100 % ante mediciones inconsistentes.
- Generación del PDF consolidado con ADNEX, sin ADNEX y sin Simple Rules.

---

## Modelos implementados

### IOTA Simple Rules

| Criterios B (benignidad) | Criterios M (malignidad) |
| --- | --- |
| B1. Quiste unilocular | M1. Tumor sólido irregular |
| B2. Componente sólido < 7 mm | M2. Ascitis |
| B3. Sombras acústicas | M3. Al menos 4 proyecciones papilares |
| B4. Tumor multilocular liso < 100 mm | M4. Tumor multilocular sólido irregular >= 100 mm |
| B5. Sin flujo Doppler color | M5. Flujo Doppler color muy intenso |

### Modelo ADNEX

Categorías estimadas:

1. Benigno.
2. Tumor borderline (limítrofe).
3. Carcinoma invasivo en estadio I.
4. Carcinoma invasivo en estadio II-IV.
5. Enfermedad metastásica.

El Riesgo de Malignidad es la suma de las categorías 2 a 5.

Variables del modelo:

| Variable | Descripción | Codificación |
| --- | --- | --- |
| `age` | Edad | Años (18–100) |
| `ca125` | CA-125 sérico | U/mL; `None` o `<= 0` activa las ecuaciones sin CA-125 |
| `mdl` | Diámetro máximo de la lesión | mm (> 0) |
| `pst` | Proporción de tejido sólido | 0–1; se calcula como `componente_sólido / mdl` |
| `tcl` | Más de 10 lóculos quísticos | 0/1 |
| `nps` | Número de proyecciones papilares | 0–4 (4 = 4 o más) |
| `sha` | Sombras acústicas | 0/1 |
| `asc` | Ascitis | 0/1 |
| `onc` | Ecografía en centro oncológico especializado | 0/1 |

Ejemplo de uso:

```python
from utils.adnex_model import calculate_adnex

resultado = calculate_adnex(
    age=59,
    mdl=59,
    pst=1.0,
    tcl=0,
    nps=0,
    sha=0,
    asc=1,
    onc=1,
    ca125=153,
)

print(resultado.percentages)
print(resultado.malignancy_percentage)
```

La proporción de tejido sólido se obtiene a partir de las medidas en
milímetros, igual que en la calculadora oficial:

```python
from utils.adnex_model import calculate_solid_proportion

pst = calculate_solid_proportion(66.0, 27.0)  # 0.409090...
```

Los coeficientes se encuentran documentados en `utils/adnex_model.py` y
provienen de las ecuaciones oficiales publicadas por el grupo IOTA.

---

## Privacidad y anonimización

- La aplicación no solicita datos identificativos del paciente.
- No se escribe ningún dato clínico en disco.
- El PDF se construye en memoria y se entrega mediante descarga.
- El nombre del archivo solo contiene la fecha y la hora de generación.
- El informe indica expresamente que no contiene identificadores.

---

## Referencias

1. Timmerman D, et al. Simple ultrasound rules to distinguish between benign
   and malignant adnexal masses before surgery: prospective validation by IOTA
   group. *BMJ*. 2010;341:c6839.
   [doi:10.1136/bmj.c6839](https://doi.org/10.1136/bmj.c6839)
2. Van Calster B, et al. Evaluating the risk of ovarian cancer before surgery
   using the ADNEX model to differentiate between benign, borderline, early
   and advanced stage invasive, and secondary metastatic tumours: prospective
   multicentre diagnostic study. *BMJ*. 2014;349:g5920.
   [doi:10.1136/bmj.g5920](https://doi.org/10.1136/bmj.g5920)
3. Van Calster B, et al. Validation of models to diagnose ovarian cancer in
   patients managed surgically or conservatively: multicentre cohort study.
   *BMJ*. 2020;370:m2614. [doi:10.1136/bmj.m2614](https://doi.org/10.1136/bmj.m2614)
4. Van Calster B, et al. Practical guidance for applying the ADNEX model from
   the IOTA group to discriminate between different subtypes of adnexal tumors.
   *Facts Views Vis Obgyn*. 2015;7(1):32-41.
   [PMC4402441](https://pmc.ncbi.nlm.nih.gov/articles/PMC4402441/)
5. Barreñada L, et al. ADNEX risk prediction model for diagnosis of ovarian
   cancer: systematic review and meta-analysis of external validation studies.
   *BMJ Med*. 2024;3(1):e000817.
   [doi:10.1136/bmjmed-2023-000817](https://doi.org/10.1136/bmjmed-2023-000817)

---

## Versión

**SIEMA v1.0.0 — Sprint 1**

Implementación académica desarrollada como parte de un proyecto universitario.
Los modelos implementados son herramientas de estimación de riesgo; su
rendimiento en una población local debe validarse antes de un uso clínico
asistencial.
