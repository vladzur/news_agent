# 📋 Especificaciones de Funcionamiento: Agente Inteligente de Contenidos

**Proyecto:** Curador de Pauta Editorial Automatizado

**Medio:** La Chispa Sur

**Versión del Motor:** 1.0.0 (Python + DeepSeek API)

## 1. Objetivo General

Automatizar la recopilación, filtrado y análisis de la agenda noticiosa nacional e internacional mediante la lectura de canales RSS seleccionados, utilizando el modelo de lenguaje **DeepSeek-Flash** para sintetizar y proponer **cinco (5) líneas editoriales semanales —tres (3) de foco nacional y dos (2) de foco internacional—** de alto impacto, profundidad analítica y narrativa ágil.

## 2. Arquitectura y Componentes del Sistema

### 2.1. Capa de Ingesta (Data Ingestion)

- **Mecanismo:** Extracción de datos sin intermediarios mediante dos vías:
  - `feedparser` para canales RSS/Atom.
  - `requests` + `BeautifulSoup` para medios sin feed, con `"method": "scraping"` y selectores CSS configurables (`selectors.article`, `selectors.title` y, opcionalmente, `summary`, `date`, `link_prefix` y `request_headers`).
  
- **Fuentes de Entrada:** Matriz de canales gestionada en un diccionario/configuración JSON independiente del código principal (`rss_feeds.json`).

- **Tolerancia a fallos:** Si un feed o un scraping falla, se registra el error y se continúa con el siguiente medio sin abortar la ejecución.
  
- **Frecuencia de Ejecución:** El agente operará bajo demanda o mediante una tarea programada (`cronjob`) de manera semanal (recomendado: domingos a las 23:00 hrs o lunes a las 07:00 hrs).
  

### 2.2. Capa de Filtrado y Ventana de Tiempo

- **Ventana Operativa:** El agente sólo procesará noticias cuya etiqueta de publicación (`published_parsed`) se encuentre dentro de las **últimas 96 horas (4 días)** respecto a la ejecución del script. Se usa `published_parsed`; una entrada sin esa fecha se descarta. La ventana es configurable con `TIME_WINDOW_HOURS`.
  
- **Truncamiento de Datos:** Para optimizar la ventana de contexto y evitar ruido, cada noticia se limitará a:
  
  - Título completo.
    
  - Nombre del medio emisor.
    
  - Resumen o descripción truncado a un máximo de **500 caracteres** (limpiando cualquier etiqueta HTML residual). Si el enriquecimiento con `trafilatura` logró extraer el texto completo, se usa ese texto como resumen de entrada y también se trunca a 500 caracteres. El límite es configurable con `SUMMARY_MAX_CHARS`.
    

### 2.3. Capa de Inteligencia (Cerebro IA)

- **Proveedor:** DeepSeek API.
  
- **Modelo Especificado:** `deepseek-flash` (o endpoint compatible vía OpenAI SDK).
  
- **Hiperparámetros de Control:**
  
  - `temperature`: **0.1** (baja temperatura para privilegiar la precisión factual y minimizar alucinaciones).

  - `base_url`: `https://api.deepseek.com/v1`.

  - `PAUTA_MAX_TOKENS`: **65536** para la pauta semanal (presupuesto compartido entre razonamiento y contenido).

  - `ARTICLE_MAX_TOKENS`: **16384** para la escritura de artículos.
    
  - Razonamiento: `PAUTA_REASONING_EFFORT="high"` y `ARTICLE_REASONING_EFFORT="high"`. El modo thinking se activa por llamada; el reintento sin razonamiento usa `CONTENT_RETRY_MAX_TOKENS=8192` como piso.

  - La configuración canónica vive en `news_agent/config.py`; esta tabla resume sus valores por defecto.
    

## 3. Directrices Editoriales Obligatorias (System Prompt)

El agente debe ceñirse estrictamente al perfil de identidad de *La Chispa Sur*:

- **Tono:** Incisivo, analítico, audaz y de lectura ágil. No debe limitarse a replicar titulares del *mainstream*; su valor radica en **conectar puntos ocultos entre noticias que comparten un mismo eje**, encontrar contradicciones o proponer enfoques de fondo (ensayo, reportaje o columnas de opinión), sin forzar cruces entre hechos sin relación directa.
  
