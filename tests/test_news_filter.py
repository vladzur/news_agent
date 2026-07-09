"""Tests para el módulo de filtrado y limpieza de noticias."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from news_agent.news_filter import filter_items, is_within_window, strip_html, truncate


# ---------------------------------------------------------------------------
# Tests de is_within_window
# ---------------------------------------------------------------------------

class TestIsWithinWindow:
    """Pruebas para la función is_within_window."""

    def test_recent_item_is_within_window(self):
        """Un artículo publicado hace 1 hora debe estar dentro de la ventana de 168h."""
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).timetuple()
        assert is_within_window(recent) is True

    def test_old_item_is_outside_window(self):
        """Un artículo de hace 200 horas debe estar fuera de la ventana de 168h."""
        old = (datetime.now(timezone.utc) - timedelta(hours=200)).timetuple()
        assert is_within_window(old) is False

    def test_none_timestamp_is_outside_window(self):
        """Un timestamp None siempre debe estar fuera de la ventana."""
        assert is_within_window(None) is False

    def test_custom_window_hours(self):
        """Debe respetar un valor de ventana personalizado."""
        recent = (datetime.now(timezone.utc) - timedelta(hours=2)).timetuple()
        # Ventana de 1 hora: debe quedar fuera
        assert is_within_window(recent, window_hours=1) is False
        # Ventana de 4 horas: debe quedar dentro
        assert is_within_window(recent, window_hours=4) is True

    def test_exact_boundary(self):
        """Un artículo justo en el límite de la ventana debe estar dentro."""
        exact = (datetime.now(timezone.utc) - timedelta(hours=168)).timetuple()
        assert is_within_window(exact, window_hours=169) is True


# ---------------------------------------------------------------------------
# Tests de strip_html
# ---------------------------------------------------------------------------

class TestStripHtml:
    """Pruebas para la función strip_html."""

    def test_strips_simple_tags(self):
        """Debe eliminar etiquetas HTML simples."""
        result = strip_html("<p>Hola <b>mundo</b></p>")
        assert result == "Hola mundo"

    def test_strips_script_tags_with_content(self):
        """Debe eliminar etiquetas script junto con su contenido."""
        result = strip_html("<p>Texto</p><script>alert('xss')</script><p>Más</p>")
        assert "alert" not in result
        assert "script" not in result.lower()
        assert "Texto" in result
        assert "Más" in result

    def test_strips_style_tags_with_content(self):
        """Debe eliminar etiquetas style junto con su contenido."""
        result = strip_html("<style>body { color: red; }</style><p>Visible</p>")
        assert "color" not in result
        assert "body" not in result.lower()
        assert "Visible" in result

    def test_strips_html_comments(self):
        """Debe eliminar comentarios HTML."""
        result = strip_html("<!-- esto es un comentario --><p>Contenido</p>")
        assert "comentario" not in result
        assert "Contenido" in result

    def test_decodes_html_entities(self):
        """Debe decodificar entidades HTML comunes."""
        result = strip_html("El ni&ntilde;o &amp; la ni&ntilde;a")
        assert "niño" in result
        assert "&" in result  # &amp; decodificado a &

    def test_normalizes_whitespace(self):
        """Debe colapsar múltiples espacios en uno solo."""
        result = strip_html("<p>Hola    mundo\n\n\t\tcruel</p>")
        assert result == "Hola mundo cruel"

    def test_none_returns_empty_string(self):
        """None debe devolver cadena vacía."""
        assert strip_html(None) == ""

    def test_plain_text_passes_through(self):
        """El texto sin HTML debe pasar sin cambios."""
        result = strip_html("Texto limpio sin marcas")
        assert result == "Texto limpio sin marcas"

    def test_nbsp_replaced_with_space(self):
        """&nbsp; debe ser reemplazado por espacio."""
        result = strip_html("Hola&nbsp;mundo")
        assert result == "Hola mundo"


# ---------------------------------------------------------------------------
# Tests de truncate
# ---------------------------------------------------------------------------

class TestTruncate:
    """Pruebas para la función truncate."""

    def test_short_text_not_truncated(self):
        """Un texto más corto que el límite no debe ser truncado."""
        result = truncate("Hola", max_chars=200)
        assert result == "Hola"

    def test_exact_limit_not_changed(self):
        """Un texto exactamente en el límite no debe ser truncado."""
        text = "a" * 200
        result = truncate(text, max_chars=200)
        assert result == text

    def test_long_text_truncated_with_ellipsis(self):
        """Un texto largo debe ser truncado con puntos suspensivos."""
        text = "Palabra " * 50  # ~400 caracteres
        result = truncate(text, max_chars=200)
        assert len(result) <= 201  # 200 + posible "…"
        assert result.endswith("…")

    def test_truncation_preserves_words(self):
        """El truncado debe evitar cortar palabras a la mitad."""
        text = "Una frase completa " * 10
        result = truncate(text, max_chars=100)
        # Debe terminar en espacio + "…" o en palabra completa + "…"
        assert result.endswith("…")
        # La parte antes de "…" no debe cortar una palabra
        body = result[:-1]
        if body:
            assert body[-1] in (" ", "a", "e", "i", "o", "u")

    def test_default_max_chars(self):
        """Debe usar el valor por defecto (SUMMARY_MAX_CHARS) si no se especifica."""
        text = "a" * 800  # Más largo que SUMMARY_MAX_CHARS=600
        result = truncate(text)
        assert len(result) <= 601  # SUMMARY_MAX_CHARS + posible "…"


# ---------------------------------------------------------------------------
# Tests de filter_items
# ---------------------------------------------------------------------------

class TestFilterItems:
    """Pruebas para la función filter_items (pipeline completo de filtrado)."""

    def _make_item(self, title, source, summary, hours_ago, link=None):
        """Helper para construir un item de prueba."""
        pub_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        return {
            "title": title,
            "source": source,
            "summary": summary,
            "published_parsed": pub_time.timetuple(),
            "link": link,
        }

    def test_filters_out_old_items(self):
        """Debe excluir artículos fuera de la ventana de 168h (7 días)."""
        items = [
            self._make_item("Reciente", "S1", "Resumen", 1),
            self._make_item("Antiguo", "S2", "Resumen", 200),
        ]

        result = filter_items(items)
        assert len(result) == 1
        assert result[0]["title"] == "Reciente"

    def test_cleans_html_in_summary(self):
        """Debe limpiar HTML del campo summary."""
        items = [
            self._make_item("T1", "S1", "<p>Texto <b>importante</b></p>", 1),
        ]

        result = filter_items(items)
        assert result[0]["summary_clean"] == "Texto importante"

    def test_truncates_long_summary(self):
        """Debe truncar resúmenes largos a SUMMARY_MAX_CHARS (600) caracteres."""
        long_text = "x " * 500  # ~1000 caracteres
        items = [
            self._make_item("T1", "S1", long_text, 1),
        ]

        result = filter_items(items)
        assert len(result[0]["summary_clean"]) <= 601  # SUMMARY_MAX_CHARS + posible "…"

    def test_includes_correct_fields(self):
        """Los items filtrados deben contener las claves esperadas."""
        items = [
            self._make_item("Título", "Medio", "Resumen", 1, "https://example.com/1"),
        ]

        result = filter_items(items)
        item = result[0]
        assert "title" in item
        assert "source" in item
        assert "summary_clean" in item
        assert "link" in item
        assert item["title"] == "Título"
        assert item["source"] == "Medio"
        assert item["link"] == "https://example.com/1"

    def test_excludes_items_without_timestamp(self):
        """Debe excluir artículos sin fecha de publicación."""
        items = [
            {
                "title": "Sin fecha",
                "source": "S1",
                "summary": "Resumen",
                "published_parsed": None,
                "link": None,
            },
        ]

        result = filter_items(items)
        assert len(result) == 0

    def test_empty_list_returns_empty(self):
        """Una lista vacía debe devolver lista vacía."""
        assert filter_items([]) == []

    def test_all_old_returns_empty(self):
        """Si todos los artículos son antiguos, debe devolver lista vacía."""
        items = [
            self._make_item(f"T{i}", "S1", "R", 200) for i in range(3)
        ]

        result = filter_items(items)
        assert result == []

    def test_all_items_filtered_stats(self):
        """Verifica que se filtren correctamente múltiples items."""
        items = [
            self._make_item("T1", "S1", "<p>R1</p>", 1),
            self._make_item("T2", "S2", "<p>R2</p>", 3),
            self._make_item("T3", "S3", "<p>R3</p>", 200),  # fuera de ventana
        ]

        result = filter_items(items)
        assert len(result) == 2
        sources = {r["source"] for r in result}
        assert sources == {"S1", "S2"}

    # -------------------------------------------------------------------
    # Tests con full_content (enriquecimiento de contenido)
    # -------------------------------------------------------------------

    def test_prefers_full_content_over_summary(self):
        """Cuando full_content está presente, summary_clean debe usarlo."""
        items = [
            {
                "title": "T1",
                "source": "S1",
                "summary": "Resumen RSS corto.",
                "full_content": "Texto completo extraído del artículo con mucho "
                "más detalle y contexto.",
                "published_parsed": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).timetuple(),
                "link": "https://example.com/1",
            },
        ]

        result = filter_items(items)
        assert len(result) == 1
        # Debe preferir full_content
        assert "Texto completo extraído" in result[0]["summary_clean"]

    def test_falls_back_to_summary_when_no_full_content(self):
        """Sin full_content, debe usar el summary RSS original."""
        items = [
            {
                "title": "T1",
                "source": "S1",
                "summary": "Resumen RSS original.",
                "published_parsed": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).timetuple(),
                "link": "https://example.com/1",
            },
        ]

        result = filter_items(items)
        assert len(result) == 1
        assert "Resumen RSS original" in result[0]["summary_clean"]

    def test_preserves_debug_fields(self):
        """Los campos summary_raw y full_content deben aparecer en el output."""
        items = [
            {
                "title": "T1",
                "source": "S1",
                "summary": "Resumen RSS.",
                "full_content": "Contenido completo.",
                "published_parsed": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).timetuple(),
                "link": "https://example.com/1",
            },
        ]

        result = filter_items(items)
        assert len(result) == 1
        assert result[0]["summary_raw"] == "Resumen RSS."
        assert result[0]["full_content"] == "Contenido completo."

    def test_full_content_is_stripped_and_truncated(self):
        """El full_content debe pasar por strip_html y truncate igual que summary."""
        items = [
            {
                "title": "T1",
                "source": "S1",
                "summary": "Corto.",
                "full_content": "<p>Texto <b>HTML</b> muy largo. " + ("x " * 500) + "</p>",
                "published_parsed": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).timetuple(),
                "link": "https://example.com/1",
            },
        ]

        result = filter_items(items)
        assert len(result) == 1
        # No debe contener etiquetas HTML
        assert "<p>" not in result[0]["summary_clean"]
        assert "<b>" not in result[0]["summary_clean"]
        # Debe estar truncado (el texto sin truncar sería ~1000 chars)
        assert len(result[0]["summary_clean"]) <= 1001  # SUMMARY_MAX_CHARS + posible "…" + margen

    def test_full_content_none_preserved_in_output(self):
        """Si no hay full_content, el campo debe aparecer como None."""
        items = [
            {
                "title": "T1",
                "source": "S1",
                "summary": "Resumen.",
                "published_parsed": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).timetuple(),
                "link": None,
            },
        ]

        result = filter_items(items)
        assert len(result) == 1
        assert result[0]["full_content"] is None
