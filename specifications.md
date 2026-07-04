# 📋 Especificaciones de Funcionamiento: Agente Inteligente de Contenidos

**Proyecto:** Curador de Pauta Editorial Automatizado

**Medio:** La Chispa Sur

**Versión del Motor:** 1.0.0 (Python + DeepSeek API)

## 1. Objetivo General

Automatizar la recopilación, filtrado y análisis de la agenda noticiosa nacional e internacional mediante la lectura de canales RSS seleccionados, utilizando el modelo de lenguaje **DeepSeek-V4-Pro** para sintetizar y proponer tres (3) líneas editoriales semanales de alto impacto, profundidad analítica y narrativa ágil.

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
  
- **Restricción de Volumen:** El agente debe entregar **exactamente tres (3) propuestas** por informe. Ni más, ni menos.
  

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
```

## 5. Manejo de Errores y Robustez (Fail-Safe)

- **Fallas de Conexión en Feeds:** Si un canal RSS falla (caída del servidor de origen o cambio de URL), el script debe registrar el error en la terminal mediante una excepción estructurada (`try-except`) y **continuar inmediatamente** con el siguiente medio de la lista sin abortar la ejecución.
  
- **Ausencia de Datos:** En caso de que la recolección sume 0 noticias en la ventana de 48 horas, el agente detendrá el flujo antes de invocar la API de DeepSeek, generando un log de advertencia para evitar consumo innecesario de tokens.
  
- **Fallo de API Key:** El script validará la existencia de la variable de entorno `DEEPSEEK_API_KEY` antes de iniciar. Si no se encuentra, arrojará un error explícito de configuración.