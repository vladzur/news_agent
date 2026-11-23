"""Tests para el módulo de construcción de prompts."""

import pytest

from news_agent.prompt_builder import (
    ARTICLE_SYSTEM_PROMPT,
    EDITORIAL_REVIEW_SYSTEM_PROMPT,
    PORTADA_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_article_system_prompt,
    build_article_user_prompt,
    build_editorial_review_system_prompt,
    build_editorial_review_user_prompt,
    build_portada_system_prompt,
    build_portada_user_prompt,
    build_system_prompt,
    build_user_prompt,
)


class TestBuildSystemPrompt:
    """Pruebas para build_system_prompt."""

    def test_returns_non_empty_string(self):
        """Debe devolver un string no vacío."""
        prompt = build_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_contains_editorial_identity(self):
        """Debe mencionar la identidad editorial La Chispa Sur."""
        prompt = build_system_prompt()
        assert "La Chispa Sur" in prompt

    def test_contains_exactly_five_proposals_rule(self):
        """Debe indicar que se requieren exactamente 5 propuestas."""
        prompt = build_system_prompt()
        assert "cinco (5)" in prompt.lower() or "exactamente cinco" in prompt.lower()

    def test_contains_tone_guidelines(self):
        """Debe incluir directrices de tono editorial."""
        prompt = build_system_prompt()
        assert "incisivo" in prompt.lower() or "analítico" in prompt.lower()

    def test_requires_provocative_headlines(self):
        """Debe exigir titulares provocadores que no sean microresúmenes."""
        prompt = build_system_prompt().lower()
        assert "agresivos, provocadores" in prompt
        assert "no es el resumen del artículo" in prompt
        assert "clickbait" in prompt

    def test_requires_firm_grounded_editorial_criticism(self):
        """Debe exigir crítica firme basada en hechos verificables."""
        prompt = build_system_prompt().lower()
        assert "denuncia y cuestiona con fuerza" in prompt
        assert "evitando acusaciones sin fundamento" in prompt

    def test_contains_output_format(self):
        """Debe especificar el formato de salida Markdown para las propuestas."""
        prompt = build_system_prompt()
        assert "## 1." in prompt or "TÍTULO GANCHO" in prompt
        # El ejemplo de formato debe mostrar las 5 propuestas numeradas.
        assert "## 5." in prompt
        # El formato ya no debe incluir la cabecera con fecha y cantidad:
        # esos datos los agrega el código automáticamente.
        assert "# ⚡ Pauta Editorial Sugerida" not in prompt

    def test_contains_fuentes_sugeridas_section(self):
        """Debe incluir la sección de Fuentes Sugeridas en el formato de salida."""
        prompt = build_system_prompt()
        assert "Fuentes Sugeridas" in prompt

    def test_contains_fuentes_instructions(self):
        """Debe incluir instrucciones sobre cómo sugerir fuentes."""
        prompt = build_system_prompt()
        assert "reales y verificables" in prompt.lower() or "reales" in prompt.lower()

    def test_returns_base_prompt_plus_focus_section(self):
        """Sin temas debe devolver el prompt base más la sección de foco."""
        prompt = build_system_prompt()

        assert prompt.startswith(SYSTEM_PROMPT)
        assert "Criterio de foco temático" in prompt

    def test_without_topics_appends_focus_section(self):
        """Sin temas (None o lista vacía) debe añadir la sección de foco."""
        expected = build_system_prompt(main_topics=None)

        assert build_system_prompt(main_topics=[]) == expected
        assert "Criterio de foco temático" in expected

    def test_with_topics_appends_priority_section(self):
        """Con temas debe añadir la sección de prioridad manteniendo el prompt base."""
        topics = ["genocidio en Gaza", "Agenda de seguridad"]
        prompt = build_system_prompt(main_topics=topics)
        assert prompt.startswith(SYSTEM_PROMPT)
        assert "Temas de interés prioritarios" in prompt
        assert "prioridad absoluta" in prompt.lower()
        assert "Criterio de foco temático" not in prompt
        assert "Un solo eje por propuesta" in prompt
        for topic in topics:
            assert topic in prompt

    def test_without_topics_forbids_unrelated_topic_mixing(self):
        """Debe prohibir mezclar temas sin conexión directa."""
        section = build_system_prompt()[len(SYSTEM_PROMPT):].lower()

        assert "un solo eje por propuesta" in section
        assert "conexión directa y verificable" in section
        assert "no agrupes" in section

    def test_without_topics_prioritizes_editorial_line(self):
        """Debe priorizar los ejes de la línea editorial del medio."""
        section = build_system_prompt()[len(SYSTEM_PROMPT):]

        assert "línea editorial de La Chispa Sur" in section
        assert "derechos sociales, laborales y territoriales" in section
        assert "neoliberal" in section
        assert "pueblos originarios" in section
        assert "Villarrica" in section
        assert "La Araucanía" in section

    def test_base_prompt_requires_topic_cohesion(self):
        """El prompt base debe exigir un solo eje por propuesta."""
        assert "Cohesión temática de cada propuesta" in SYSTEM_PROMPT
        assert "conexión directa y verificable" in SYSTEM_PROMPT

    def test_contains_chile_focus(self):
        """Debe mencionar el enfoque en Chile."""
        prompt = build_system_prompt()
        assert "Chile" in prompt
        assert "chileno" in prompt.lower() or "chilena" in prompt.lower()

    def test_contains_geographic_distribution(self):
        """Debe especificar la distribución 3 nacionales / 2 internacionales."""
        prompt = build_system_prompt().lower()
        assert "tres (3)" in prompt
        assert "dos (2)" in prompt
        assert "nacional" in prompt
        assert "internacional" in prompt

    def test_contains_international_emphasis(self):
        """Debe exigir foco internacional en hechos que conmocionan al mundo,
        pueblos oprimidos y políticas imperialistas."""
        prompt = build_system_prompt().lower()
        assert "conmocionan al mundo" in prompt
        assert "pueblos oprimidos" in prompt
        assert "imperialistas" in prompt
        assert "estabilidad mundial" in prompt

    def test_contains_left_wing_identity(self):
        """Debe incluir la identidad de izquierda y anti-neoliberal."""
        prompt = build_system_prompt()
        assert "izquierda" in prompt.lower()
        assert "neoliberal" in prompt.lower()

    def test_requires_article_number_references(self):
        """Debe exigir referencias a números de artículo con formato [art. N]."""
        prompt = build_system_prompt()
        assert "Referencia los artículos fuente con su número" in prompt \
            or "[art. N]" in prompt

    def test_contains_verification_section(self):
        """Debe incluir sección de verificación de datos y consistencia."""
        prompt = build_system_prompt()
        assert "Verificación de datos y consistencia" in prompt

    def test_contains_logical_consistency_rules(self):
        """Debe incluir reglas de consistencia lógica entre propuestas."""
        prompt = build_system_prompt()
        assert "Coherencia entre propuestas" in prompt
        assert "Conexión lógica entre hecho y análisis" in prompt

    def test_contains_no_speculation_rule(self):
        """Debe incluir regla contra la especulación sobre motivaciones."""
        prompt = build_system_prompt()
        assert "especulación sobre motivaciones" in prompt.lower() \
            or "verdaderas intenciones" in prompt

    def test_contains_source_verification_rules(self):
        """Debe incluir reglas de verificación para fuentes sugeridas."""
        prompt = build_system_prompt()
        assert "Fuentes reales y pertinentes" in prompt

    def test_contains_self_verification_checklist(self):
        """Debe incluir lista de autoverificación antes de entregar."""
        prompt = build_system_prompt()
        assert "Autoverificación final" in prompt

    def test_does_not_include_header_in_output_format(self):
        """El formato de salida no debe incluir la cabecera con fecha/cantidad."""
        prompt = build_system_prompt()
        assert "No incluyas la cabecera" in prompt \
            or "el sistema la agregará" in prompt.lower()


