"""Tests para el módulo de construcción de prompts."""

import pytest

from news_agent.prompt_builder import (
    ARTICLE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_article_system_prompt,
    build_article_user_prompt,
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

    def test_contains_exactly_three_proposals_rule(self):
        """Debe indicar que se requieren exactamente 3 propuestas."""
        prompt = build_system_prompt()
        assert "tres (3)" in prompt.lower() or "exactamente tres" in prompt.lower()

    def test_contains_tone_guidelines(self):
        """Debe incluir directrices de tono editorial."""
        prompt = build_system_prompt()
        assert "incisivo" in prompt.lower() or "analítico" in prompt.lower()

    def test_contains_output_format(self):
        """Debe especificar el formato de salida Markdown para las propuestas."""
        prompt = build_system_prompt()
        assert "## 1." in prompt or "TÍTULO GANCHO" in prompt
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

    def test_returns_system_prompt_constant(self):
        """Debe devolver exactamente la constante SYSTEM_PROMPT."""
        assert build_system_prompt() == SYSTEM_PROMPT

    def test_contains_chile_focus(self):
        """Debe mencionar el enfoque en Chile."""
        prompt = build_system_prompt()
        assert "Chile" in prompt
        assert "chileno" in prompt.lower() or "chilena" in prompt.lower()

    def test_contains_geographic_distribution(self):
        """Debe especificar la distribución geográfica 90% nacional / 10% internacional."""
        prompt = build_system_prompt()
        assert "90%" in prompt or "90 %" in prompt
        assert "10%" in prompt or "10 %" in prompt
        assert "nacional" in prompt.lower() or "chilenas" in prompt.lower()
        assert "internacional" in prompt.lower()

    def test_contains_left_wing_identity(self):
        """Debe incluir la identidad de izquierda y anti-neoliberal."""
        prompt = build_system_prompt()
        assert "izquierda" in prompt.lower()
        assert "neoliberal" in prompt.lower()

    def test_prohibits_article_number_references(self):
        """Debe prohibir referencias a números de artículo interno."""
        prompt = build_system_prompt()
        assert "Prohibido referenciar números de artículo" in prompt \
            or "prohibido referenciar" in prompt.lower()

    def test_contains_verification_section(self):
        """Debe incluir sección de verificación de datos y consistencia."""
        prompt = build_system_prompt()
        assert "Verificación de datos y consistencia" in prompt

    def test_contains_factual_precision_rules(self):
        """Debe incluir reglas de precisión factual (cifras, atribución, nombres)."""
        prompt = build_system_prompt()
        assert "Cifras, porcentajes y fechas" in prompt
        assert "Atribución correcta" in prompt
        assert "Nombres propios" in prompt

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

    def test_contains_post_writing_verification(self):
        """Debe incluir verificación posterior a la escritura."""
        prompt = build_article_system_prompt()
        assert "Después de escribir" in prompt
        assert "prueba de lectura inversa" in prompt.lower()


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

    def test_includes_no_article_numbers_warning(self):
        """La instrucción final debe recordar no usar números de artículo."""
        items = [
            self._make_item("T1", "S1", "R1"),
        ]

        result = build_user_prompt(items)

        assert "Cita solo el **nombre del medio**" in result \
            or "Nunca incluyas números de artículo" in result \
            or "nunca incluyas" in result.lower()

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
        """Debe recordar revisar coherencia entre las tres propuestas."""
        items = [
            self._make_item("T1", "S1", "R1"),
        ]

        result = build_user_prompt(items)

        assert "coherencia" in result.lower() or "contradicciones" in result.lower()

    def test_includes_source_attribution_reminder(self):
        """Debe recordar verificar atribución correcta de fuentes."""
        items = [
            self._make_item("T1", "S1", "R1"),
        ]

        result = build_user_prompt(items)

        assert "atribuida al medio correcto" in result.lower() \
            or "nombre del medio" in result.lower()
