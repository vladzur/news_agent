# 📋 Especificaciones de Funcionamiento: Agente Inteligente de Contenidos

**Proyecto:** Curador de Pauta Editorial Automatizado

**Medio:** La Chispa Sur

**Versión del Motor:** 1.0.0 (Python + DeepSeek API)

## 1. Objetivo General

Automatizar la recopilación, filtrado y análisis de la agenda noticiosa nacional e internacional mediante la lectura de canales RSS seleccionados, utilizando el modelo de lenguaje **DeepSeek-V4-Pro** para sintetizar y proponer **cinco (5) líneas editoriales semanales —tres (3) de foco nacional y dos (2) de foco internacional—** de alto impacto, profundidad analítica y narrativa ágil.

## 2. Arquitectura y Componentes del Sistema

### 2.1. Capa de Ingesta (Data Ingestion)

- **Mecanismo:** Extracción de datos sin intermediarios mediante la librería `feedparser`.
  
- **Fuentes de Entrada:** Matriz de canales RSS gestionada en un diccionario/configuración JSON independiente del código principal.
  
- **Frecuencia de Ejecución:** El agente operará bajo demanda o mediante una tarea programada (`cronjob`) de manera semanal (recomendado: domingos a las 23:00 hrs o lunes a las 07:00 hrs).
  

### 2.2. Capa de Filtrado y Ventana de Tiempo

- **Ventana Operativa:** El agente sólo procesará noticias cuya etiqueta de publicación (`published_parsed` o `updated_parsed`) se encuentre dentro de las **últimas 48 horas** respecto a la ejecución del script.
  
- **Truncamiento de Datos:** Para optimizar la ventana de contexto y evitar ruido, cada noticia se limitará a:
  
  - Título completo.
    
  - Nombre del medio emisor.
    
  - Resumen o descripción truncado a un máximo de **200 caracteres** (limpiando cualquier etiqueta HTML residual).
    

### 2.3. Capa de Inteligencia (Cerebro IA)

- **Proveedor:** DeepSeek API.
  
- **Modelo Especificado:** `deepseek-v4-pro` (o endpoint compatible vía OpenAI SDK).
  
- **Hiperparámetros de Control:**
  
  - `temperature`: **0.5** (Garantiza un balance entre creatividad periodística y estricta fidelidad a los hechos reportados, minimizando alucinaciones).
    
  - `base_url`: `[https://api.deepseek.com/v1](https://api.deepseek.com/v1)`.
    

## 3. Directrices Editoriales Obligatorias (System Prompt)

El agente debe ceñirse estrictamente al perfil de identidad de *La Chispa Sur*:

- **Tono:** Incisivo, analítico, audaz y de lectura ágil. No debe limitarse a replicar titulares del *mainstream*; su valor radica en **conectar puntos ocultos**, encontrar contradicciones o proponer enfoques de fondo (ensayo, reportaje o columnas de opinión).
  
- **Restricción de Volumen:** El agente debe entregar **exactamente cinco (5) propuestas** por informe: **tres (3) de ámbito nacional** y **dos (2) de ámbito internacional**, estas últimas con énfasis en hechos que conmocionan al mundo, pueblos oprimidos y políticas imperialistas que afectan la estabilidad mundial. Ni más, ni menos.
  

## 4. Formato de Salida Requerido (Output Schema)

La respuesta del agente debe estructurarse obligatoriamente en formato **Markdown (`.md`)**, guardarse localmente con la estampa de fecha correspondiente (`pauta_semanal_AAAA_MM_DD.md`) y respetar la siguiente estructura de campos:

Markdown

```
# ⚡ Pauta Editorial Sugerida - La Chispa Sur
**Fecha de Generación:** [Insertar Fecha]  
**Notas Procesadas:** [Cantidad de artículos analizados]

---

## 1. [TÍTULO GANCHO DEL ARTÍCULO 1]
*   **Enfoque Editorial:** [Explicación de 3 a 5 líneas de por qué este tema es crucial, cómo se cruza la información de los diferentes medios analizados y cuál es el valor agregado que dará La Chispa Sur].
*   **Puntos Clave a Desarrollar:**
    1. [Arista de investigación o contexto fáctico 1]
    2. [Arista de investigación o contexto fáctico 2]
    3. [Ángulo crítico, proyección o pregunta abierta para el lector]

## 2. [TÍTULO GANCHO DEL ARTÍCULO 2]
...

## 3. [TÍTULO GANCHO DEL ARTÍCULO 3]
...

## 4. [TÍTULO GANCHO DEL ARTÍCULO 4]
...

## 5. [TÍTULO GANCHO DEL ARTÍCULO 5]
...
```