- **Restricción de Volumen:** El agente debe entregar **exactamente cinco (5) propuestas** por informe: **tres (3) de ámbito nacional** y **dos (2) de ámbito internacional**, estas últimas con énfasis en hechos que conmocionan al mundo, pueblos oprimidos y políticas imperialistas que afectan la estabilidad mundial. Ni más, ni menos.

- **Excepción por temas prioritarios (`MAIN_TOPICS`):** cuando la variable de entorno `MAIN_TOPICS` está definida con un array JSON de temas, esos temas tienen prioridad sobre la distribución geográfica 3/2. La cantidad total sigue siendo cinco, pero la proporción entre propuestas nacionales e internacionales puede ajustarse para cubrirlos. Si no hay material suficiente para un tema prioritario, se marca «Requiere investigación adicional» en lugar de inventar contenido.

- **Criterio de foco sin `MAIN_TOPICS`:** cuando la variable no está definida o está vacía, cada propuesta debe girar en torno a un solo eje temático, territorial, institucional o de conflicto, y solo puede relacionar hechos con conexión directa y verificable (misma política, actor, territorio, institución o causa estructural). Se prohíbe agrupar noticias de coyunturas distintas para forzar un cruce. En este modo se priorizan los ejes de la línea editorial de La Chispa Sur: derechos sociales, laborales y territoriales; crítica al neoliberalismo y al extractivismo; pueblos originarios y conflictos territoriales; derechos humanos y memoria; medio ambiente; salud, educación y vivienda; foco en Villarrica y La Araucanía; y, en lo internacional, pueblos oprimidos y políticas imperialistas.

- **Foco único en la redacción de notas:** el artículo completo desarrolla exclusivamente el eje de la propuesta aprobada. No incorpora material de origen de otros temas ni fuerza conexiones para unirlo; si el material disponible no respalda el eje, lo descarta.
  

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
*   **Fuentes Sugeridas para Ampliar:**
    *   [Nombre del medio o recurso]: [Qué aporta esta fuente]

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
  
- **Ausencia de Datos:** En caso de que la recolección sume 0 noticias en la ventana de 96 horas, el agente detendrá el flujo antes de invocar la API de DeepSeek, generando un log de advertencia para evitar consumo innecesario de tokens.
  
- **Fallo de API Key:** El script validará la existencia de la variable de entorno `DEEPSEEK_API_KEY` antes de iniciar. Si no se encuentra, arrojará un error explícito de configuración.

- **Respuesta sin contenido visible:** Como `max_tokens` es un presupuesto compartido entre el razonamiento interno y el texto final, un razonamiento extenso puede agotarlo y dejar `content` vacío. En ese caso el cliente **reintenta la llamada con el razonamiento desactivado y un presupuesto ampliado**; si el reintento tampoco devuelve contenido, la ejecución falla de forma explícita. El razonamiento interno nunca se escribe en un archivo de salida, porque no es texto publicable.

- **Respuesta que no es un artículo:** Antes de escribir el archivo, se verifica que la respuesta traiga titular de nivel 1 y al menos un subtítulo de sección. Si no los trae, se descarta y se aborta sin crear archivo, para no publicar contenido inválido.

- **Editor de portada:** Tras la redacción se hace una segunda llamada con rol de editor de portada. Devuelve, en JSON, **tres propuestas de titular y bajada** con enfoques fijos (denuncia/tesis política, narrativo/humano y analítico/geopolítico). Los largos se validan en código —12 a 16 palabras el titular, 25 a 45 la bajada—; si no se cumplen se reintenta una vez con una nota de corrección y, si el segundo intento tampoco cumple, se recorta por código y se advierte en el log. La primera propuesta se aplica al artículo y las tres se anexan en un apéndice `## 📰 Propuestas de portada`. El apéndice está marcado como no publicable: el parser de RRSS corta el cuerpo antes de esa marca, de modo que no contamina los prompts de redes sociales. Si la segunda llamada falla, el artículo se guarda igual con el titular del redactor y sin apéndice.

## 6. Subsistema de Repurposing para Redes Sociales (RRSS)

### 6.1. Objetivo

Transformar un artículo ya publicado en piezas multiplataforma para **X/Twitter, Facebook e Instagram**, mediante un flujo local que se ejecuta desde el mismo punto de entrada CLI del agente:

```
python -m news_agent social --platforms x,instagram
python -m news_agent --socialize articulos/articulo_1_slug.md --output ./social
```

