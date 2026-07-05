# ⚡ News Agent — Agente Inteligente de Pauta Editorial

**Curador automatizado de pauta periodística para La Chispa Sur**, medio digital independiente de izquierda, crítico del modelo neoliberal.

El agente recolecta noticias desde canales RSS, las filtra por una ventana temporal de 72 horas y utiliza el modelo **DeepSeek-V4-Pro** (vía API compatible con OpenAI SDK) para sintetizar **tres propuestas de pauta editorial semanal** con profundidad analítica, tono incisivo y narrativa ágil. También permite **escribir artículos completos (~1000 palabras)** a partir de cualquiera de las propuestas generadas.

---

## 🧠 Funcionalidades

### 1. Generación de pauta editorial semanal

Flujo automatizado que:

1. **Ingesta RSS** — Obtiene artículos desde múltiples fuentes configuradas en `rss_feeds.json` usando `feedparser`, con tolerancia a fallos individuales por feed.
2. **Filtrado temporal** — Descarta noticias con más de 72 horas de antigüedad (configurable).
3. **Limpieza HTML** — Elimina etiquetas, comentarios, scripts y decodifica entidades HTML de los resúmenes.
4. **Truncado inteligente** — Recorta resúmenes a 200 caracteres sin cortar palabras a la mitad.
5. **Análisis con IA** — Envía los artículos filtrados a DeepSeek-V4-Pro con un system prompt que define la identidad editorial de La Chispa Sur (izquierda independiente, rigor periodístico, enfoque chileno).
6. **Reporte Markdown** — Genera un archivo `pauta_semanal_AAAA_MM_DD.md` con tres propuestas estructuradas: título gancho, enfoque editorial, puntos clave a desarrollar y fuentes sugeridas para ampliar.

### 2. Escritura de artículo completo

Toma una propuesta específica de la pauta (1, 2 o 3) y la expande a un artículo de **~1000 palabras**:

- Parsea automáticamente el archivo de pauta para extraer título, enfoque, puntos clave y fuentes.
- Usa un system prompt de redactor periodístico (identidad La Chispa Sur).
- Genera un artículo con lead, desarrollo por secciones y fuentes citadas.
- Guarda el resultado como `articulo_N_slug-del-titulo.md`.

### 3. CLI unificado

El punto de entrada `python -m news_agent` ofrece dos modos:

| Modo | Comando |
|------|---------|
| Generar pauta | `python -m news_agent --feeds rss_feeds.json --output ./reportes` |
| Escribir artículo | `python -m news_agent --write-article reportes/pauta_semanal_AAAA_MM_DD.md --article 1 --output ./articulos` |

Flags adicionales:

- `--verbose`: Activa logging nivel DEBUG.
- `--output`: Directorio donde guardar los archivos generados.

---

## 🏗️ Arquitectura

```
news_agent/
├── __main__.py          # Punto de entrada CLI (argparse)
├── orchestrator.py      # Orquestador del pipeline completo
├── config.py            # Carga de .env, validación de API key, feeds JSON
├── rss_fetcher.py       # Ingesta RSS con feedparser + tolerancia a fallos
├── news_filter.py       # Ventana temporal (72h), limpieza HTML, truncado
├── prompt_builder.py    # Construcción de system/user prompts editoriales
├── llm_client.py        # Cliente DeepSeek vía SDK OpenAI (modo compatible)
├── report_writer.py     # Escritura de reportes .md y artículos
└── article_writer.py    # Parseo de pauta + escritura de artículo completo
```

### Stack técnico

| Capa | Tecnología | Propósito |
|------|-----------|-----------|
| Ingesta RSS | `feedparser` | Parseo de canales RSS/Atom |
| Cliente LLM | `openai` (SDK) | Conexión con DeepSeek API en modo compatible |
| Lenguaje | Python ≥ 3.10 | Sin dependencias pesadas, solo stdlib + dos librerías |
| Configuración | `.env` + `rss_feeds.json` | Separación de credenciales y fuentes |
| Testing | `pytest`, `pytest-mock`, `freezegun` | Tests unitarios para todos los módulos |

### Parámetros del modelo

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `model` | `deepseek-v4-pro` | Modelo principal (límite de salida: 384K tokens) |
| `temperature` | `0.5` | Balance creatividad/rigor factual |
| `max_tokens` (pauta) | `8192` | Suficiente para tres propuestas detalladas |
| `max_tokens` (artículo) | `16384` | El doble que pauta: margen para razonamiento + ~1000 palabras |
| `reasoning_effort` | `high` | Razonamiento profundo habilitado |
| `base_url` | `https://api.deepseek.com/v1` | Endpoint compatible OpenAI |

### Modo thinking y distribución de tokens

DeepSeek-V4-Pro opera con **thinking mode activado** (`reasoning_effort: high`). En este modo, los tokens de salida se dividen en dos campos:

- **`reasoning_content`**: cadena de razonamiento interna (CoT) que el modelo usa para estructurar el análisis.
- **`content`**: respuesta final visible que se escribe en el archivo de salida.

