# 📋 Especificaciones de Funcionamiento: Agente Inteligente de Contenidos

**Proyecto:** Curador de Pauta Editorial Automatizado

**Medio:** La Chispa Sur

**Versión del Motor:** 1.0.0 (Python + DeepSeek API)

## 1. Objetivo General

Automatizar la recopilación, filtrado y análisis de la agenda noticiosa nacional e internacional mediante la lectura de canales RSS seleccionados, utilizando el modelo de lenguaje **DeepSeek-Flash** para sintetizar y proponer **cinco (5) líneas editoriales semanales —tres (3) de foco nacional y dos (2) de foco internacional—** de alto impacto, profundidad analítica y narrativa ágil.

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
  
- **Modelo Especificado:** `deepseek-flash` (o endpoint compatible vía OpenAI SDK).
  
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
python -m news_agent social --platforms x,instagram
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
- **Estilo por defecto: arte digital vívido y caricatura editorial estilizada**, con paleta saturada, figuras exageradas y tono satírico, en lugar de ilustración conceptual apagada. La directriz de estilo vive en `social_config.json`.
- **Restricciones verificadas en código**, no solo sugeridas en el prompt:
  - Prohibido describir **texto, letras, números o tipografía** en la imagen, porque los modelos de difusión los renderizan como artefactos.
  - Permitido **caricaturizar a las figuras públicas nombradas** en el artículo (presidentes, senadores, alcaldes, ministros, líderes de partido), siempre con estilo ilustrado y rasgos exagerados. Prohibido el retrato fotorrealista y el *deepfake*. Prohibido mostrar de forma reconocible a víctimas, menores o personas privadas: se representan como figuras anónimas con el rostro girado o abstraído.
  - Obligatorio nombrar una **paleta de color** en cada prompt: un prompt sin señales cromáticas se rechaza, porque devuelve ilustraciones planas y sin contraste.
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

## 7. Interfaz de Línea de Comandos (CLI)

### 7.1. Objetivo

El motor se opera desde un CLI por subcomandos que reduce la ejecución de cada flujo a un solo comando y encadena los tres pasos del proceso editorial cuando se quiere de punta a punta. Los modos clásicos por banderas se conservan para los scripts y cron ya desplegados.

### 7.2. Subcomandos

| Comando | Responsabilidad | Entradas | Artefactos |
|---------|-----------------|----------|------------|
| `report` | Genera la pauta editorial semanal | `--feeds`, `--output`, `--debug` | `reportes/pauta_semanal_AAAA_MM_DD.md` y su companion JSON |
| `article` | Escribe una nota desde una propuesta | `--pauta`, `-n/--number`, `--output` | `articulos/articulo_N_slug.md` |
| `social` | Repurposing para redes sociales | `--article`, `--output`, `--platforms`, `--social-config`, `--skip-banners`, `--skip-prompts` | `social/AAAA_MM_DD_slug/` con copys, prompts, Markdown y banners |
| `print` | Tríptico impreso de la semana | `--pauta`, `--output`, `--triptych-config` | `impresos/AAAA_MM_DD_pauta-semanal/` con el tríptico en JSON, el Markdown panel por panel y el manifiesto |
| `all` | Secuencia completa | `--feeds`, `--base`, `-n/--number`, opciones sociales, `--triptych-config` y `--debug` | Los cuatro anteriores |
| `clean` | Limpieza de artefactos antiguos | `--base`, `--target`, `--days`, `--dry-run`, `--yes` | Elimina archivos y bundles |

Todos los comandos aceptan `--verbose`.

### 7.3. Comando secuencial `all`

Ejecuta, en orden y dentro de una misma invocación: la generación de la pauta, la escritura de la nota elegida, el bundle de redes sociales y el tríptico impreso. La pauta y el artículo recién generados se pasan como entrada al paso siguiente, sin intervención manual. El tríptico se arma desde la pauta del primer paso, así que no depende de la nota elegida. Si un paso falla, la ejecución se detiene con su código de error y no se ejecutan los pasos posteriores.

### 7.4. Entradas implícitas y directorio de salida