El subsistema produce cuatro familias de artefactos: **copys estructurados**, **prompts visuales en inglés**, **banners renderizados localmente** y el **carrusel vertical de Instagram**. No publica nada en las plataformas ni genera las imágenes finales del prompt visual: entrega al equipo editorial el material listo para publicar y para pegar en un generador de imágenes.

### 6.2. Entrada

El único origen admitido es un **artículo Markdown ya publicado** (`articulos/articulo_N_slug.md`), con la estructura que produce el agente: titular de nivel 1, firma, separador horizontal, lead, secciones de nivel 2 y bloque final de fuentes.

- **Formato inválido:** un archivo sin titular de nivel 1 se rechaza con un error explícito de parseo.
- **Guardia de material:** si el cuerpo del artículo tiene menos de `SOCIAL_MIN_ARTICLE_WORDS` (150) palabras, el flujo se detiene **antes** de invocar la API para evitar consumo innecesario de tokens.
- **Material extraído:** titular, firma, lead, secciones, fuentes citadas, cifras detectadas por patrón y oraciones candidatas a cita, ordenadas por potencial editorial. Todo lo que se genere después se valida contra este material.

### 6.3. Capa de generación de copys

- **Salida JSON, no Markdown.** A diferencia de la pauta y de los artículos, el subsistema pide al modelo un objeto JSON estructurado con el contrato completo de la pieza.
- **Extracción defensiva.** La respuesta se parsea tolerando bloques de código Markdown, texto explicativo alrededor y comas finales sueltas. Si no se obtiene un objeto válido, se reintenta la llamada con una nota de corrección, hasta `SOCIAL_JSON_MAX_RETRIES` veces.
- **Campos del contrato:** `hooks`, `summary`, `hook`, `quote_card`, `key_figures`, `cta`, `alt_text`, `x`, `facebook`, `instagram` (con `caption`, `hashtags` y `slides`).

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
| Slides del carrusel de Instagram | Se exigen exactamente 3; cada slide tiene solo `text` (≤ 240 caracteres) y un `figure` opcional (≤ 40). No hay titular. Las cifras se verifican contra el artículo. Si faltan slides, se completan con la síntesis ejecutiva y material del artículo. |
| Coherencia de los slides | Se descartan textos duplicados, se conserva el orden y se usa la misma retícula, el mismo tamaño de lectura y los mismos topes en los tres slides. |

### 6.4. Capa del prompt visual

- **Un único prompt por columna, en inglés y listo para Midjourney.** El subsistema no genera imágenes ni entrega prompts por relación de aspecto: produce un comando completo con la proporción declarada en `social_config.json` (por defecto `--ar 16:9`) y los flags de versión.
- **El tratamiento se decide por columna con precedencia explícita y queda declarado en la salida:**
  - `representative` — **prioridad**. Se usa cuando la columna gira en torno a figuras públicas políticas nombradas: jefes de Estado, ministros, legisladores, candidatos, autoridades o dirigentes de partido. El prompt debe mostrar a esas figuras con un **parecido reconocible** dentro de una composición editorial construida —collage de papel recortado, serigrafía con semitono, afiche pintado o risografía—, con color plano posterizado, contornos de tinta y textura de papel. La composición no puede confundirse con una fotografía real ni con una recreación de prensa.
  - `photorealistic` — **camino por defecto sin figuras públicas**. Se usa cuando no hay figuras públicas políticas centrales y la columna reporta hechos, lugares, objetos o escenas concretas que pueden mostrarse como una fotografía documental plausible.
  - `caricature` — **excepción**. Se usa solo cuando la columna es abstracta, no nombra figuras públicas políticas y no tiene una escena documentable: un argumento, una tendencia económica o institucional, una metáfora o una crítica. La caricatura no puede ser una forma de eludir un hecho fotografiable.
  - El modelo declara en `political_figures` las figuras públicas políticas que la imagen muestra, copiadas del artículo. La lista es obligatoria y puede quedar vacía. Si no está vacía, el tratamiento debe ser `representative` y cada figura debe aparecer nombrada en el prompt positivo. El modelo explica en `rationale`, en español, qué hechos concretos sostienen el tratamiento y qué figuras obligan la composición representativa. Un rationale vacío invalida la respuesta.
