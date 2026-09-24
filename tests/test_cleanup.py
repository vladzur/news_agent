"""Tests de la limpieza de artefactos antiguos (comando ``clean``)."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from news_agent.cleanup import (
    ARTICLES_TARGET,
    REPORTS_TARGET,
    StaleEntry,
    find_stale_entries,
    format_size,
    remove_entries,
)
from news_agent.config import (
    DEFAULT_ARTICLES_DIR,
    DEFAULT_REPORTS_DIR,
    DEFAULT_SOCIAL_OUTPUT_DIR,
)

# Momento de referencia fijo: así las antigüedades son deterministas y no
# dependen del reloj de la máquina que corre la suite.
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def _create_file(path: Path, when: datetime) -> Path:
    """Crea un archivo con contenido y le fija la fecha de modificación.

    Args:
        path: Ruta del archivo a crear.
        when: Fecha de modificación a fijar.

    Returns:
        Path: La ruta del archivo creado.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("contenido de prueba", encoding="utf-8")
    timestamp = when.timestamp()
    os.utime(path, (timestamp, timestamp))
    return path


def _create_bundle(base: Path, name: str, when: datetime) -> Path:
    """Crea un bundle de RRSS con assets, igual que los reales.

    Args:
        base: Directorio base del proyecto.
        name: Nombre de la carpeta del bundle (``AAAA_MM_DD_slug``).
        when: Fecha de modificación de los archivos.

    Returns:
        Path: La ruta de la carpeta del bundle.
    """
    bundle = base / DEFAULT_SOCIAL_OUTPUT_DIR / name
    _create_file(bundle / "assets" / "headline_card_x.png", when)
    _create_file(bundle / "manifest.json", when)
    return bundle


def _empty_entry(tmp_path: Path, name: str) -> StaleEntry:
    """Construye una entrada antigua apuntando a una ruta inexistente.

    Args:
        tmp_path: Directorio temporal del test.
        name: Nombre del archivo inexistente.

    Returns:
        StaleEntry: Entrada lista para probar los fallos de borrado.
    """
    return StaleEntry(
        path=tmp_path / name,
        reference=NOW,
        age=timedelta(days=40),
        size_bytes=0,
    )