class TestBuildArticleSystemPrompt:
    """Pruebas para build_article_system_prompt."""

    def test_returns_non_empty_string(self):
        """Debe devolver un string no vacío."""
        prompt = build_article_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_contains_la_chispa_sur(self):
        """Debe mencionar La Chispa Sur."""
        prompt = build_article_system_prompt()
        assert "La Chispa Sur" in prompt

    def test_contains_word_count_guidance(self):
        """Debe indicar la extensión esperada de ~1000 palabras."""
        prompt = build_article_system_prompt()
        assert "1000" in prompt or "900" in prompt

    def test_contains_left_wing_identity(self):
        """Debe incluir la identidad de izquierda y anti-neoliberal."""
        prompt = build_article_system_prompt()
        assert "izquierda" in prompt.lower()
        assert "neoliberal" in prompt.lower()

    def test_contains_article_structure(self):
        """Debe incluir la estructura esperada del artículo."""
        prompt = build_article_system_prompt()
        assert "Lead" in prompt or "entrada" in prompt.lower()

    def test_returns_article_system_prompt_constant(self):
        """Debe devolver exactamente la constante ARTICLE_SYSTEM_PROMPT."""
        assert build_article_system_prompt() == ARTICLE_SYSTEM_PROMPT

    def test_contains_verification_section(self):
        """Debe incluir sección de verificación de hechos y consistencia argumental."""
        prompt = build_article_system_prompt()
        assert "Verificación de hechos y consistencia argumental" in prompt

    def test_contains_fact_tracing_rules(self):
        """Debe incluir reglas de trazabilidad de datos a fuentes."""
        prompt = build_article_system_prompt()
        assert "Trazabilidad de cada dato" in prompt
        assert "no conviertas hipótesis en afirmaciones" in prompt.lower()

    def test_contains_argument_consistency_rules(self):
        """Debe incluir reglas de consistencia argumental y línea editorial."""
        prompt = build_article_system_prompt()
        assert "Consistencia con la línea editorial" in prompt
        assert "Cierre coherente" in prompt

    def test_requires_provocative_article_headline(self):
        """Debe pedir un titular provocador y no un microresumen."""
        prompt = build_article_system_prompt().lower()
        assert "agresivo, provocador" in prompt
        assert "no lo conviertas en un micro resumen" in prompt
        assert "llamado claro a la lectura" in prompt

    def test_requires_firm_criticism_without_false_neutrality(self):
        """Debe rechazar la falsa neutralidad sin permitir acusaciones inventadas."""
        prompt = build_article_system_prompt().lower()
        assert "crítica sin falsa neutralidad" in prompt
        assert "denuncia las relaciones de poder" in prompt
        assert "no autoriza a inventar" in prompt

    def test_contains_post_writing_verification(self):
        """Debe incluir verificación posterior a la escritura."""
        prompt = build_article_system_prompt()
        assert "Después de escribir" in prompt
        assert "prueba de lectura inversa" in prompt.lower()

    def test_prohibits_internal_art_references(self):
        """Debe prohibir referencias internas [art. N] en el artículo final."""
        prompt = build_article_system_prompt()
        assert "[art. N]" in prompt or "NUNCA incluyas referencias internas" in prompt

    def test_requires_a_headline_of_12_to_16_words(self):
        """Debe fijar el rango de 12 a 16 palabras para el titular."""
        prompt = " ".join(build_article_system_prompt().lower().split())

        assert "entre 12 y 16 palabras" in prompt
        assert "núcleo del conflicto" in prompt

    def test_requires_a_deck_of_25_to_45_words(self):
        """Debe exigir la bajada con su rango y sus reglas."""
        prompt = " ".join(build_article_system_prompt().lower().split())

        assert "entre 25 y 45 palabras" in prompt
        assert "bajada" in prompt
        assert "puente entre el titular" in prompt

    def test_mandates_the_deck_in_the_structure(self):
        """La plantilla del artículo debe incluir la línea de bajada."""
        prompt = build_article_system_prompt()

        assert "*[Bajada o copete" in prompt

    def test_requires_single_focus_and_discards_unrelated_material(self):
        """Debe exigir foco único y descartar material de otros temas."""
        prompt = build_article_system_prompt().lower()

        assert "foco editorial único" in prompt
        assert "un solo eje" in prompt
        assert "descártalo" in prompt
        assert "sin conexiones forzadas" in prompt


