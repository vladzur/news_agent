# ⚡ News Agent — Agente Inteligente de Pauta Editorial

**Curador automatizado de pauta periodística para La Chispa Sur**, medio digital independiente de izquierda, crítico del modelo neoliberal.

El agente recolecta noticias desde canales RSS y scraping web, las filtra por una ventana temporal de 7 días (168 horas) y utiliza el modelo **DeepSeek-V4-Pro** (vía API compatible con OpenAI SDK) para sintetizar **tres propuestas de pauta editorial semanal** con profundidad analítica, tono incisivo y narrativa ágil. También permite **escribir artículos completos (~1000 palabras)** a partir de cualquiera de las propuestas generadas.

---

## 🧠 Funcionalidades

### 1. Generación de pauta editorial semanal

Flujo automatizado que:

1. **Ingesta de noticias** — Obtiene artículos desde múltiples fuentes configuradas en `rss_feeds.json`:
   - **RSS**: Usa `feedparser` para canales RSS/Atom tradicionales.
   - **Scraping web**: Usa `requests` + `BeautifulSoup` con selectores CSS configurables por sitio, para medios sin feed RSS.
   - Tolerancia a fallos individuales: si un feed o scraping falla, continúa con el siguiente.
2. **Filtrado temporal** — Descarta noticias con más de 7 días (168 horas) de antigüedad, cubriendo la ventana semanal de lunes a domingo. Configurable.
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
├── rss_fetcher.py       # Ingesta RSS + despacho a scraping según método
├── scraper.py           # Scraping web con requests + BeautifulSoup (selectores CSS)
├── news_filter.py       # Ventana temporal (168h / 7 días), limpieza HTML, truncado
├── prompt_builder.py    # Construcción de system/user prompts editoriales
├── llm_client.py        # Cliente DeepSeek vía SDK OpenAI (modo compatible)
├── report_writer.py     # Escritura de reportes .md y artículos
└── article_writer.py    # Parseo de pauta + escritura de artículo completo
```

### Stack técnico

| Capa | Tecnología | Propósito |
|------|-----------|-----------|
| Ingesta RSS | `feedparser` | Parseo de canales RSS/Atom |
| Scraping web | `requests` + `beautifulsoup4` | Extracción de artículos desde sitios sin RSS con selectores CSS configurables |
| Cliente LLM | `openai` (SDK) | Conexión con DeepSeek API en modo compatible |
| Lenguaje | Python ≥ 3.10 | stdlib + 4 dependencias ligeras |
| Configuración | `.env` + `rss_feeds.json` | Separación de credenciales y fuentes |
| Testing | `pytest`, `pytest-mock`, `freezegun` | Tests unitarios para todos los módulos |

### Parámetros del modelo

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `model` | `deepseek-v4-pro` | Modelo principal (límite de salida: 384K tokens) |
| `temperature` | `0.5` | Balance creatividad/rigor factual |
| `max_tokens` (pauta) | `16384` | Presupuesto para razonamiento + 3 propuestas sobre ~1000 noticias semanales |
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

### 4. Configurar fuentes

Edita `rss_feeds.json` para agregar, quitar o modificar las fuentes de noticias. Se soportan dos métodos de ingesta:

#### Fuentes RSS (por defecto)

```json
[
    {
        "name": "Nombre del Medio",
        "url": "https://ejemplo.com/rss.xml"
    }
]
```

#### Fuentes con scraping web

Para medios que no disponen de feed RSS, usa `"method": "scraping"` con selectores CSS:

```json
[
    {
        "name": "Nombre del Medio",
        "url": "https://www.medio.cl",
        "method": "scraping",
        "selectors": {
            "article": "h2:has(a[href]), h3:has(a[href])",
            "title": "a[href]",
            "link": "a[href]",
            "summary": ".excerpt, .summary",
            "date": "time, .date"
        },
        "date_regex": "/(\\d{4})/(\\d{2})/(\\d{2})/",
        "date_format": "%Y/%m/%d",
        "link_prefix": "https://www.medio.cl",
        "request_headers": {}
    }
]
```

| Campo | Obligatorio | Descripción |
|-------|:-----------:|-------------|
| `name` | ✅ | Nombre descriptivo del medio |
| `url` | ✅ | URL del sitio web a scrapear |
| `method` | ✅ | Debe ser `"scraping"` para activar scraping |
| `selectors.article` | ✅ | Selector CSS para cada contenedor de artículo |
| `selectors.title` | ✅ | Selector CSS para el título (dentro del contenedor) |
| `selectors.link` | ❌ | Selector CSS para el enlace (por defecto usa el mismo que `title`) |
| `selectors.summary` | ❌ | Selector CSS para el resumen/extracto |
| `selectors.date` | ❌ | Selector CSS para la fecha de publicación |
| `date_regex` | ❌ | Regex para extraer la fecha desde la URL del artículo (ej: `/(\\d{4})/(\\d{2})/(\\d{2})/`) |
| `date_format` | ❌ | Formato `strptime` para parsear la fecha extraída |
| `link_prefix` | ❌ | Prefijo para resolver URLs relativas |
| `request_headers` | ❌ | Headers HTTP adicionales para la petición |

> **Nota:** Los selectores CSS deben coincidir con la estructura HTML real del sitio. Usa las herramientas de desarrollador del navegador para identificar los selectores correctos. Si el sitio cambia su estructura, solo necesitas actualizar los selectores en el JSON, sin tocar código.
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
| `MAX_TOKENS` | `16384` | Límite de tokens para generación de pauta semanal |
| `ARTICLE_MAX_TOKENS` | `16384` | Límite de tokens para escritura de artículo (~1000 palabras + razonamiento) |
| `REASONING_EFFORT` | `"high"` | Esfuerzo de razonamiento (`low`, `high`, `max`) |
| `TIME_WINDOW_HOURS` | `168` | Ventana de análisis en horas (7 días, lunes a domingo) |
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

- **Feed caído o scraping fallido** → registra el error, continúa con el siguiente medio.
- **0 noticias en ventana** → aborta antes de llamar a la API (ahorro de tokens).
- **API key ausente** → error explícito de configuración al inicio.
- **API devuelve vacío** → aborta con mensaje claro. Si `content` es `None` pero existe `reasoning_content`, se usa este último como fallback automático.
- **Directorio de salida inexistente** → `IOError` antes de escribir.
- **Configuración de scraping inválida** → error descriptivo al cargar `rss_feeds.json` si faltan selectores obligatorios.

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