- **Pauta:** si `article` no recibe `--pauta`, toma la más reciente de `reportes/`. El orden lo da el nombre, que incluye la fecha (`AAAA_MM_DD`).
- **Artículo:** si `social` no recibe `--article`, toma el de fecha de modificación más reciente de `articulos/`, porque las notas no llevan fecha en el nombre.
- **Propuesta:** si `article` o `all` no reciben `-n/--number`, muestran los cinco titulares y preguntan cuál desarrollar. Sin terminal interactiva (por ejemplo en un cron) la ejecución falla con código 2 y un mensaje que pide `--number`, en lugar de quedar esperando una respuesta que nunca llegará.
- **Pauta del tríptico:** si `print` no recibe `--pauta`, toma la más reciente de `reportes/`. El tríptico no pide número de propuesta: cubre las cinco, así que `-n` no aplica.
- **Directorio de salida:** si no se indica `--output`, cada flujo usa su carpeta por defecto (`reportes/`, `articulos/`, `social/` o `impresos/`) y la crea si no existe. Una ruta que apunte al directorio actual se rechaza con error de uso, en los subcomandos y también en los modos clásicos.
- **Sin argumentos:** `python -m news_agent` no ejecuta ningún flujo. Muestra la ayuda y sale con código 2, porque el modo clásico por defecto consumiría tokens de la API y escribiría en el directorio actual sin que el usuario lo haya pedido. Los cron deben indicar el flujo y la salida explícitamente.

### 7.5. Limpieza de artefactos (`clean`)

- **Alcance:** solo los artefactos propios de la herramienta, declarados como patrones en `news_agent/cleanup.py`: pautas y companion JSON de `reportes/`, notas de `articulos/` y bundles de `social/`.
- **Fuera de alcance:** los bundles de `impresos/` todavía no son un objetivo de `clean`. Se limpian a mano hasta que se agregue su patrón.
- **Nunca se elimina** la caché de contenido (`cache/`) ni los recursos de la marca (`assets/`): ninguna entrada fuera de los patrones declarados se considera, aunque sea antigua.
- **Fecha de referencia:** la fecha codificada en el nombre cuando existe (pautas y bundles) y, cuando no (las notas), la fecha de modificación. La fecha del nombre es la fuente fiable: al clonar o copiar el repositorio, todos los archivos quedan con la fecha de la copia.
- **Umbral:** `--days N` (por defecto `DEFAULT_CLEAN_MAX_AGE_DAYS`, 30). Se elimina lo que supere ese corte; un valor menor que 1 es un error de uso.
- **Confirmación:** el comando lista lo que va a eliminar, con antigüedad y tamaño, y pide confirmación. `--dry-run` muestra el listado sin borrar nada y `--yes` omite la confirmación para automatizar.
- **Aislamiento de fallos:** si un artefacto no se puede eliminar, se registra en el log, el resto del lote continúa y el resumen final informa cuántos fallaron.

### 7.6. Estructura

| Módulo | Responsabilidad |
|--------|-----------------|
| `__main__.py` | Punto de entrada: distingue los subcomandos de los modos clásicos por banderas |
| `cli.py` | Parser de subcomandos, localización de entradas recientes, selección interactiva y handlers |
| `cleanup.py` | Detección y borrado de artefactos antiguos |
| `config.py` | Directorios de salida por defecto (`reportes/`, `articulos/`, `social/`, `impresos/`) y umbral de limpieza |

> **¿Por qué el subcomando se reconoce solo en la primera posición?** Los modos clásicos siempre empiezan con una bandera, así que exigir que el nombre del comando vaya primero evita que un valor que coincida con un comando (por ejemplo `--output social`) se interprete como una invocación del subcomando `social`.

### 7.7. Códigos de salida

| Código | Significado |
|:------:|-------------|
| `0` | Ejecución exitosa (o nada que procesar, sin invocar a la API) |
| `1` | Error de ejecución: configuración, API, pauta imposible de parsear, artefacto de entrada inexistente |
| `2` | Error de uso: comando desconocido, opción inválida, plataforma desconocida, falta `--number` sin terminal o `--days` no positivo |
| `130` | Interrupción con Ctrl+C |

## 8. Subsistema de Tríptico Impreso

### 8.1. Objetivo