class TestBuildArticleUserPrompt:
    """Pruebas para build_article_user_prompt."""

    @pytest.fixture
    def sample_proposal(self):
        """Propuesta de ejemplo para tests."""
        return {
            "title": "Título Gancho del Artículo",
            "enfoque": "Este es el enfoque editorial con análisis crítico.",
            "puntos": [
                "Primer punto clave a desarrollar.",
                "Segundo punto clave con datos.",
                "Tercer punto con pregunta abierta.",
            ],
            "fuentes": [
                "Fuente A: Descripción de la fuente A.",
                "Fuente B: Descripción de la fuente B.",
            ],
        }

    def test_formats_title(self, sample_proposal):
        """Debe incluir el título de la propuesta."""
        result = build_article_user_prompt(sample_proposal)
        assert "Título Gancho del Artículo" in result

    def test_formats_enfoque(self, sample_proposal):
        """Debe incluir el enfoque editorial."""
        result = build_article_user_prompt(sample_proposal)
        assert "enfoque editorial con análisis crítico" in result

    def test_formats_puntos_clave(self, sample_proposal):
        """Debe incluir los puntos clave numerados."""
        result = build_article_user_prompt(sample_proposal)
        assert "1. Primer punto clave" in result
        assert "2. Segundo punto clave" in result
        assert "3. Tercer punto" in result

    def test_formats_fuentes(self, sample_proposal):
        """Debe incluir las fuentes sugeridas."""
        result = build_article_user_prompt(sample_proposal)
        assert "Fuente A" in result
        assert "Fuente B" in result

    def test_includes_instruction(self, sample_proposal):
        """Debe incluir la instrucción de escritura."""
        result = build_article_user_prompt(sample_proposal)
        assert "artículo completo" in result.lower() or "escribe" in result.lower()

    def test_includes_single_focus_reminder(self, sample_proposal):
        """Debe recordar desarrollar solo el eje de la propuesta."""
        result = build_article_user_prompt(sample_proposal)

        assert "Foco único" in result
        assert "descártalo" in result

    def test_reinforces_provocative_headline_and_editorial_criticism(
        self, sample_proposal
    ):
        """Debe reforzar el titular provocador y la crítica fundamentada."""
        result = build_article_user_prompt(sample_proposal).lower()
        assert "titular debe ser agresivo, provocador" in result
        assert "no lo redactes como un micro resumen" in result
        assert "crítica editorial firme" in result

    def test_states_the_headline_and_deck_lengths(self, sample_proposal):
        """Debe recordar los rangos de 12-16 y 25-45 palabras."""
        result = build_article_user_prompt(sample_proposal).lower()

        assert "entre 12 y 16 palabras" in result
        assert "entre 25 y 45" in result

    def test_handles_missing_fuentes(self):
        """Debe funcionar sin fuentes (lista vacía)."""
        proposal = {
            "title": "Título",
            "enfoque": "Enfoque.",
            "puntos": ["Punto 1."],
            "fuentes": [],
        }
        result = build_article_user_prompt(proposal)
        assert "Título" in result
        assert "Fuentes sugeridas" not in result

    def test_includes_date(self, sample_proposal):
        """Debe incluir la fecha actual."""
        result = build_article_user_prompt(sample_proposal)
        assert "2026" in result

    # ------------------------------------------------------------------
    # Tests para source_articles (material de origen desde companion)
    # ------------------------------------------------------------------

    def test_includes_source_articles_when_provided(self, sample_proposal):
        """Debe incluir la sección de material de origen cuando hay source_articles."""
        source_articles = [
            {
                "title": "Artículo fuente 1",
                "source": "La Tercera",
                "link": "https://example.com/1",
                "summary": "Resumen del artículo fuente 1.",
                "content": "Contenido completo del artículo fuente 1.",
            },
            {
                "title": "Artículo fuente 2",
                "source": "DF Diario",
                "link": "https://example.com/2",
                "summary": "Resumen del artículo fuente 2.",
                "content": "Contenido completo del artículo fuente 2.",
            },
        ]

        result = build_article_user_prompt(sample_proposal, source_articles=source_articles)

        assert "Material de origen disponible" in result
        assert "Artículo fuente 1" in result
        assert "Artículo fuente 2" in result
        assert "La Tercera" in result
        assert "DF Diario" in result

    def test_source_articles_are_limited_to_the_proposal_axis(
        self, sample_proposal
    ):
        """Debe pedir descartar el material de origen de otros temas."""
        source_articles = [
            {
                "title": "Noticia de economía",
                "source": "Cooperativa",
                "link": "https://example.com/eco",
                "summary": "Resumen breve.",
                "content": "Contenido de la noticia.",
            }
        ]

        result = build_article_user_prompt(
            sample_proposal, source_articles=source_articles
        )

        assert "respalden el eje de la propuesta" in result
        assert "descarta los que traten otros temas" in result

    def test_does_not_include_section_when_source_articles_is_none(
        self, sample_proposal
    ):
        """No debe incluir la sección de material de origen cuando es None."""
        result = build_article_user_prompt(sample_proposal, source_articles=None)
        assert "Material de origen disponible" not in result

    def test_does_not_include_section_when_source_articles_is_empty(
        self, sample_proposal
    ):
        """No debe incluir la sección de material de origen cuando la lista está vacía."""
        result = build_article_user_prompt(sample_proposal, source_articles=[])
        assert "Material de origen disponible" not in result

    def test_formats_source_article_content_correctly(self, sample_proposal):
        """Debe formatear correctamente el contenido completo de los artículos fuente."""
        source_articles = [
            {
                "title": "Noticia de economía",
                "source": "Cooperativa",
                "link": "https://example.com/eco",
                "summary": "Resumen breve.",
                "content": "Contenido largo extraído con trafilatura.",
            }
        ]

        result = build_article_user_prompt(sample_proposal, source_articles=source_articles)

        assert "### Artículo fuente 1" in result
        assert "**Título:** Noticia de economía" in result
        assert "**Fuente:** Cooperativa" in result
        assert "**Enlace:** https://example.com/eco" in result
        assert "**Resumen:** Resumen breve." in result
        assert "**Contenido:**" in result
        assert "Contenido largo extraído con trafilatura." in result

    def test_handles_missing_fields_in_source_articles(self, sample_proposal):
        """Debe manejar campos ausentes en los artículos fuente sin errores."""
        source_articles = [
            {
                "title": "Solo título",
                "source": "Solo fuente",
                "link": "",
                "summary": "",
                "content": "",
            }
        ]

        result = build_article_user_prompt(sample_proposal, source_articles=source_articles)

        assert "Material de origen disponible" in result
        assert "Solo título" in result
        # No debe incluir Enlace si está vacío
        assert "**Enlace:**" not in result