- **Fuerza de representación verificada en código:** el prompt debe nombrar anclas concretas del artículo —nombres propios, acrónimos, instituciones, lugares, objetos y cifras—. Se exigen dos anclas distintas en `photorealistic` y `representative`, y una en `caricature`; si el artículo no produce anclas utilizables, la comprobación se omite con una advertencia en el log. Las anclas detectadas se enumeran en el user prompt para que el modelo conserve los nombres propios en su grafía original en español.
- **Coherencia verificada en código**, no solo sugerida en el prompt:
  - `photorealistic` exige un recurso fotográfico (lente, luz natural, reportaje o grano de película), rechaza las señales de ilustración y rechaza los tropos abstractos (`abstract composition`, `purely symbolic`, `surreal`, `dreamlike`, `floating symbols`, `visual metaphor`, entre otros).
  - `representative` exige una técnica de composición editorial (collage, semitono, serigrafía, afiche o risografía) y rechaza el lenguaje fotográfico y de realismo (`photograph`, `documentary`, `35mm`, `lens`, `photorealistic`, `paparazzi`, `film still`, entre otros). También rechaza las frases que ocultan el rostro de la figura.
  - `caricature` exige una técnica de ilustración y no puede declarar lenguaje fotográfico.
  - Las figuras declaradas se verifican contra el titular, el lead, los subtítulos y el cuerpo del artículo. Una figura inventada, ausente o que solo figure en las fuentes o en el apéndice de portada invalida la respuesta. Si el artículo menciona un cargo sin nombrar a la persona, no se inventa un rostro.
- **Negativos por tratamiento:** `treatment_negatives.representative` agrega al `--no` los términos que impiden derivar hacia una foto realista —realismo fotográfico, foto de prensa, paparazzi, piel realista—. El negativo final se compone en este orden: negativo de marca → negativo del tratamiento → `extra_negative`, sin duplicar términos. Un `extra_negative` que prohíba figuras públicas se rechaza siempre; en `representative` también se rechaza el que esconda su rostro o su parecido.
- **Textos breves dentro de la escena**: rótulos de tres o cuatro palabras en español, integrados como letreros, pancartas, carteles, pantallas o precios, **en mayúsculas y sin comillas** (`PENSIONES`, `-10,39%`). El material de origen entrega las cifras de la columna para que el modelo las use cuando aporten.
- **Restricciones verificadas en código**:
  - Se rechazan los **bloques de texto**: párrafos, letra pequeña y titulares largos, porque los modelos de difusión los renderizan como ruido. Los rótulos breves y las cifras no se marcan como infracción.
  - Obligatorio nombrar una **paleta de color**: un prompt sin señales cromáticas se rechaza, porque devuelve imágenes planas y sin contraste.
  - Se rechaza la **violencia explícita** (`blood`, `gore`, `corpse`, `massacre`, entre otros) y las **escenas fabricadas o suplantaciones de identidad** (`deepfake`, `face swap`, `staged reenactment`, `fabricated scene`).
  - Los rótulos dentro de la imagen —en mayúsculas o entre comillas— quedan excluidos de la heurística que detecta prompts escritos en español. Antes de aplicar esa heurística también se retiran las anclas del artículo y los artículos que las preceden (`La Moneda`, `La Araucanía`, `Los Lagos`), de modo que un prompt en inglés puede nombrar lugares y personas en español sin ser rechazado. Además, el código retira las comillas y las barras invertidas del prompt: Midjourney recibe texto plano, no JSON.
  - Prompt positivo entre 25 y 200 palabras, en inglés.
- **Reglas editoriales del prompt**, no verificables de forma determinista:
  - La imagen debe representar el contenido real de la columna. Una escena genérica o abstracta que podría ilustrar cualquier artículo es un fallo, aunque cumpla las demás reglas.
  - Las figuras públicas políticas nombradas no se omiten, recortan, ocultan ni sustituyen por siluetas o personas anónimas. Se muestran con su parecido reconocible y dentro de una composición que se lea de inmediato como una ilustración editorial.
  - Las víctimas, menores y personas privadas se representan de forma no identificable.
  - En el tratamiento fotorrealista no se inventa un evento que la columna no reporte; la escena debe ser plausible y fiel a sus hechos.
- **Salida:** tratamiento, figuras públicas, justificación en español, prompt positivo, prompt negativo (el de marca más el del tratamiento y los agregados específicos de la columna, sin duplicar términos) y comando completo de Midjourney (`--ar`, flag de estilo, `--v` y `--no`).
- **Dos archivos por bundle:** `visual_prompt.txt` contiene únicamente el comando en texto plano —sin JSON, sin comillas escapadas— para pegarlo en Midjourney; `visual_prompts.json` conserva los metadatos (tratamiento, figuras públicas, justificación, prompt, negativo y proporción).

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

