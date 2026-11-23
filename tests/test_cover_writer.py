"""Tests de la escritura del bundle de portadas."""

import json
from datetime import datetime, timezone

from news_agent.cover.writer import (
    METADATA_FILE_NAME,
    build_bundle_dir,
    metadata_path,
    read_metadata,
    save_metadata,
)

WHEN = datetime(2026, 11, 23, tzinfo=timezone.utc)


class TestBundleDir:
    """Nombre y creación del directorio del bundle."""

    def test_combines_the_date_and_the_slug(self, tmp_path):
        bundle = build_bundle_dir(tmp_path / "portadas", "cierre-escuela", WHEN)

        assert bundle.name == "2026_11_23_cierre-escuela"
        assert bundle.is_dir()

    def test_uses_a_fallback_slug(self, tmp_path):
        bundle = build_bundle_dir(tmp_path / "portadas", "", WHEN)

        assert bundle.name.endswith("sin-titulo")

    def test_creates_the_base_directory(self, tmp_path):
        base = tmp_path / "nueva" / "portadas"

        build_bundle_dir(base, "titular", WHEN)

        assert base.is_dir()


class TestMetadata:
    """Manifiesto del bundle."""

    def test_writes_a_readable_json(self, tmp_path):
        bundle = tmp_path / "portadas" / "2026_11_23_titular"
        bundle.mkdir(parents=True)
        payload = {"title": "Titular", "category": "Nacional"}

        path = save_metadata(payload, bundle)

        assert path == metadata_path(bundle)
        assert path.name == METADATA_FILE_NAME
        assert json.loads(path.read_text(encoding="utf-8")) == payload

    def test_reads_the_manifest(self, tmp_path):
        bundle = tmp_path / "portadas" / "2026_11_23_titular"
        bundle.mkdir(parents=True)
        save_metadata({"title": "Titular"}, bundle)

        assert read_metadata(bundle) == {"title": "Titular"}

    def test_returns_none_when_the_manifest_is_missing(self, tmp_path):
        assert read_metadata(tmp_path / "sin-manifiesto") is None

    def test_returns_none_when_the_manifest_is_corrupt(self, tmp_path):
        bundle = tmp_path / "portadas" / "2026_11_23_titular"
        bundle.mkdir(parents=True)
        metadata_path(bundle).write_text("{no es json", encoding="utf-8")

        assert read_metadata(bundle) is None

    def test_returns_none_when_the_manifest_is_not_an_object(self, tmp_path):
        bundle = tmp_path / "portadas" / "2026_11_23_titular"
        bundle.mkdir(parents=True)
        metadata_path(bundle).write_text("[1, 2]", encoding="utf-8")

        assert read_metadata(bundle) is None