class TestBuildUserPrompt:
    """Pruebas para build_user_prompt."""

    def _make_item(self, title, source, summary_clean, link=None):
        """Helper para construir un item filtrado."""
        item = {
            "title": title,
            "source": source,
            "summary_clean": summary_clean,
        }
        if link:
            item["link"] = link
        return item

    def test_formats_single_item(self):
        """Debe formatear correctamente un solo artículo."""
        items = [
            self._make_item("Título de prueba", "Medio X", "Resumen de prueba"),
        ]

        result = build_user_prompt(items)

        assert "Título de prueba" in result
        assert "Medio X" in result
        assert "Resumen de prueba" in result
        assert "Fuente:" in result

    def test_formats_multiple_items(self):
        """Debe formatear correctamente múltiples artículos."""
        items = [
            self._make_item("T1", "S1", "R1"),
            self._make_item("T2", "S2", "R2"),
            self._make_item("T3", "S3", "R3"),
        ]

        result = build_user_prompt(items)

        assert "**Fuente:** S1" in result
        assert "**Fuente:** S2" in result
        assert "**Fuente:** S3" in result
        assert result.count("---") >= 4  # separadores entre artículos + inicio/fin

    def test_includes_article_count(self):
        """Debe incluir la cantidad de artículos procesados."""
        items = [
            self._make_item("T1", "S1", "R1"),
            self._make_item("T2", "S2", "R2"),
        ]

        result = build_user_prompt(items)

        assert "2 artículos" in result or "2 artículo" in result

    def test_includes_link_when_present(self):
        """Debe incluir el enlace cuando está disponible."""
        items = [
            self._make_item("T1", "S1", "R1", link="https://example.com/1"),
        ]

        result = build_user_prompt(items)

        assert "https://example.com/1" in result
        assert "Enlace" in result

    def test_handles_missing_link(self):
        """No debe incluir la línea de enlace cuando link es None."""
        items = [
            self._make_item("T1", "S1", "R1", link=None),
        ]

        result = build_user_prompt(items)

        assert "Enlace:" not in result

    def test_includes_analysis_instruction(self):
        """Debe incluir la instrucción final de análisis."""
        items = [
            self._make_item("T1", "S1", "R1"),
        ]

        result = build_user_prompt(items)

        assert "propuestas" in result.lower()

    def test_instructs_five_proposals(self):
        """La instrucción final debe pedir cinco propuestas: 3 nacionales y 2 internacionales."""
        items = [
            self._make_item("T1", "S1", "R1"),
        ]

        result = build_user_prompt(items).lower()

        assert "cinco propuestas" in result
        assert "nacionales" in result
        assert "internacionales" in result

    def test_includes_article_reference_instruction(self):
        """La instrucción final debe recordar usar referencias [art. N]."""
        items = [
            self._make_item("T1", "S1", "R1"),
        ]

        result = build_user_prompt(items)

        assert "[art. N]" in result \
            or "Referencia los artículos fuente" in result \
            or "art. 42" in result

    def test_empty_items_returns_empty_string(self):
        """Debe devolver cadena vacía cuando no hay artículos."""
        assert build_user_prompt([]) == ""

    def test_includes_date_in_header(self):
        """Debe incluir la fecha de análisis en la cabecera."""
        items = [
            self._make_item("T1", "S1", "R1"),
        ]

        result = build_user_prompt(items)

        assert "Fecha de análisis" in result
        # Debe contener un año (2026) en el prompt
        assert "2026" in result

    def test_includes_accuracy_reminders(self):
        """Debe incluir recordatorios de precisión al final del prompt."""
        items = [
            self._make_item("T1", "S1", "R1"),
        ]

        result = build_user_prompt(items)

        assert "Recordatorios críticos de precisión" in result

    def test_includes_date_and_count_reinforcement(self):
        """Debe reforzar la fecha y cantidad exacta al final del prompt."""
        items = [
            self._make_item("T1", "S1", "R1"),
            self._make_item("T2", "S2", "R2"),
        ]

        result = build_user_prompt(items)

        assert "fecha de análisis es" in result.lower()
        assert "2 artículos" in result or "2 artículo" in result or "**2 artículos**" in result

    def test_includes_consistency_reminder(self):
        """Debe recordar revisar coherencia entre las cinco propuestas."""
        items = [
            self._make_item("T1", "S1", "R1"),
        ]

        result = build_user_prompt(items)

        assert "coherencia" in result.lower() or "contradicciones" in result.lower()
        assert "cinco" in result.lower()

    def test_includes_source_attribution_reminder(self):
        """Debe recordar verificar atribución correcta de fuentes."""
        items = [
            self._make_item("T1", "S1", "R1"),
        ]

        result = build_user_prompt(items)

        assert "atribuida al medio correcto" in result.lower() \
            or "nombre del medio" in result.lower()

    def test_includes_main_topics_when_provided(self):
        """Debe incluir los temas prioritarios cuando se proporcionan."""
        items = [self._make_item("T1", "S1", "R1")]
        topics = ["genocidio en Gaza", "Retrocesos laborales"]

        result = build_user_prompt(items, main_topics=topics)

        assert "MAIN_TOPICS" in result
        assert "genocidio en Gaza" in result
        assert "Retrocesos laborales" in result
        assert "un solo eje" in result.lower()

    def test_omits_main_topics_when_not_provided(self):
        """No debe incluir la sección de temas si no se proporcionan."""
        items = [self._make_item("T1", "S1", "R1")]

        result = build_user_prompt(items)

        assert "MAIN_TOPICS" not in result

    def test_includes_single_focus_reminder_without_topics(self):
        """Sin temas debe recordar el foco único y la prioridad editorial."""
        items = [self._make_item("T1", "S1", "R1")]

        result = build_user_prompt(items)

        assert "Foco temático único" in result
        assert "un solo eje" in result.lower()
        assert "Villarrica" in result