#### 6.5.1. Carrusel vertical de Instagram

Cuando la plataforma `instagram` está habilitada, el subsistema suma un carrusel de **cinco piezas verticales de 1080×1440 (4:3 vertical)**, todas con la misma retícula y la misma identidad visual del banner:

| Orden | Pieza | Contenido |
|:-----:|-------|-----------|
| 1 | Portada | Barra de acento, etiqueta de marca, logo, titular, bajada, llamado a deslizar y contador `01 / 05` |
| 2–4 | Tres slides de resumen | Número de punto discreto, idea principal en tipografía grande, tarjeta opcional de dato duro, puntos de progreso y contador. Sin titular. |
| 5 | Firma | Logo centrado, nombre de la marca, tagline, sitio, handle y llamado a leer la nota completa |

- **Estética compartida:** las cinco piezas reutilizan la paleta, las fuentes, el logo, la barra de acento y el pie de marca de `banner_renderer.py`. El encabezado y el pie están en la misma coordenada en todas, y los tres resúmenes usan el mismo bloque de texto y el mismo tamaño de lectura.
- **Formato obligatorio:** `instagram_carousel.format` debe apuntar a un `instagram_*` declarado en `banners.sizes` y con alto mayor que ancho. El formato del repositorio es `instagram_portrait`, de 1080×1440, para que la pieza sea 4:3 vertical y no el 9:16 de un reel. Cualquier otra combinación se rechaza al cargar la configuración y, si se construye el renderizador directamente, lanza `InstagramRenderError`.
- **Contenido de los resúmenes:** sale de `instagram.slides` del contrato de copys. Cada slide trae `text` y `figure`; no existe un titular separado. La portada y la firma se componen siempre con datos de la marca, no con texto del modelo.
- **Tolerancia a fallos:** un slide que falla no interrumpe los otros cuatro; queda con `path: null` en el manifiesto.
- **Salida:** los cinco PNG se escriben juntos en el subdirectorio exclusivo `instagram/` del bundle.

### 6.6. Formato de salida (bundle)

Cada ejecución escribe una carpeta autocontenida `social/AAAA_MM_DD_slug-del-titulo/` con los copys en JSON, el comando de Midjourney en `visual_prompt.txt`, los metadatos del prompt en `visual_prompts.json` (tratamiento, figuras públicas, justificación, prompt y negativo), un Markdown listo para copiar y pegar por plataforma, los PNG de los banners en `assets/`, el carrusel vertical 4:3 (1080×1440) en el subdirectorio exclusivo `instagram/` (`01_cover.png`, `02_point_1.png`, `03_point_2.png`, `04_point_3.png` y `05_signature.png`) y un `manifest.json` que registra qué se generó, qué falló y con qué artículo se produjo. El bloque `visual_prompts` del manifiesto incluye `status` (`generated`, `skipped` o `failed`), `error` cuando la generación falló y `political_figures` con las figuras representadas, de modo que omitir el prompt con `--skip-prompts` no se confunde con un fallo. El bloque `instagram_carousel` registra `status` (`generated`, `partial`, `failed` o `skipped`), formato, dimensiones, cantidad de slides y la ruta de cada pieza.

El campo `quote_card.verbatim` del JSON de copys —repetido como `verified_quote` en el manifiesto— indica si la cita destacada se verificó palabra por palabra contra el artículo de origen.

### 6.7. Configuración externa

La identidad visual y los límites viven en `social_config.json`, versionado en la raíz del proyecto y validado al cargarse, siguiendo el mismo criterio que `rss_feeds.json` para las fuentes:

| Sección | Contenido | Obligatoria |
|---------|-----------|:-----------:|
| `brand` | Nombre, handle, sitio, logo opcional, paleta de colores y tipografías por rol | ✅ |
| `platforms` | Límite de caracteres, largo del hilo y tope de hashtags por plataforma. Sobrescriben los valores por defecto de `config.py` y se validan al cargar | ❌ |
| `banners.templates` / `banners.sizes` | Matriz plantilla → formatos y tamaño de cada formato | ✅ |
| `banners.safe_zone` | Bandas no utilizables de los formatos verticales, incluido `instagram_portrait` | ❌ |
| `instagram_carousel` | Formato del carrusel vertical; debe ser un `instagram_*` vertical declarado en `banners.sizes`. Por defecto, `instagram_portrait` (1080×1440) | ❌ |
| `visual_prompts` | Los tres tratamientos, las reglas de decisión, el prompt negativo de marca, los negativos por tratamiento, la proporción única y el sufijo de Midjourney. Se validan al cargar | ✅ |