## 5. Manejo de Errores y Robustez (Fail-Safe)

- **Fallas de Conexión en Feeds:** Si un canal RSS falla (caída del servidor de origen o cambio de URL), el script debe registrar el error en la terminal mediante una excepción estructurada (`try-except`) y **continuar inmediatamente** con el siguiente medio de la lista sin abortar la ejecución.
  
- **Ausencia de Datos:** En caso de que la recolección sume 0 noticias en la ventana de 48 horas, el agente detendrá el flujo antes de invocar la API de DeepSeek, generando un log de advertencia para evitar consumo innecesario de tokens.
  
- **Fallo de API Key:** El script validará la existencia de la variable de entorno `DEEPSEEK_API_KEY` antes de iniciar. Si no se encuentra, arrojará un error explícito de configuración.

- **Respuesta sin contenido visible:** Como `max_tokens` es un presupuesto compartido entre el razonamiento interno y el texto final, un razonamiento extenso puede agotarlo y dejar `content` vacío. En ese caso el cliente **reintenta la llamada con el razonamiento desactivado y un presupuesto ampliado**; si el reintento tampoco devuelve contenido, la ejecución falla de forma explícita. El razonamiento interno nunca se escribe en un archivo de salida, porque no es texto publicable.

- **Respuesta que no es un artículo:** Antes de escribir el archivo, se verifica que la respuesta traiga titular de nivel 1 y al menos un subtítulo de sección. Si no los trae, se descarta y se aborta sin crear archivo, para no publicar contenido inválido.

## 6. Subsistema de Repurposing para Redes Sociales (RRSS)

### 6.1. Objetivo

Transformar un artículo ya publicado en piezas multiplataforma para **X/Twitter, Facebook e Instagram**, mediante un flujo local que se ejecuta desde el mismo punto de entrada CLI del agente:

```
python -m news_agent --socialize articulos/articulo_1_slug.md --output ./social
```

El subsistema produce tres familias de artefactos: **copys estructurados**, **prompts visuales en inglés** y **banners renderizados localmente**. No publica nada en las plataformas ni genera las imágenes finales: entrega al equipo editorial el material listo para publicar y para pegar en un generador de imágenes.

### 6.2. Entrada

El único origen admitido es un **artículo Markdown ya publicado** (`articulos/articulo_N_slug.md`), con la estructura que produce el agente: titular de nivel 1, firma, separador horizontal, lead, secciones de nivel 2 y bloque final de fuentes.

- **Formato inválido:** un archivo sin titular de nivel 1 se rechaza con un error explícito de parseo.
- **Guardia de material:** si el cuerpo del artículo tiene menos de `SOCIAL_MIN_ARTICLE_WORDS` (150) palabras, el flujo se detiene **antes** de invocar la API para evitar consumo innecesario de tokens.
- **Material extraído:** titular, firma, lead, secciones, fuentes citadas, cifras detectadas por patrón y oraciones candidatas a cita, ordenadas por potencial editorial. Todo lo que se genere después se valida contra este material.

### 6.3. Capa de generación de copys

- **Salida JSON, no Markdown.** A diferencia de la pauta y de los artículos, el subsistema pide al modelo un objeto JSON estructurado con el contrato completo de la pieza.
- **Extracción defensiva.** La respuesta se parsea tolerando bloques de código Markdown, texto explicativo alrededor y comas finales sueltas. Si no se obtiene un objeto válido, se reintenta la llamada con una nota de corrección, hasta `SOCIAL_JSON_MAX_RETRIES` veces.
- **Campos del contrato:** `hooks`, `summary`, `hook`, `quote_card`, `key_figures`, `cta`, `alt_text`, `x`, `facebook`, `instagram`.

