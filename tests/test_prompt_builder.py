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
        """Debe especificar el formato de salida Markdown."""
        prompt = build_system_prompt()
        assert "## 1." in prompt or "TÍTULO GANCHO" in prompt

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
        assert "ARTÍCULO 1" in result

    def test_formats_multiple_items(self):
        """Debe formatear correctamente múltiples artículos."""
        items = [
            self._make_item("T1", "S1", "R1"),
            self._make_item("T2", "S2", "R2"),
            self._make_item("T3", "S3", "R3"),
        ]

        result = build_user_prompt(items)

        assert "ARTÍCULO 1" in result
        assert "ARTÍCULO 2" in result
        assert "ARTÍCULO 3" in result
        assert "ARTÍCULO 4" not in result  # exactamente 3

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