Un color mal escrito, una clave de color faltante, un tamaño inválido, una sección `visual_prompts` incompleta o con un tratamiento o un negativo por tratamiento inválido, una plataforma con límites inválidos, una plantilla que apunte a un formato inexistente, o un carrusel que apunte a un formato no vertical o de otra plataforma se detectan al cargar el archivo, con un mensaje que indica el campo culpable.

### 6.8. Estructura del subsistema

| Módulo (`news_agent/social/`) | Responsabilidad |
|-------------------------------|-----------------|
| `orchestrator.py` | Coordina el flujo completo y devuelve el resumen del bundle |
| `article_source.py` | Parsea el artículo de origen, extrae su material reutilizable y calcula las anclas concretas del prompt visual |
| `prompt_builder.py` | Construye los prompts de copys (español) y del prompt visual (inglés) |
| `copy_generator.py` | Genera y valida los copys contra los límites de cada plataforma |
| `visual_prompts.py` | Genera y valida el prompt visual en inglés con sus tres tratamientos, figuras públicas y anclas |
| `banner_renderer.py` | Renderiza los banners con Pillow y expone las primitivas de retícula compartidas |
| `instagram_renderer.py` | Renderiza el carrusel vertical: portada, tres resúmenes y firma |
| `platform_specs.py` | Resuelve los límites por plataforma y filtra por formato |
| `text_utils.py` | Recorte por caracteres y normalización de hashtags |
| `json_utils.py` | Extracción defensiva de JSON de las respuestas del modelo |
| `models.py` | Dataclasses de los artefactos del subsistema |
| `writer.py` | Escribe el bundle de salida y su manifiesto |

### 6.9. Manejo de errores y robustez

- **JSON inválido o incompleto** → reintento con nota de corrección, hasta agotar `SOCIAL_JSON_MAX_RETRIES`.
- **Copys imposibles de validar** → se aborta sin escribir un bundle a medias.
- **Prompt visual fallido** → el bundle se escribe igualmente con los copys y los banners; el manifiesto lo registra con `status: "failed"` y el motivo en `error`.
- **Banner fallido** → se registra el error y el resto del lote continúa.
- **Slide del carrusel fallido** → se registra el error, el slide queda con ruta nula y los otros cuatro se escriben igualmente.
- **Formato de carrusel inválido** → se rechaza al cargar la configuración si no es un `instagram_*` vertical; si se construye el renderizador directamente, lanza `InstagramRenderError` y el bundle se escribe sin carrusel.
- **Directorio de salida inexistente** → se crea automáticamente (incluidos los directorios intermedios).
- **Artículo inexistente, vacío o sin titular** → error explícito de parseo y salida con código distinto de cero.
- **API key ausente** → error explícito de configuración antes de cualquier llamada.
- **Combinación de argumentos inválida** (`--socialize` junto a `--feeds`, `--debug`, `--write-article` o `--article`, o banderas del subsistema sin `--socialize`) → error de uso en `stderr` y salida con código 2.

## 7. Interfaz de Línea de Comandos (CLI)

### 7.1. Objetivo

El motor se opera desde un CLI por subcomandos que reduce la ejecución de cada flujo a un solo comando y encadena los cuatro pasos del proceso editorial cuando se quiere de punta a punta: pauta, una o todas las notas, redes sociales de cada nota y tríptico impreso. Los modos clásicos por banderas se conservan para los scripts y cron ya desplegados.

### 7.2. Subcomandos