#### Reglas aplicadas en código, no delegadas al modelo

| Regla | Implementación |
|-------|----------------|
| Hilo de 5 a 7 tweets | Se recorta al máximo y se advierte si queda por debajo del mínimo |
| 280 caracteres por tweet | Recorte en cierre de oración o en espacio, con puntos suspensivos |
| `x.thread[0]` es el gancho | Se fuerza la coherencia entre `hook_tweet` y el primer elemento del hilo |
| Hashtags publicables | Se quita el `#`, se unen palabras (`#La Araucania` → `#LaAraucania`) y se aplica el tope de cada plataforma |
| Hashtags dentro del tweet de cierre | Se reserva espacio y se recorta el texto si no caben; además se eliminan los hashtags que el modelo haya dejado dentro del cuerpo del tweet, del post o de la caption, para que se publiquen una sola vez |
| Límite de Facebook e Instagram | Recorte al máximo declarado en la configuración |
| Cita literal | Se verifica palabra por palabra; si no proviene del artículo, se reemplaza por una oración candidata verificada o por el lead |
| Cifras verificables | Se descartan las cifras que no aparecen en el texto; si ninguna se verifica, se usan las detectadas en el artículo |
| Textos alternativos | Se completan y se recortan al límite de cada plataforma (X 300, Facebook 200, Instagram 100 caracteres) |

### 6.4. Capa de prompts visuales

- **Idioma obligatorio: inglés.** Un prompt por relación de aspecto, filtrado por las plataformas pedidas: `16:9` (X y Facebook), `1:1` (feed de Instagram) y `9:16` (stories).
- **Restricciones verificadas en código**, no solo sugeridas en el prompt:
  - Prohibido describir **texto, letras, números o tipografía** en la imagen, porque los modelos de difusión los renderizan como artefactos.
  - Prohibido representar **personas reales identificables** (evita suplantación de figuras públicas): el poder, el Estado o los pueblos se representan de forma simbólica.
  - Prohibida la **violencia explícita**.
  - Prompt positivo entre 25 y 200 palabras, en inglés.
- **Salida por aspecto:** prompt positivo, prompt negativo (el de marca más los agregados específicos del artículo, sin duplicar términos), variante lista para Midjourney con sus flags (`--ar`, estilo, `--v`, `--no`) y parámetros sugeridos (pasos, guidance, sampler).

### 6.5. Capa de assets locales (Pillow)

Dos plantillas declaradas en la configuración, renderizadas en los formatos pedidos:

| Plantilla | Contenido | Formatos por defecto |
|-----------|-----------|----------------------|
| `headline_card` | Etiqueta de marca, titular del artículo y barra inferior con handle y sitio | X 1600×900, Facebook 1200×630, IG feed 1080×1080, IG story 1080×1920 |
| `quote_card` | Comilla destacada, cita textual y atribución | IG feed 1080×1080, IG story 1080×1920 |

- **Diseño parametrizado por escala:** todas las plantillas se dibujan con un factor `ancho / 1080`, de modo que una sola implementación sirve para los cuatro tamaños sin reescalar bitmaps.
- **Ajuste tipográfico automático:** el titular y la cita se envuelven y reducen de tamaño hasta caber en su caja; si ni con el tamaño mínimo entran, se recortan a la cantidad de líneas permitida.
- **Zonas seguras:** en el formato vertical se respetan las bandas superior e inferior declaradas en la configuración, porque la interfaz de la plataforma las tapa.
- **Logo de la marca:** si `brand.logo_path` apunta a un PNG válido, se recorta su padding transparente antes de escalarlo —para usar el arte real y no el lienzo del archivo—, se ajusta a `brand.logo_height_ratio` del ancho del lienzo y se pega en la esquina superior derecha. El ancho se limita al 22% del lienzo para que no invada la etiqueta de marca, y la franja superior del diseño se dimensiona con el mayor de los dos elementos, de modo que un logo alto desplaza el titular en lugar de superponerse a él. Un logo ausente, nulo o ilegible no interrumpe el renderizado: el banner se genera sin logo y se advierte en el log.
- **Fuentes:** se resuelve primero la ruta declarada en `brand.fonts`, luego el directorio de `SOCIAL_FONT_DIR` y después las rutas habituales del sistema (DejaVu, Liberation, Noto o Arial). Si ninguna existe, se usa la fuente por defecto de Pillow y se advierte en el log.
- **Aislamiento de fallos:** un banner que falla al renderizar no interrumpe el resto del lote; queda registrado en el manifiesto como pendiente.