class TestPortadaPrompts:
    """Pruebas del prompt del editor de portada."""

    def test_returns_the_constant(self):
        """Debe devolver exactamente PORTADA_SYSTEM_PROMPT."""
        assert build_portada_system_prompt() == PORTADA_SYSTEM_PROMPT

    def test_contains_the_portada_role(self):
        """Debe presentarse como editor de portada de La Chispa Sur."""
        prompt = build_portada_system_prompt()

        assert "editor de portada" in prompt
        assert "La Chispa Sur" in prompt

    def test_contains_the_headline_rules(self):
        """Debe fijar el rango de 12-16 palabras y el núcleo del conflicto."""
        prompt = build_portada_system_prompt().lower()

        assert "12 a 16 palabras" in prompt
        assert "núcleo del conflicto" in prompt
        assert "tesis + hecho duro" in prompt
        assert "contraste o paradoja" in prompt
        assert "pregunta retórica + enfoque" in prompt

    def test_contains_the_deck_rules(self):
        """Debe fijar el rango de 25-45 palabras y sus tres reglas."""
        prompt = build_portada_system_prompt().lower()

        assert "25 a 45 palabras" in prompt
        assert "anclaje factual" in prompt
        assert "complementariedad" in prompt
        assert "tensión narrativa" in prompt

    def test_prohibits_clickbait_and_invented_data(self):
        """Debe prohibir el clickbait y la invención de datos."""
        prompt = build_portada_system_prompt().lower()

        assert "clickbait" in prompt
        assert "inventar datos" in prompt
        assert "no introduzcas hechos" in prompt

    def test_requires_three_differentiated_proposals(self):
        """Debe exigir tres propuestas con los enfoques pedidos."""
        prompt = build_portada_system_prompt().lower()

        assert "3 propuestas diferenciadas" in prompt
        assert "denuncia / tesis política" in prompt
        assert "narrativo / humano" in prompt
        assert "analítico / geopolítico" in prompt
        assert "json" in prompt

    def test_user_prompt_includes_the_article(self):
        """Debe incluir el markdown del artículo a titular."""
        result = build_portada_user_prompt("# Titular\n\nCuerpo del artículo.")

        assert "# Titular" in result
        assert "Cuerpo del artículo." in result

    def test_user_prompt_includes_the_pauta_angle(self):
        """Debe incluir el título y el enfoque aprobados como referencia."""
        result = build_portada_user_prompt(
            "cuerpo",
            {"title": "Título de pauta", "enfoque": "Enfoque aprobado"},
        )

        assert "Título de pauta" in result
        assert "Enfoque aprobado" in result

    def test_user_prompt_works_without_a_proposal(self):
        """Debe funcionar sin propuesta de pauta."""
        result = build_portada_user_prompt("cuerpo")

        assert "cuerpo" in result
        assert "Ángulo aprobado" not in result