| Comando | Responsabilidad | Entradas | Artefactos |
|---------|-----------------|----------|------------|
| `report` | Genera la pauta editorial semanal | `--feeds`, `--output`, `--debug` | `reportes/pauta_semanal_AAAA_MM_DD.md` y su companion JSON |
| `article` | Escribe una nota desde una propuesta | `--pauta`, `-n/--number`, `--output` | `articulos/articulo_N_slug.md` |
| `social` | Repurposing para redes sociales | `--article`, `--articles-dir`, `--all`, `--select`, `--output`, `--platforms`, `--social-config`, `--skip-banners`, `--skip-prompts` | `social/AAAA_MM_DD_slug/` con copys, prompts, Markdown y banners |
| `print` | Tríptico impreso de la semana | `--pauta`, `--output`, `--triptych-config` | `impresos/AAAA_MM_DD_pauta-semanal/` con el tríptico en JSON, el Markdown panel por panel y el manifiesto |
| `all` | Secuencia completa, con una nota o la edición entera | `--feeds`, `--base`, `-n/--number`, `--all-articles`, opciones sociales, `--triptych-config` y `--debug` | Los cuatro anteriores; con `--all-articles`, una nota y un bundle de RRSS por propuesta |
| `clean` | Limpieza de artefactos antiguos | `--base`, `--target`, `--days`, `--dry-run`, `--yes` | Elimina archivos y bundles |

Todos los comandos aceptan `--verbose`. En `clean` la bandera se acepta por uniformidad del parser, pero todavía no cambia el nivel de logging.

### 7.3. Comando secuencial `all`

Ejecuta, en orden y dentro de una misma invocación: la generación de la pauta, la escritura de una nota o de todas las propuestas, el bundle de redes sociales de cada nota y el tríptico impreso. La pauta y las notas recién generadas se pasan como entrada al paso siguiente, sin intervención manual.

- **Modo de una nota** (`--number N`): escribe esa propuesta, genera su bundle de RRSS y arma el tríptico. Un fallo en cualquiera de las etapas detiene la ejecución con su código de error.
- **Edición completa** (`--all-articles`): lee las propuestas reales de la pauta, escribe una nota por cada una y genera un bundle de RRSS por nota. Si una nota o un bundle social falla, se informa y se continúa con los demás; el tríptico se arma igualmente desde la pauta. Al final se muestra un resumen y se sale con código 1 si hubo incidencias. No pregunta por la terminal, así que es el modo recomendado para cron.
- El tríptico se arma desde la pauta del primer paso, así que no depende de las notas generadas.

### 7.4. Entradas implícitas y directorio de salida

- **Pauta:** si `article` no recibe `--pauta`, toma la más reciente de `reportes/`. El orden lo da el nombre, que incluye la fecha (`AAAA_MM_DD`).
- **Artículo:** si `social` no recibe `--article` ni usa `--all`/`--select`, toma el de fecha de modificación más reciente del directorio indicado por `--articles-dir` (`articulos/` por defecto), porque las notas no llevan fecha en el nombre.
- **Propuesta:** si `article` o `all` no reciben `-n/--number`, muestran los cinco titulares y preguntan cuál desarrollar. Sin terminal interactiva (por ejemplo en un cron) la ejecución falla con código 2 y un mensaje que pide `--number` o `--all-articles`, en lugar de quedar esperando una respuesta que nunca llegará. `all` valida el modo de edición y `--platforms` antes de generar la pauta. `--all-articles` es excluyente con `--number` y no requiere terminal.
- **Pauta del tríptico:** si `print` no recibe `--pauta`, toma la más reciente de `reportes/`. El tríptico no pide número de propuesta: cubre las cinco, así que `-n` no aplica.
- **Directorio de salida:** si no se indica `--output`, cada flujo usa su carpeta por defecto (`reportes/`, `articulos/`, `social/` o `impresos/`) y la crea si no existe. Una ruta que apunte al directorio actual se rechaza con error de uso, en los subcomandos y también en los modos clásicos.
- **Sin argumentos:** `python -m news_agent` no ejecuta ningún flujo. Muestra la ayuda y sale con código 2, porque el modo clásico por defecto consumiría tokens de la API y escribiría en el directorio actual sin que el usuario lo haya pedido. Los cron deben indicar el flujo y la salida explícitamente.

### 7.5. Limpieza de artefactos (`clean`)

