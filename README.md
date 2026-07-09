# ⚡ News Agent — Agente Inteligente de Pauta Editorial

**Curador automatizado de pauta periodística para La Chispa Sur**, medio digital independiente de izquierda, crítico del modelo neoliberal.

El agente recolecta noticias desde canales RSS y scraping web, las filtra por una ventana temporal de 7 días (168 horas), enriquece los resúmenes cortos extrayendo el contenido completo de los artículos con trafilatura, y utiliza el modelo **DeepSeek-V4-Pro** (vía API compatible con OpenAI SDK) para sintetizar **tres propuestas de pauta editorial semanal** con profundidad analítica, tono incisivo y narrativa ágil. También permite **escribir artículos completos (~1000 palabras)** a partir de cualquiera de las propuestas generadas.

---

## 🧠 Funcionalidades

### 1. Generación de pauta editorial semanal

Flujo automatizado que:

1. **Ingesta de noticias** — Obtiene artículos desde múltiples fuentes configuradas en `rss_feeds.json`:
   - **RSS**: Usa `feedparser` para canales RSS/Atom tradicionales.
   - **Scraping web**: Usa `requests` + `BeautifulSoup` con selectores CSS configurables por sitio, para medios sin feed RSS.
   - Tolerancia a fallos individuales: si un feed o scraping falla, continúa con el siguiente.
2. **Enriquecimiento de contenido** — Cuando el resumen RSS de un artículo es demasiado corto para un análisis de calidad (< 150 caracteres), el agente extrae el texto completo del artículo desde su URL usando `trafilatura`. Procesamiento paralelo con rate limiting por dominio y caché en archivo JSON para no re-descargar URLs ya visitadas. El enriquecimiento es best-effort: si falla, se conserva el resumen RSS original sin interrumpir el pipeline.
3. **Filtrado temporal** — Descarta noticias con más de 7 días (168 horas) de antigüedad, cubriendo la ventana semanal de lunes a domingo. Configurable.
4. **Limpieza HTML** — Elimina etiquetas, comentarios, scripts y decodifica entidades HTML de los resúmenes.
5. **Truncado inteligente** — Recorta resúmenes a 700 caracteres sin cortar palabras a la mitad.
6. **Guardado intermedio de depuración (opcional)** — Con el flag `--debug`, guarda un archivo JSON con los artículos procesados (resumen RSS original, contenido extraído y resumen final) para comparar y ajustar el prompt.
7. **Análisis con IA** — Envía los artículos filtrados a DeepSeek-V4-Pro con un system prompt que define la identidad editorial de La Chispa Sur (izquierda independiente, rigor periodístico, enfoque chileno, foco territorial en Villarrica y La Araucanía).
8. **Reporte Markdown** — Genera un archivo `pauta_semanal_AAAA_MM_DD.md` con tres propuestas estructuradas: título gancho, enfoque editorial, puntos clave a desarrollar y fuentes sugeridas para ampliar. La cabecera (fecha y cantidad de notas) se genera automáticamente desde el código para garantizar precisión.

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
| Generar pauta + debug | `python -m news_agent --feeds rss_feeds.json --output ./reportes --debug` |
| Escribir artículo | `python -m news_agent --write-article reportes/pauta_semanal_AAAA_MM_DD.md --article 1 --output ./articulos` |

Flags adicionales:

- `--verbose`: Activa logging nivel DEBUG para diagnóstico detallado.
- `--output`: Directorio donde guardar los archivos generados.
- `--debug`: Guarda un archivo JSON intermedio en `debug/articulos_procesados_YYYY_MM_DD.json` con los datos completos de cada artículo (resumen RSS, contenido extraído y resumen final enviado al LLM) para depuración y ajuste de prompts.

---

## 🏗️ Arquitectura

```
news_agent/
├── __main__.py            # Punto de entrada CLI (argparse)
├── orchestrator.py        # Orquestador del pipeline completo
├── config.py              # Carga de .env, validación de API key, feeds JSON
├── rss_fetcher.py         # Ingesta RSS + despacho a scraping según método
├── scraper.py             # Scraping web con requests + BeautifulSoup (selectores CSS)
├── content_enricher.py    # Extracción de texto completo con trafilatura + caché
├── news_filter.py         # Ventana temporal (168h / 7 días), limpieza HTML, truncado
├── intermediate_writer.py # Escritura de archivo JSON intermedio para depuración
├── prompt_builder.py      # Construcción de system/user prompts editoriales (~545 líneas)
├── llm_client.py          # Cliente DeepSeek vía SDK OpenAI (modo compatible)
├── report_writer.py       # Escritura de reportes .md y artículos
└── article_writer.py      # Parseo de pauta + escritura de artículo completo
```

### Stack técnico