Transformar la pauta semanal completa en una **hoja oficio doblada en tres** —seis paneles, doble faz— con cinco mini-notas en lenguaje simple, una por propuesta, más un panel de portada. A diferencia del subsistema de RRSS, que parte de un artículo ya publicado, el tríptico parte de la **pauta**: es la pieza que se reparte en la calle y la lee alguien que no sigue el noticiero ni lee el diario.

```
python -m news_agent print
python -m news_agent print --pauta reportes/pauta_semanal_2026_09_24.md
```

El subsistema entrega **texto**: el tríptico en JSON, el mismo contenido en Markdown —panel por panel— y un manifiesto con las mediciones y lo que quedó pendiente. No maqueta ni genera PDF ni ilustraciones: el armado final lo hace el equipo de diseño.

### 8.2. Restricción de largo

El cuerpo del tríptico tiene un tope físico: **una columna y media** de una hoja oficio en tipografía monospace de 12 pt. Ese tope se traduce a caracteres, porque el tríptico se mide, no se estima a ojo:

| Medida | Valor |
|--------|-------|
| Hoja | oficio, 215,9 × 330,2 mm, con margen de 15 mm |
| Ancho útil por columna | 61,97 mm |
| Avance de un carácter monospace de 12 pt | 2,5506 mm |
| Caracteres por línea | **24** en una columna · **36** en columna y media |
| Líneas por columna | **59** |
| Techo de una columna | 1.416 caracteres |
| Techo del bloque de una nota | **2.124 caracteres** |
| Objetivo de redacción del cuerpo | 700 caracteres |

Todos esos números se derivan de la configuración en `news_agent/triptych/specs.py`, y el prompt que recibe el modelo usa los mismos valores: lo que se le pide y lo que después se mide no pueden separarse.

El bloque de una nota es el título más el cuerpo, los datos clave, el «por qué te importa» y las fuentes. El tope aplica a ese bloque completo, no solo al cuerpo.

### 8.3. Entrada

El único origen es una **pauta semanal** (`reportes/pauta_semanal_AAAA_MM_DD.md`) y su companion JSON:

- De cada propuesta se toman el título, el enfoque editorial, los puntos clave y las fuentes sugeridas, reutilizando `article_writer.parse_pauta_file`.
- Del companion se toma el contenido de las noticias que respaldan cada propuesta, reutilizando `source_references.load_companion_data`, con el contenido recortado a `SOURCE_ARTICLE_MAX_CHARS`.
- **Companion ausente o corrupto:** el flujo continúa con el enfoque y los puntos de la pauta, y lo registra en el log. No es un error.
- **Pauta ilegible o sin material usable:** error explícito y salida con código 1, antes de invocar a la API.

### 8.4. Contrato de la respuesta

Como el subsistema de RRSS, pide al modelo un **objeto JSON** en lugar de Markdown, con la extracción defensiva de `social/json_utils.py` y reintentos con nota de corrección hasta agotar `TRIPTYCH_JSON_MAX_RETRIES`. El contrato es:

| Campo | Contenido |
|-------|-----------|
| `cover.hook` | Gancho de portada, en una línea |
| `cover.title` | Título de la edición semanal |
| `notes[]` | Exactamente una nota por propuesta, en orden |
| `notes[].proposal_number` | Número de la propuesta de la pauta |
| `notes[].title` | Título en lenguaje llano |
| `notes[].body` | Qué pasó, en dos o tres párrafos cortos |
| `notes[].key_data` | Los datos que lo prueban: tres elementos |
| `notes[].why_it_matters` | Por qué le importa a quien lee |

El panel 1 queda reservado para la portada; las cinco notas ocupan los paneles 2 a 6. Las fuentes de cada nota no las escribe el modelo: se toman de las fuentes sugeridas de su propia propuesta.

### 8.5. Reglas de lenguaje simple

Las cuatro reglas duras del tono se declaran en el system prompt y se verifican después en código:

| Regla | Verificación |
|-------|--------------|
| Frases de 15 palabras o menos | Se cuenta cada oración y se advierte las que se pasan |
| Ninguna sigla sin explicar | Se detectan las mayúsculas sostenidas y se contrastan con `style.acronym_allowlist` |
| Trato directo al lector | Directriz de redacción |
| Estructura fija: qué pasó → por qué te importa → los datos que lo prueban | Se verifica que los tres bloques existan y que `key_data` tenga tres elementos |

### 8.6. Política de errores: fatal contra advertencia

