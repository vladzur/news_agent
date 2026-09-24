"""Limpieza de los artefactos antiguos generados por el agente.

El subcomando ``clean`` del CLI apoya su lógica en este módulo: detecta pautas,
artículos y bundles de redes sociales cuya antigüedad supera un máximo de días
y los elimina.

La fecha de referencia de cada entrada se toma del nombre cuando la convención
la incluye (``pauta_semanal_AAAA_MM_DD.md`` y ``social/AAAA_MM_DD_slug/``) y,
cuando no (``articulo_N_slug.md``), de la fecha de modificación del archivo.
La fecha del nombre es más fiable que la de modificación: al clonar o copiar el
repositorio, todos los archivos quedan con la fecha de la copia.

Solo se consideran los patrones declarados en ``CLEAN_PATTERNS``: la caché de
contenido (``cache/``) y los recursos de la marca (``assets/``) quedan siempre
fuera del alcance del comando.
"""

import logging
import re
import shutil
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import (
    DEFAULT_ARTICLES_DIR,
    DEFAULT_REPORTS_DIR,
    DEFAULT_SOCIAL_OUTPUT_DIR,
)

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# Nombre de los grupos de artefactos que puede limpiar el comando.
REPORTS_TARGET = "reports"
ARTICLES_TARGET = "articles"
SOCIAL_TARGET = "social"

# Directorio de cada grupo, relativo al directorio base del proyecto.
TARGET_DIRECTORIES: dict[str, str] = {
    REPORTS_TARGET: DEFAULT_REPORTS_DIR,
    ARTICLES_TARGET: DEFAULT_ARTICLES_DIR,
    SOCIAL_TARGET: DEFAULT_SOCIAL_OUTPUT_DIR,
}

# Patrones (glob) de los artefactos de cada grupo. Todo lo que no coincida con
# estos patrones se respeta, aunque viva en el mismo directorio.
CLEAN_PATTERNS: dict[str, tuple[str, ...]] = {
    REPORTS_TARGET: (
        "pauta_semanal_*.md",
        "pauta_semanal_*_companion.json",
    ),
    ARTICLES_TARGET: ("articulo_*.md",),
    SOCIAL_TARGET: ("[0-9][0-9][0-9][0-9]_[0-9][0-9]_[0-9][0-9]_*",),
}

# Grupos disponibles, en el orden en que se informan al usuario.
ALL_TARGETS: tuple[str, ...] = (
    REPORTS_TARGET,
    ARTICLES_TARGET,
    SOCIAL_TARGET,
)

# Fecha (AAAA_MM_DD) dentro del nombre de un artefacto. Se busca en cualquier
# posición porque la convención la sitúa en medio en las pautas
# (``pauta_semanal_AAAA_MM_DD.md``) y al inicio en los bundles
# (``AAAA_MM_DD_slug/``).
_DATE_IN_NAME_PATTERN = re.compile(r"(?<!\d)(\d{4})_(\d{2})_(\d{2})(?!\d)")

# Unidades para el formateo legible de tamaños.
_SIZE_UNITS: tuple[str, ...] = ("B", "KB", "MB", "GB", "TB")


@dataclass(frozen=True)
class StaleEntry:
    """Artefacto detectado como antiguo y candidato a eliminación.

    Attributes:
        path: Ruta absoluta de la entrada.
        reference: Fecha usada para medir la antigüedad.
        age: Antigüedad calculada al momento de la detección.
        size_bytes: Tamaño total en bytes (suma recursiva si es un directorio).
    """

    path: Path
    reference: datetime
    age: timedelta
    size_bytes: int


def _parse_name_date(name: str) -> datetime | None:
    """Extrae la fecha ``AAAA_MM_DD`` de un nombre de artefacto.

    La fecha se busca en cualquier posición del nombre, porque la convención
    la sitúa en medio en las pautas (``pauta_semanal_AAAA_MM_DD.md``) y al
    inicio en los bundles (``AAAA_MM_DD_slug``).

    Args:
        name: Nombre del archivo o directorio.

    Returns:
        datetime | None: Fecha en UTC, o None si el nombre no incluye una
        fecha válida.
    """
    match = _DATE_IN_NAME_PATTERN.search(name)
    if match is None:
        return None

    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            tzinfo=timezone.utc,
        )
    except ValueError:
        # Fecha imposible (mes 13, día 32...): se ignora el nombre.
        return None


def _reference_date(path: Path) -> datetime:
    """Obtiene la fecha de referencia de una entrada.

    Args:
        path: Entrada a inspeccionar.

    Returns:
        datetime: Fecha codificada en el nombre o, si no la trae, la fecha de
        modificación.
    """
    parsed = _parse_name_date(path.name)
    if parsed is not None:
        return parsed
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _directory_size(path: Path) -> int:
    """Suma el tamaño de todos los archivos de un directorio.

    Args:
        path: Directorio a medir.

    Returns:
        int: Tamaño total en bytes, ignorando los archivos ilegibles.
    """
    total = 0
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        try:
            total += child.stat().st_size
        except OSError:
            # Un archivo que desaparece a mitad del recorrido no es un error
            # de la limpieza: se omite del total.
            continue
    return total