class TestEditorialReviewPrompts:
    """Pruebas del prompt del editor periodístico."""

    def test_returns_the_constant(self):
        """Debe devolver exactamente EDITORIAL_REVIEW_SYSTEM_PROMPT."""
        assert (
            build_editorial_review_system_prompt()
            == EDITORIAL_REVIEW_SYSTEM_PROMPT
        )

    def test_contains_the_editor_role(self):
        """Debe presentarse como editor periodístico de La Chispa Sur."""
        prompt = build_editorial_review_system_prompt().lower()

        assert "editor periodístico" in prompt
        assert "la chispa sur" in prompt
        assert "jefe de cierre" in prompt

    def test_contains_the_editorial_identity(self):
        """Debe fijar la línea editorial que la revisión debe cuidar."""
        prompt = build_editorial_review_system_prompt().lower()

        assert "marxista" in prompt
        assert "antiimperialista" in prompt
        assert "neoliberal" in prompt
        assert "villarrica" in prompt
        assert "la araucanía" in prompt

    def test_contains_the_three_review_axes(self):
        """Debe cubrir redacción, coherencia y estilo."""
        prompt = build_editorial_review_system_prompt().lower()

        assert "redacción" in prompt
        assert "coherencia" in prompt
        assert "estilo" in prompt
        assert "ortografía" in prompt
        assert "clickbait" in prompt

    def test_prohibits_new_facts_and_structure_changes(self):
        """Debe prohibir inventar datos y alterar la estructura."""
        prompt = build_editorial_review_system_prompt().lower()

        assert "no agregues hechos" in prompt
        assert "no borres datos verificables" in prompt
        assert "mismo número de secciones" in prompt
        assert "bloque de fuentes" in prompt
        assert "[art. n]" in prompt

    def test_requires_the_json_contract(self):
        """Debe exigir las cuatro claves del contrato."""
        prompt = build_editorial_review_system_prompt().lower()

        assert '"titular"' in prompt
        assert '"bajada"' in prompt
        assert '"cuerpo"' in prompt
        assert '"resumen_cambios"' in prompt
        assert "12 a 16 palabras" in prompt
        assert "25 a 45" in prompt

    def test_user_prompt_includes_the_pieces_and_the_proposal(self):
        """Debe incluir propuesta, titular, bajada y cuerpo."""
        result = build_editorial_review_user_prompt(
            "Titular seleccionado",
            "Bajada seleccionada",
            "Cuerpo del artículo.",
            {
                "title": "Título de pauta",
                "enfoque": "Enfoque aprobado",
                "puntos": ["Primer punto", "Segundo punto"],
            },
        )

        assert "Título de pauta" in result
        assert "Enfoque aprobado" in result
        assert "Primer punto" in result
        assert "Titular seleccionado" in result
        assert "Bajada seleccionada" in result
        assert "Cuerpo del artículo." in result
        assert "12 y 16 palabras" in result
        assert "25 y 45" in result

    def test_user_prompt_works_without_a_proposal(self):
        """Debe funcionar sin propuesta de pauta."""
        result = build_editorial_review_user_prompt(
            "Titular", "Bajada", "Cuerpo"
        )

        assert "Titular" in result
        assert "Bajada" in result
        assert "Cuerpo" in result
        assert "Propuesta aprobada" not in result