### 6.6. Formato de salida (bundle)

Cada ejecución escribe una carpeta autocontenida `social/AAAA_MM_DD_slug-del-titulo/` con los copys en JSON, los prompts visuales en JSON, un Markdown listo para copiar y pegar por plataforma, los PNG de los banners en `assets/` y un `manifest.json` que registra qué se generó, qué falló y con qué artículo se produjo.

El campo `quote_card.verbatim` del JSON de copys —repetido como `verified_quote` en el manifiesto— indica si la cita destacada se verificó palabra por palabra contra el artículo de origen.

### 6.7. Configuración externa

La identidad visual y los límites viven en `social_config.json`, versionado en la raíz del proyecto y validado al cargarse, siguiendo el mismo criterio que `rss_feeds.json` para las fuentes:

| Sección | Contenido | Obligatoria |
|---------|-----------|:-----------:|
| `brand` | Nombre, handle, sitio, logo opcional, paleta de colores y tipografías por rol | ✅ |
| `platforms` | Límite de caracteres, largo del hilo y tope de hashtags por plataforma. Sobrescriben los valores por defecto de `config.py` | ❌ |
| `banners.templates` / `banners.sizes` | Matriz plantilla → formatos y tamaño de cada formato | ✅ |
| `banners.safe_zone` | Bandas no utilizables de los formatos verticales | ❌ |
| `visual_prompts` | Estilo, prompt negativo, sufijo de Midjourney, relaciones de aspecto y parámetros sugeridos | ✅ |

Un color mal escrito, un tamaño inválido o una plantilla que apunte a un formato inexistente se detectan al cargar el archivo, con un mensaje que indica el campo culpable.

### 6.8. Estructura del subsistema

| Módulo (`news_agent/social/`) | Responsabilidad |
|-------------------------------|-----------------|
| `orchestrator.py` | Coordina el flujo completo y devuelve el resumen del bundle |
| `article_source.py` | Parsea el artículo de origen y extrae su material reutilizable |
| `prompt_builder.py` | Construye los prompts de copys (español) y de imágenes (inglés) |
| `copy_generator.py` | Genera y valida los copys contra los límites de cada plataforma |
| `visual_prompts.py` | Genera y valida los prompts visuales en inglés |
| `banner_renderer.py` | Renderiza los banners con Pillow |
| `platform_specs.py` | Resuelve los límites por plataforma y filtra por formato |
| `text_utils.py` | Recorte por caracteres y normalización de hashtags |
| `json_utils.py` | Extracción defensiva de JSON de las respuestas del modelo |
| `models.py` | Dataclasses de los artefactos del subsistema |
| `writer.py` | Escribe el bundle de salida y su manifiesto |

### 6.9. Manejo de errores y robustez

- **JSON inválido o incompleto** → reintento con nota de corrección, hasta agotar `SOCIAL_JSON_MAX_RETRIES`.
- **Copys imposibles de validar** → se aborta sin escribir un bundle a medias.
- **Prompts visuales fallidos** → el bundle se escribe igualmente con los copys y los banners, y el manifiesto lo refleja.
- **Banner fallido** → se registra el error y el resto del lote continúa.
- **Directorio de salida inexistente** → se crea automáticamente (incluidos los directorios intermedios).
- **Artículo inexistente, vacío o sin titular** → error explícito de parseo y salida con código distinto de cero.
- **API key ausente** → error explícito de configuración antes de cualquier llamada.
- **Combinación de argumentos inválida** (`--socialize` junto a `--feeds`, `--debug`, `--write-article` o `--article`, o banderas del subsistema sin `--socialize`) → error de uso en `stderr` y salida con código 2.
