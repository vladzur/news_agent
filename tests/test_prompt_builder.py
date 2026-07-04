"""Tests para el módulo de construcción de prompts."""

from news_agent.prompt_builder import (
    SYSTEM_PROMPT,
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