def _entry_size(path: Path) -> int:
    """Calcula el tamaño de una entrada (archivo o directorio).

    Args:
        path: Entrada a medir.

    Returns:
        int: Tamaño en bytes, o 0 si no se puede leer.
    """
    try:
        if path.is_dir():
            return _directory_size(path)
        return path.stat().st_size
    except OSError:
        return 0


def format_size(num_bytes: int) -> str:
    """Formatea un tamaño en bytes de forma legible.

    Args:
        num_bytes: Cantidad de bytes.

    Returns:
        str: Tamaño con su unidad (por ejemplo ``"1.5 MB"``).
    """
    size = float(num_bytes)
    unit = _SIZE_UNITS[0]
    for candidate in _SIZE_UNITS:
        unit = candidate
        if size < 1024:
            break
        size /= 1024

    if unit == _SIZE_UNITS[0]:
        return f"{size:.0f} {unit}"
    return f"{size:.1f} {unit}"


def _iter_target_paths(
    directory: Path,
    patterns: Sequence[str],
) -> Iterator[Path]:
    """Recorre los artefactos de un grupo que coinciden con sus patrones.

    Args:
        directory: Directorio del grupo (por ejemplo ``reportes/``).
        patterns: Patrones glob de los artefactos del grupo.

    Yields:
        Path: Ruta de cada artefacto encontrado.
    """
    for pattern in patterns:
        yield from sorted(directory.glob(pattern))


def _build_stale_entry(
    path: Path,
    moment: datetime,
    cutoff: timedelta,
) -> StaleEntry | None:
    """Construye la entrada antigua de una ruta, si la supera el corte.

    Args:
        path: Artefacto a evaluar.
        moment: Momento de referencia para medir la antigüedad.
        cutoff: Antigüedad máxima admitida.

    Returns:
        StaleEntry | None: La entrada si es más antigua que el corte, o None
        si todavía está vigente o no se puede fechar.
    """
    try:
        reference = _reference_date(path)
    except OSError as exc:
        logger.debug("No se pudo fechar %s: %s", path, exc)
        return None

    age = moment - reference
    if age <= cutoff:
        return None

    return StaleEntry(
        path=path.resolve(),
        reference=reference,
        age=age,
        size_bytes=_entry_size(path),
    )


def find_stale_entries(
    base_dir: str | Path,
    targets: Sequence[str] | None = None,
    max_age_days: int = 0,
    now: datetime | None = None,
) -> list[StaleEntry]:
    """Detecta los artefactos más antiguos que la antigüedad máxima.

    Args:
        base_dir: Directorio base del proyecto, que contiene ``reportes/``,
            ``articulos/`` y ``social/``.
        targets: Grupos a revisar (ver ``ALL_TARGETS``). Por defecto, todos.
        max_age_days: Antigüedad máxima en días; se elimina lo que la supere.
        now: Momento de referencia. Por defecto, el actual en UTC.

    Returns:
        list[StaleEntry]: Entradas antiguas, ordenadas de la más vieja a la
        más reciente.
    """
    moment = now or datetime.now(timezone.utc)
    cutoff = timedelta(days=max_age_days)
    base = Path(base_dir)

    entries: list[StaleEntry] = []
    seen: set[Path] = set()

    for target in targets or ALL_TARGETS:
        directory = base / TARGET_DIRECTORIES[target]
        if not directory.is_dir():
            continue

        for path in _iter_target_paths(directory, CLEAN_PATTERNS[target]):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)

            entry = _build_stale_entry(path, moment, cutoff)
            if entry is not None:
                entries.append(entry)

    entries.sort(key=lambda entry: (entry.reference, str(entry.path)))
    return entries


def remove_entries(entries: Sequence[StaleEntry]) -> tuple[int, int]:
    """Elimina las entradas indicadas.

    Un fallo individual no interrumpe el resto: se registra en el log y se
    contabiliza como fallido.

    Args:
        entries: Entradas a eliminar.

    Returns:
        tuple[int, int]: Cantidad de entradas eliminadas y cantidad fallida.
    """
    removed = 0
    failed = 0

    for entry in entries:
        try:
            if entry.path.is_dir() and not entry.path.is_symlink():
                shutil.rmtree(entry.path)
            else:
                entry.path.unlink()
        except OSError as exc:
            logger.warning("No se pudo eliminar %s: %s", entry.path, exc)
            failed += 1
        else:
            logger.info("Eliminado: %s", entry.path)
            removed += 1

    return removed, failed