El parámetro `max_tokens` es el **presupuesto total compartido** entre ambos campos. El razonamiento típicamente consume el 60-80% del presupuesto. Por eso la escritura de artículos usa 16K tokens: necesita espacio suficiente para que el modelo razone sobre estructura, tono y fuentes **antes** de producir el artículo final de ~1000 palabras.

Si el modelo agota el presupuesto en razonamiento y `content` queda vacío, el cliente tiene un **fallback automático** que rescata `reasoning_content` como último recurso para no perder la ejecución.

---

## 🚀 Instalación y uso

### Requisitos

- Python 3.10 o superior
- Una [API key de DeepSeek](https://platform.deepseek.com/api_keys)

### 1. Clonar el repositorio

```bash
git clone <repo-url> && cd news_agent
```

### 2. Crear entorno virtual e instalar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Configurar API key

```bash
cp .env.example .env
# Editar .env y reemplazar con tu key real:
# DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4. Configurar fuentes RSS

Edita `rss_feeds.json` para agregar, quitar o modificar los canales RSS. El formato es:

```json
[
    {
        "name": "Nombre del Medio",
        "url": "https://ejemplo.com/rss.xml"
    }
]
```

### 5. Ejecutar

```bash
# Generar pauta editorial semanal
python -m news_agent --feeds rss_feeds.json --output ./reportes

# Escribir artículo completo desde propuesta #1
python -m news_agent --write-article reportes/pauta_semanal_2026_07_04.md --article 1 --output ./articulos
```

### 6. Ejecutar tests

```bash
pip install -e ".[dev]"
pytest
```

---

## ⚙️ Configuración avanzada

Las constantes principales se encuentran en [news_agent/config.py](news_agent/config.py) y pueden ajustarse según necesidades:

| Constante | Valor por defecto | Descripción |
|-----------|-------------------|-------------|
| `DEEPSEEK_MODEL` | `"deepseek-v4-pro"` | Modelo a utilizar |
| `TEMPERATURE` | `0.5` | Creatividad del sampling (0.0–2.0) |
| `MAX_TOKENS` | `8192` | Límite de tokens para generación de pauta |
| `ARTICLE_MAX_TOKENS` | `16384` | Límite de tokens para escritura de artículo (~1000 palabras + razonamiento) |
| `REASONING_EFFORT` | `"high"` | Esfuerzo de razonamiento (`low`, `high`, `max`) |
| `TIME_WINDOW_HOURS` | `72` | Ventana de análisis en horas |
| `SUMMARY_MAX_CHARS` | `200` | Caracteres máximos por resumen |

### Automatización con cron

Para ejecutar el agente de forma semanal (recomendado: domingo a las 23:00 o lunes a las 07:00):

```bash
# Ejemplo: todos los lunes a las 07:00 hrs
0 7 * * 1 cd /ruta/al/news_agent && /ruta/al/.venv/bin/python -m news_agent --feeds rss_feeds.json --output ./reportes
```

---

## 🛡️ Manejo de errores

El agente implementa fail-safe en cada etapa del pipeline:

- **Feed caído** → registra el error, continúa con el siguiente medio.
- **0 noticias en ventana** → aborta antes de llamar a la API (ahorro de tokens).
- **API key ausente** → error explícito de configuración al inicio.
- **API devuelve vacío** → aborta con mensaje claro. Si `content` es `None` pero existe `reasoning_content`, se usa este último como fallback automático.
- **Directorio de salida inexistente** → `IOError` antes de escribir.

---

## 📝 Output de ejemplo

### Pauta semanal (`reportes/pauta_semanal_AAAA_MM_DD.md`)

```markdown
# ⚡ Pauta Editorial Sugerida - La Chispa Sur
**Fecha de Generación:** 2026-07-04
**Notas Procesadas:** 200

---

## 1. [TÍTULO GANCHO DEL ARTÍCULO 1]
*   **Enfoque Editorial:** [3-5 líneas explicando el valor agregado...]
*   **Puntos Clave a Desarrollar:**
    1. [Arista de investigación 1]
    2. [Arista de investigación 2]
    3. [Ángulo crítico, proyección o pregunta abierta]
*   **Fuentes Sugeridas para Ampliar:**
    *   [Medio 1]: [Qué aporta]
    *   [Medio 2]: [Qué aporta]

## 2. [TÍTULO GANCHO DEL ARTÍCULO 2]
...
```

### Artículo completo (`articulos/articulo_1_slug-del-titulo.md`)

Artículo de ~1000 palabras con lead periodístico, desarrollo en 3 secciones con subtítulos, y fuentes citadas al final. Ver ejemplo real en [articulos/](articulos/).

---

## 🧪 Desarrollo

```bash
# Instalar dependencias de desarrollo
pip install -e ".[dev]"

# Ejecutar tests
pytest

# Ejecutar tests con cobertura
pytest --cov=news_agent
```