- **Alcance:** solo los artefactos propios de la herramienta, declarados como patrones en `news_agent/cleanup.py`: pautas y companion JSON de `reportes/`, notas de `articulos/` y bundles de `social/`.
- **Fuera de alcance:** los bundles de `impresos/` todavía no son un objetivo de `clean`. Se limpian a mano hasta que se agregue su patrón.
- **Nunca se elimina** la caché de contenido (`cache/`) ni los recursos de la marca (`assets/`): ninguna entrada fuera de los patrones declarados se considera, aunque sea antigua.
- **Fecha de referencia:** la fecha codificada en el nombre cuando existe (pautas y bundles) y, cuando no (las notas), la fecha de modificación. La fecha del nombre es la fuente fiable: al clonar o copiar el repositorio, todos los archivos quedan con la fecha de la copia.
- **Umbral:** `--days N` (por defecto `DEFAULT_CLEAN_MAX_AGE_DAYS`, 30). Se elimina lo que supere ese corte; un valor menor que 1 es un error de uso.
- **Confirmación:** el comando lista lo que va a eliminar, con antigüedad y tamaño, y pide confirmación. `--dry-run` muestra el listado sin borrar nada y `--yes` omite la confirmación para automatizar. En un cron no hay terminal para confirmar, así que se debe usar `--yes` o `--dry-run`; sin terminal y sin `--yes`, el comando sale con error de uso.
- **Aislamiento de fallos:** si un artefacto no se puede eliminar, se registra en el log, el resto del lote continúa y el resumen final informa cuántos fallaron. Si hubo fallos parciales, el comando termina con código 1.

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
| `1` | Error de ejecución: configuración, API, pauta imposible de parsear, artefacto de entrada inexistente, fallos parciales de la edición completa o fallos parciales al eliminar artefactos |
| `2` | Error de uso: comando desconocido, opción inválida, plataforma desconocida, `--select` sin terminal interactiva, falta `--number` sin terminal y sin `--all-articles`, combinación inválida de `--number` con `--all-articles`, combinación inválida de `--write-article`/`--article`, `clean` sin terminal para confirmar o `--days` no positivo |
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
| `cover.hook` | Gancho de portada (el prompt reserva hasta tres líneas) |
| `cover.title` | Título de la edición semanal |
| `notes[]` | Una nota por cada propuesta seleccionada, en orden; `layout.notes` fija la cantidad (5 por defecto) y no puede superar los paneles disponibles |
| `notes[].proposal_number` | Número declarado por el modelo; si no coincide con la propuesta se advierte y la nota se maqueta por posición |
| `notes[].title` | Título en lenguaje llano |
| `notes[].body` | Qué pasó, en dos o tres párrafos cortos |
| `notes[].key_data` | Los datos que lo prueban: tres elementos |
| `notes[].why_it_matters` | Por qué le importa a quien lee |

El panel 1 queda reservado para la portada; con el valor por defecto, las cinco notas ocupan los paneles 2 a 6. Las fuentes de cada nota no las escribe el modelo: se toman de las fuentes sugeridas de su propia propuesta.

### 8.5. Reglas de lenguaje simple

Las cuatro reglas duras del tono se declaran en el system prompt y se verifican después en código sobre el cuerpo y el bloque «por qué te importa»:

| Regla | Verificación |
|-------|--------------|
| Frases de 15 palabras o menos | Se cuenta cada oración y se advierte las que se pasan |
| Ninguna sigla sin explicar | Se detectan las mayúsculas sostenidas y se contrastan con `style.acronym_allowlist` |
| Trato directo al lector | Directriz de redacción |
| Estructura fija: qué pasó → por qué te importa → los datos que lo prueban | Se verifica que los tres bloques existan y que `key_data` tenga tres elementos |

### 8.6. Política de errores: fatal contra advertencia

| Situación | Respuesta |
|-----------|-----------|
| JSON inválido o contrato incumplido | Reintento con nota de corrección; agotados los intentos, error |
| Cantidad de notas distinta de la cantidad de propuestas | Error: no se escribe nada |
| Nota sin título, sin cuerpo o sin «por qué te importa» | Error: no se escribe nada |
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
| `brand` | Nombre de la marca; el tríptico usa `name` como respaldo de la portada | ❌ |

El tríptico solo consume `brand.name`; `handle`, `website` y `logo_path` se aceptan en el archivo de configuración pero no se dibujan en esta pieza.

Una medida negativa, un margen que se coma la hoja, un pliegue desconocido, una cantidad de notas que no quepa en los paneles o una lista de siglas declarada como texto se detectan al cargar, con un mensaje que nombra el campo culpable. La portada ocupa un panel: una hoja de `sides × columns_per_side` paneles solo admite `sides × columns_per_side − 1` notas. Cambiar la medida del papel o el cuerpo de la tipografía no requiere tocar código: el presupuesto de caracteres se recalcula solo y el Markdown usa el `preset` declarado en la configuración.

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