class TestFindStaleEntries:
    """Detección de artefactos que superan la antigüedad máxima."""

    def test_detects_an_old_report_by_its_name_date(self, tmp_path):
        old = _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_08_01.md", NOW
        )

        entries = find_stale_entries(tmp_path, max_age_days=30, now=NOW)

        assert [entry.path for entry in entries] == [old.resolve()]

    def test_detects_the_companion_json_of_an_old_report(self, tmp_path):
        companion = _create_file(
            tmp_path
            / DEFAULT_REPORTS_DIR
            / "pauta_semanal_2026_08_01_companion.json",
            NOW,
        )

        entries = find_stale_entries(tmp_path, max_age_days=30, now=NOW)

        assert [entry.path for entry in entries] == [companion.resolve()]

    def test_keeps_recent_artifacts(self, tmp_path):
        _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_09_20.md", NOW
        )

        assert find_stale_entries(tmp_path, max_age_days=30, now=NOW) == []

    def test_prefers_the_name_date_over_the_modification_date(self, tmp_path):
        # Un repositorio clonado o copiado deja todos los archivos con fecha de
        # modificación reciente: la fecha del nombre debe mandar.
        old = _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_01_05.md", NOW
        )

        entries = find_stale_entries(tmp_path, max_age_days=30, now=NOW)

        assert [entry.path for entry in entries] == [old.resolve()]

    def test_uses_the_modification_date_for_articles(self, tmp_path):
        # Los artículos no llevan fecha en el nombre (articulo_N_slug.md), así
        # que la única referencia disponible es la fecha de modificación.
        old = _create_file(
            tmp_path / DEFAULT_ARTICLES_DIR / "articulo_1_slug.md",
            NOW - timedelta(days=45),
        )
        _create_file(
            tmp_path / DEFAULT_ARTICLES_DIR / "articulo_2_slug.md",
            NOW - timedelta(days=2),
        )

        entries = find_stale_entries(tmp_path, max_age_days=30, now=NOW)

        assert [entry.path for entry in entries] == [old.resolve()]

    def test_detects_social_bundles_with_their_assets(self, tmp_path):
        bundle = _create_bundle(tmp_path, "2026_07_01_titular", NOW)

        entries = find_stale_entries(tmp_path, max_age_days=30, now=NOW)

        assert [entry.path for entry in entries] == [bundle.resolve()]
        assert entries[0].size_bytes > 0

    def test_covers_every_target_by_default(self, tmp_path):
        report = _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_06_01.md", NOW
        )
        article = _create_file(
            tmp_path / DEFAULT_ARTICLES_DIR / "articulo_1_slug.md",
            NOW - timedelta(days=90),
        )
        bundle = _create_bundle(tmp_path, "2026_06_01_titular", NOW)

        found = {
            entry.path
            for entry in find_stale_entries(tmp_path, max_age_days=30, now=NOW)
        }

        assert found == {report.resolve(), article.resolve(), bundle.resolve()}

    def test_keeps_the_artifacts_inside_the_cutoff(self, tmp_path):
        _create_file(
            tmp_path / DEFAULT_ARTICLES_DIR / "articulo_1_slug.md",
            NOW - timedelta(days=30) + timedelta(seconds=1),
        )

        assert find_stale_entries(tmp_path, max_age_days=30, now=NOW) == []

    def test_detects_the_artifacts_just_past_the_cutoff(self, tmp_path):
        old = _create_file(
            tmp_path / DEFAULT_ARTICLES_DIR / "articulo_1_slug.md",
            NOW - timedelta(days=30, seconds=1),
        )

        entries = find_stale_entries(tmp_path, max_age_days=30, now=NOW)

        assert [entry.path for entry in entries] == [old.resolve()]

    def test_fills_the_reference_age_and_size(self, tmp_path):
        _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_08_01.md", NOW
        )

        entry = find_stale_entries(tmp_path, max_age_days=30, now=NOW)[0]

        assert entry.reference == datetime(2026, 8, 1, tzinfo=timezone.utc)
        assert entry.age.days == 53
        assert entry.size_bytes == len("contenido de prueba")

    def test_orders_from_oldest_to_newest(self, tmp_path):
        newest = _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_08_20.md", NOW
        )
        oldest = _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_06_01.md", NOW
        )

        entries = find_stale_entries(tmp_path, max_age_days=30, now=NOW)

        assert [entry.path for entry in entries] == [
            oldest.resolve(),
            newest.resolve(),
        ]

    def test_ignores_files_outside_the_clean_patterns(self, tmp_path):
        stale = NOW - timedelta(days=90)
        _create_file(tmp_path / DEFAULT_REPORTS_DIR / "notas_sueltas.txt", stale)
        _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "debug" / "articulos_2026_01_01.json",
            stale,
        )
        _create_file(tmp_path / DEFAULT_ARTICLES_DIR / "borrador.md", stale)
        _create_file(tmp_path / "assets" / "logo.png", stale)

        assert find_stale_entries(tmp_path, max_age_days=30, now=NOW) == []

    def test_never_reaches_the_content_cache(self, tmp_path):
        _create_file(tmp_path / "cache" / "enriched_content.json", NOW - timedelta(days=365))

        assert find_stale_entries(tmp_path, max_age_days=1, now=NOW) == []

    def test_ignores_directories_that_do_not_exist(self, tmp_path):
        missing = tmp_path / "proyecto_vacio"

        assert find_stale_entries(missing, max_age_days=30, now=NOW) == []

    def test_filters_by_target(self, tmp_path):
        report = _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_08_01.md", NOW
        )
        _create_file(
            tmp_path / DEFAULT_ARTICLES_DIR / "articulo_1_slug.md",
            NOW - timedelta(days=90),
        )

        entries = find_stale_entries(
            tmp_path, targets=(REPORTS_TARGET,), max_age_days=30, now=NOW
        )

        assert [entry.path for entry in entries] == [report.resolve()]

    def test_filters_by_the_articles_target(self, tmp_path):
        article = _create_file(
            tmp_path / DEFAULT_ARTICLES_DIR / "articulo_1_slug.md",
            NOW - timedelta(days=90),
        )
        _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_08_01.md", NOW
        )

        entries = find_stale_entries(
            tmp_path, targets=(ARTICLES_TARGET,), max_age_days=30, now=NOW
        )

        assert [entry.path for entry in entries] == [article.resolve()]


class TestRemoveEntries:
    """Borrado efectivo de las entradas detectadas."""

    def test_removes_files_and_directories(self, tmp_path):
        report = _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_08_01.md", NOW
        )
        bundle = _create_bundle(tmp_path, "2026_07_01_titular", NOW)
        entries = [
            StaleEntry(report.resolve(), NOW, timedelta(days=40), 1),
            StaleEntry(bundle.resolve(), NOW, timedelta(days=40), 1),
        ]

        removed, failed = remove_entries(entries)

        assert (removed, failed) == (2, 0)
        assert not report.exists()
        assert not bundle.exists()

    def test_counts_missing_paths_as_failures(self, tmp_path):
        assert remove_entries([_empty_entry(tmp_path, "no-existe.md")]) == (0, 1)

    def test_keeps_going_after_a_failure(self, tmp_path):
        report = _create_file(
            tmp_path / DEFAULT_REPORTS_DIR / "pauta_semanal_2026_08_01.md", NOW
        )
        entries = [
            _empty_entry(tmp_path, "no-existe.md"),
            StaleEntry(report.resolve(), NOW, timedelta(days=40), 1),
        ]

        removed, failed = remove_entries(entries)

        assert (removed, failed) == (1, 1)
        assert not report.exists()

    def test_does_nothing_with_an_empty_list(self):
        assert remove_entries([]) == (0, 0)


class TestFormatSize:
    """Formateo legible de tamaños."""

    def test_formats_bytes(self):
        assert format_size(0) == "0 B"
        assert format_size(512) == "512 B"

    def test_formats_kilobytes(self):
        assert format_size(2048) == "2.0 KB"

    def test_formats_megabytes(self):
        assert format_size(5 * 1024 * 1024) == "5.0 MB"