| Capa | Tecnología | Propósito |
|------|-----------|-----------|
| Ingesta RSS | `feedparser` | Parseo de canales RSS/Atom |
| Scraping web | `requests` + `beautifulsoup4` | Extracción de artículos desde sitios sin RSS con selectores CSS configurables |
| Enriquecimiento | `trafilatura` | Extracción del texto completo de artículos con resúmenes RSS insuficientes |
| Cliente LLM | `openai` (SDK) | Conexión con DeepSeek API en modo compatible |
| Lenguaje | Python ≥ 3.10 | stdlib + 5 dependencias |
| Configuración | `.env` + `rss_feeds.json` | Separación de credenciales y fuentes |
| Testing | `pytest`, `pytest-mock`, `freezegun` | Tests unitarios para todos los módulos |

### Parámetros del modelo

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `model` | `deepseek-v4-pro` | Modelo principal (límite de salida: 384K tokens) |
| `temperature` | `0.1` | Baja temperatura para maximizar rigurosidad factual y minimizar alucinaciones |
| `max_tokens` (pauta) | `16384` | Presupuesto compartido entre razonamiento y contenido para ~1000+ noticias semanales |
| `max_tokens` (artículo) | `4069` | Suficiente para razonamiento + artículo final de ~1000 palabras |
| `reasoning_effort` | `high` | Razonamiento profundo habilitado |
| `base_url` | `https://api.deepseek.com/v1` | Endpoint compatible OpenAI |

### Modo thinking y distribución de tokens

DeepSeek-V4-Pro opera con **thinking mode activado** (`reasoning_effort: high`). En este modo, los tokens de salida se dividen en dos campos:

- **`reasoning_content`**: cadena de razonamiento interna (CoT) que el modelo usa para estructurar el análisis.
- **`content`**: respuesta final visible que se escribe en el archivo de salida.

El parámetro `max_tokens` es el **presupuesto total compartido** entre ambos campos. El razonamiento típicamente consume el 60-80% del presupuesto. Para la pauta semanal se usan 16K tokens para dar espacio al razonamiento sobre grandes volúmenes de noticias (~1000+ artículos). Para la escritura de artículos se usan ~4K tokens, ya que el modelo solo necesita razonar sobre una propuesta concreta.

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
        "enrich": false,
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
| `enrich` | ❌ | Controla si se extrae el contenido completo de artículos con resúmenes cortos. Por defecto `true`. Usar `false` para medios donde el scraping ya obtiene resúmenes completos y no se justifica una petición HTTP adicional (ej: El Mostrador) |
| `min_summary_length` | ❌ | Umbral de longitud mínima de resumen (en caracteres) por debajo del cual se intenta enriquecer. Si no se especifica, usa el default global (150) |
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

### 5. Ejecutar

```bash
# Generar pauta editorial semanal
python -m news_agent --feeds rss_feeds.json --output ./reportes

# Generar pauta con archivo de depuración intermedio
python -m news_agent --feeds rss_feeds.json --output ./reportes --debug

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
| `TEMPERATURE` | `0.1` | Temperatura de sampling (0.0–2.0). Valor bajo para privilegiar precisión factual |
| `MAX_TOKENS` | `16384` | Límite de tokens para generación de pauta semanal |
| `ARTICLE_MAX_TOKENS` | `4069` | Límite de tokens para escritura de artículo (~1000 palabras + razonamiento) |
| `REASONING_EFFORT` | `"high"` | Esfuerzo de razonamiento (`"low"`, `"high"`, `"max"`) |
| `TIME_WINDOW_HOURS` | `168` | Ventana de análisis en horas (7 días, lunes a domingo) |
| `SUMMARY_MAX_CHARS` | `700` | Caracteres máximos por resumen. Amplio para preservar leads, cifras y atribuciones necesarias para la verificación factual |
| `FULL_CONTENT_FETCH_ENABLED` | `True` | Control global de enriquecimiento de contenido |
| `MIN_SUMMARY_LENGTH` | `150` | Si el resumen RSS tiene menos de esto, se intenta extraer el texto completo |
| `FULL_CONTENT_TIMEOUT` | `15` | Timeout HTTP (segundos) para cada extracción de artículo |
| `FULL_CONTENT_DELAY` | `1.0` | Pausa entre peticiones al mismo dominio (segundos) |
| `FULL_CONTENT_MAX_WORKERS` | `4` | Hilos paralelos para extracción de contenido |
| `FULL_CONTENT_CACHE_DIR` | `"cache"` | Directorio para caché de contenido extraído |

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
- **Extracción de contenido fallida** → conserva el resumen RSS original. El enriquecimiento es best-effort y nunca interrumpe el pipeline.
- **Timeout en trafilatura** → timeout configurable por hilo; si se excede, se descarta la extracción y se usa el resumen RSS.
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
**Fecha de Generación:** 2026-07-08
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

### Archivo de depuración (`debug/articulos_procesados_YYYY_MM_DD.json`)

Al usar `--debug`, se genera un JSON con cada artículo procesado, permitiendo comparar:

- `summary_raw`: resumen RSS original
- `full_content`: contenido completo extraído (si se logró enriquecer)
- `summary_clean`: resumen final enviado al LLM

### Artículo completo (`articulos/articulo_N_slug-del-titulo.md`)

Artículo de ~1000 palabras con lead periodístico, desarrollo en 3 secciones con subtítulos, y fuentes citadas al final. Ver ejemplos reales en [articulos/](articulos/).

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