| Situación | Respuesta |
|-----------|-----------|
| JSON imposible de extraer | Reintento con nota de corrección; agotados los intentos, error |
| Cantidad de notas distinta de la cantidad de propuestas | Error: no se escribe nada |
| Nota sin título o sin cuerpo | Error: no se escribe nada |
| Cuerpo por debajo de `TRIPTYCH_NOTE_MIN_CHARS` | Error: la respuesta no es una nota publicable |
| Bloque que supera una columna y media | **Advertencia.** Nunca se recorta: el texto se escribe completo y el aviso viaja al Markdown y al manifiesto |
| Oración larga, sigla sin explicar o término a evitar | **Advertencia**, con el texto culpable citado |
| Cantidad de datos clave distinta de tres | **Advertencia** |

La distinción es deliberada: un recorte automático mutila la redacción, y el ajuste final de una pieza impresa lo hace una persona. Por eso el desborde se mide, se informa y se deja intacto.

### 8.7. Formato de salida (bundle)

Cada ejecución escribe una carpeta autocontenida `impresos/AAAA_MM_DD_pauta-semanal/`, cuya fecha es la de la **pauta**, no la de ejecución: así la carpeta corresponde a la edición que se imprime aunque el tríptico se genere días después.

| Archivo | Contenido |
|---------|-----------|
| `triptych.json` | Portada y las cinco notas con su medición y sus advertencias |
| `triptych.md` | El tríptico panel por panel, listo para leer o pegar en la plantilla de diseño |
| `manifest.json` | Pauta de origen, formato derivado, presupuesto de caracteres, medición por nota y totales de advertencias |

El Markdown encabeza con la edición, el formato, el pliegue y el tope por nota; sigue con la portada, un panel por nota, y cierra con el bloque de advertencias pendientes, que solo aparece si hay algo que ajustar. Incluye una nota de armado con el orden lógico de los paneles y la advertencia de que la imposición definitiva en la hoja se confirma con la imprenta según el tipo de pliegue.

### 8.8. Configuración externa

La geometría, la tipografía y las reglas de estilo viven en `triptych_config.json`, versionado en la raíz del proyecto y validado al cargarse con `load_triptych_config`, siguiendo el mismo criterio que `social_config.json`:

| Sección | Contenido | Obligatoria |
|---------|-----------|:-----------:|
| `page` | Medidas de la hoja, margen, columnas por cara, caras y tipo de pliegue | ✅ |
| `typography` | Familia, cuerpo en puntos, avance de carácter e interlínea | ✅ |
| `limits` | Tope en columnas del bloque y objetivo de caracteres del cuerpo | ✅ |
| `style` | Máximo de palabras por oración, siglas permitidas y términos a evitar | ✅ |
| `layout` | Cantidad de notas y de datos clave por nota | ✅ |
| `brand` | Nombre, handle, sitio y logo | ❌ |

Una medida negativa, un margen que se coma la hoja, un pliegue desconocido o una lista de siglas declarada como texto se detectan al cargar, con un mensaje que nombra el campo culpable. Cambiar la medida del papel o el cuerpo de la tipografía no requiere tocar código: el presupuesto de caracteres se recalcula solo.

### 8.9. Estructura del subsistema

| Módulo (`news_agent/triptych/`) | Responsabilidad |
|---------------------------------|-----------------|
| `orchestrator.py` | Coordina el flujo completo y devuelve el resumen del bundle |
| `pauta_source.py` | Carga las propuestas de la pauta y su companion como material de origen |
| `specs.py` | Deriva el presupuesto de caracteres de la geometría y la tipografía |
| `text_utils.py` | Verifica las reglas de lenguaje simple (oraciones, siglas, términos) |
| `prompt_builder.py` | Construye los prompts con el presupuesto y el esquema derivados de la configuración |
| `generator.py` | Genera, valida y mide el tríptico; separa lo fatal de lo advertible |
| `models.py` | Dataclasses de los artefactos del subsistema |
| `writer.py` | Escribe el bundle y su manifiesto, y redacta el Markdown por panel |

Reutiliza `article_writer.parse_pauta_file`, `source_references.load_companion_data`, `social.json_utils.extract_json_object` y `config.load_triptych_config`. No depende de Pillow: el tríptico se entrega como texto.
