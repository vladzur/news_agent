"""Interfaz de línea de comandos por subcomandos del agente de contenidos.

Complementa los modos clásicos del punto de entrada (``--feeds``,
``--write-article`` y ``--socialize``) con un conjunto de subcomandos pensados
para el uso diario:

    report   Genera la pauta editorial semanal desde los feeds RSS.
    article  Escribe una nota completa desde una propuesta de la pauta.
    social   Genera el bundle de redes sociales de un artículo.
    all      Encadena los tres pasos anteriores en una sola ejecución.
    clean    Elimina los artefactos generados con más de N días.

Cuando un paso necesita una entrada y no se indica una ruta explícita, el CLI
toma la más reciente del directorio correspondiente (``reportes/`` o
``articulos/``), de modo que el uso diario se reduce a un solo comando.

Uso:
    python -m news_agent report --feeds rss_feeds.json
    python -m news_agent article --number 2
    python -m news_agent social --platforms x,instagram
    python -m news_agent all --number 1
    python -m news_agent clean --days 30 --dry-run
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .article_writer import PautaParseError, parse_pauta_file, write_article
from .cleanup import (
    ALL_TARGETS,
    StaleEntry,
    find_stale_entries,
    format_size,
    remove_entries,
)
from .config import (
    DEFAULT_ARTICLES_DIR,
    DEFAULT_CLEAN_MAX_AGE_DAYS,
    DEFAULT_REPORTS_DIR,
    DEFAULT_SOCIAL_OUTPUT_DIR,
    NUM_PROPOSALS,
)
from .orchestrator import run_pipeline
from .social.platform_specs import ALL_PLATFORMS, parse_platforms

# Nombre del programa tal como lo invoca el usuario.
PROGRAM_NAME = "python -m news_agent"

# Mensaje común al interrumpir la ejecución con Ctrl+C.
CANCELLED_MESSAGE = "\nEjecución cancelada por el usuario."

# Comandos disponibles, en el orden en que se muestran en la ayuda.
COMMANDS: tuple[str, ...] = ("report", "article", "social", "all", "clean")

# Descripción de una línea de cada comando, usada en la ayuda general.
COMMAND_DESCRIPTIONS: dict[str, str] = {
    "report": "Genera la pauta editorial semanal desde los feeds RSS.",
    "article": "Escribe una nota completa desde una propuesta de la pauta.",
    "social": "Genera el bundle de redes sociales de un artículo publicado.",
    "all": "Ejecuta la secuencia completa: pauta, nota y redes sociales.",
    "clean": "Elimina los artefactos generados con más de N días.",
}

# Patrones con que se localizan la pauta y el artículo más recientes.
REPORT_FILE_PATTERN = "pauta_semanal_*.md"
ARTICLE_FILE_PATTERN = "articulo_*.md"

# Ayuda reutilizada por todos los subcomandos.
VERBOSE_HELP = "Activa logging en modo DEBUG para diagnóstico detallado."


class OutputDirectoryError(Exception):
    """Excepción para una ruta de salida inválida o ausente."""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _build_epilog() -> str:
    """Construye el pie de la ayuda general con el listado de comandos.

    Returns:
        str: Bloque de comandos y ejemplos en texto plano.
    """
    lines = ["Comandos:", ""]
    lines.extend(
        f"  {name:<8} {COMMAND_DESCRIPTIONS[name]}" for name in COMMANDS
    )
    lines.extend(
        [
            "",
            "Usa '-h' después de un comando para ver sus opciones.",
            "",
            "Ejemplos:",
            f"  {PROGRAM_NAME} report --feeds rss_feeds.json",
            f"  {PROGRAM_NAME} article --number 2",
            f"  {PROGRAM_NAME} social --platforms x,instagram",
            f"  {PROGRAM_NAME} all --number 1",
            f"  {PROGRAM_NAME} clean --days 30 --dry-run",
        ]
    )
    return "\n".join(lines)


def _add_social_platform_options(parser: argparse.ArgumentParser) -> None:
    """Agrega las opciones del subsistema de RRSS a un subcomando.

    Args:
        parser: Subparser que recibe las opciones.
    """
    parser.add_argument(
        "--platforms",
        type=str,
        default=None,
        metavar="LISTA",
        help="Plataformas a preparar, separadas por comas "
        f"({', '.join(ALL_PLATFORMS)}). Por defecto, todas.",
    )
    parser.add_argument(
        "--social-config",
        type=str,
        default=None,
        metavar="RUTA",
        help="Ruta al JSON de configuración de marca y plantillas "
        "(por defecto: social_config.json).",
    )
    parser.add_argument(
        "--skip-banners",
        action="store_true",
        help="Omite el renderizado de banners con Pillow.",
    )
    parser.add_argument(
        "--skip-prompts",
        action="store_true",
        help="Omite la generación de prompts visuales en inglés.",
    )


def _add_report_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    """Registra el subcomando ``report`` (generar pauta)."""
    parser = subparsers.add_parser(
        "report",
        help=COMMAND_DESCRIPTIONS["report"],
        description=(
            "Obtiene las noticias de los feeds configurados y genera la pauta "
            "editorial semanal con las propuestas del modelo."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--feeds",
        type=str,
        default=None,
        metavar="RUTA",
        help="Ruta al JSON de configuración de feeds RSS "
        "(por defecto: rss_feeds.json).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_REPORTS_DIR,
        metavar="DIR",
        help=f"Directorio donde guardar la pauta "
        f"(por defecto: {DEFAULT_REPORTS_DIR}/).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Guarda además un JSON intermedio con los artículos procesados.",
    )
    parser.add_argument("--verbose", action="store_true", help=VERBOSE_HELP)
    parser.set_defaults(handler=_handle_report)


def _add_article_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    """Registra el subcomando ``article`` (escribir nota)."""
    parser = subparsers.add_parser(
        "article",
        help=COMMAND_DESCRIPTIONS["article"],
        description=(
            "Desarrolla una propuesta de la pauta como nota completa, con el "
            "material de origen del archivo companion."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pauta",
        type=str,
        default=None,
        metavar="RUTA",
        help="Ruta a la pauta semanal. Por defecto, la más reciente de "
        f"{DEFAULT_REPORTS_DIR}/.",
    )
    parser.add_argument(
        "-n",
        "--number",
        type=int,
        default=None,
        choices=list(range(1, NUM_PROPOSALS + 1)),
        metavar="N",
        help=f"Número de propuesta a desarrollar (1 a {NUM_PROPOSALS}). "
        "Si se omite, se pregunta por la terminal.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_ARTICLES_DIR,
        metavar="DIR",
        help=f"Directorio donde guardar la nota "
        f"(por defecto: {DEFAULT_ARTICLES_DIR}/).",
    )
    parser.add_argument("--verbose", action="store_true", help=VERBOSE_HELP)
    parser.set_defaults(handler=_handle_article)


def _add_social_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    """Registra el subcomando ``social`` (repurposing de RRSS)."""
    parser = subparsers.add_parser(
        "social",
        help=COMMAND_DESCRIPTIONS["social"],
        description=(
            "Genera copys, prompts visuales y banners para X, Facebook e "
            "Instagram a partir de un artículo publicado."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--article",
        type=str,
        default=None,
        metavar="RUTA",
        help="Ruta al artículo Markdown. Por defecto, el más reciente de "
        f"{DEFAULT_ARTICLES_DIR}/.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_SOCIAL_OUTPUT_DIR,
        metavar="DIR",
        help=f"Directorio base de los bundles "
        f"(por defecto: {DEFAULT_SOCIAL_OUTPUT_DIR}/).",
    )
    _add_social_platform_options(parser)
    parser.add_argument("--verbose", action="store_true", help=VERBOSE_HELP)
    parser.set_defaults(handler=_handle_social)


def _add_all_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    """Registra el subcomando ``all`` (secuencia completa)."""
    parser = subparsers.add_parser(
        "all",
        help=COMMAND_DESCRIPTIONS["all"],
        description=(
            "Ejecuta la secuencia completa: genera la pauta, escribe la nota "
            "elegida y produce el bundle de redes sociales, todo de una vez."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--feeds",
        type=str,
        default=None,
        metavar="RUTA",
        help="Ruta al JSON de configuración de feeds RSS "
        "(por defecto: rss_feeds.json).",
    )
    parser.add_argument(
        "--base",
        type=str,
        default=".",
        metavar="DIR",
        help="Directorio base del proyecto: las salidas van a "
        f"<DIR>/{DEFAULT_REPORTS_DIR}, <DIR>/{DEFAULT_ARTICLES_DIR} y "
        f"<DIR>/{DEFAULT_SOCIAL_OUTPUT_DIR} (por defecto: .).",
    )
    parser.add_argument(
        "-n",
        "--number",
        type=int,
        default=None,
        choices=list(range(1, NUM_PROPOSALS + 1)),
        metavar="N",
        help=f"Número de propuesta a desarrollar (1 a {NUM_PROPOSALS}). "
        "Si se omite, se pregunta por la terminal.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Guarda además un JSON intermedio con los artículos procesados.",
    )
    _add_social_platform_options(parser)
    parser.add_argument("--verbose", action="store_true", help=VERBOSE_HELP)
    parser.set_defaults(handler=_handle_all)


def _add_clean_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    """Registra el subcomando ``clean`` (limpieza de artefactos)."""
    parser = subparsers.add_parser(
        "clean",
        help=COMMAND_DESCRIPTIONS["clean"],
        description=(
            "Elimina pautas, artículos y bundles de redes sociales que superen "
            "una antigüedad máxima. Nunca toca la caché de contenido ni los "
            "assets de la marca."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base",
        type=str,
        default=".",
        metavar="DIR",
        help="Directorio base del proyecto donde buscar "
        f"{DEFAULT_REPORTS_DIR}/, {DEFAULT_ARTICLES_DIR}/ y "
        f"{DEFAULT_SOCIAL_OUTPUT_DIR}/ (por defecto: .).",
    )
    parser.add_argument(
        "--target",
        choices=("all", *ALL_TARGETS),
        default="all",
        help="Grupo de artefactos a limpiar: all, reports, articles o social "
        "(por defecto: all).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_CLEAN_MAX_AGE_DAYS,
        metavar="N",
        help="Antigüedad mínima, en días, para eliminar "
        f"(por defecto: {DEFAULT_CLEAN_MAX_AGE_DAYS}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué se eliminaría sin borrar nada.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Omite la confirmación interactiva.",
    )
    parser.add_argument("--verbose", action="store_true", help=VERBOSE_HELP)
    parser.set_defaults(handler=_handle_clean)


def build_cli_parser() -> argparse.ArgumentParser:
    """Construye el parser del CLI por subcomandos.

    Returns:
        argparse.ArgumentParser: Parser con los comandos report, article,
        social, all y clean.
    """
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description="Agente Inteligente de Contenidos - La Chispa Sur",
        epilog=_build_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMANDO",
        title="comandos",
        required=True,
    )

    _add_report_parser(subparsers)
    _add_article_parser(subparsers)
    _add_social_parser(subparsers)
    _add_all_parser(subparsers)
    _add_clean_parser(subparsers)

    return parser


# ---------------------------------------------------------------------------
# Localización de entradas recientes
# ---------------------------------------------------------------------------


def find_latest_report(
    directory: str | Path = DEFAULT_REPORTS_DIR,
) -> Path | None:
    """Localiza la pauta más reciente de un directorio.

    El nombre incluye la fecha (``pauta_semanal_AAAA_MM_DD.md``), así que el
    orden alfabético coincide con el cronológico.

    Args:
        directory: Directorio donde buscar.

    Returns:
        Path | None: Ruta de la pauta más reciente, o None si no hay ninguna.
    """
    base = Path(directory)
    if not base.is_dir():
        return None

    candidates = [
        path for path in base.glob(REPORT_FILE_PATTERN) if path.is_file()
    ]
    if not candidates:
        return None

    return max(candidates, key=lambda path: path.name)


def find_latest_article(
    directory: str | Path = DEFAULT_ARTICLES_DIR,
) -> Path | None:
    """Localiza el artículo más reciente de un directorio.

    Los artículos no llevan fecha en el nombre, así que se usa la fecha de
    modificación como criterio de orden.

    Args:
        directory: Directorio donde buscar.

    Returns:
        Path | None: Ruta del artículo más reciente, o None si no hay ninguno.
    """
    base = Path(directory)
    if not base.is_dir():
        return None

    candidates = [
        path for path in base.glob(ARTICLE_FILE_PATTERN) if path.is_file()
    ]
    if not candidates:
        return None

    return max(candidates, key=lambda path: path.stat().st_mtime)


def resolve_pauta(pauta: str | None) -> Path:
    """Resuelve la pauta a usar, tomando la más reciente si no se indicó una.

    Args:
        pauta: Ruta explícita a la pauta, o None.

    Returns:
        Path: Ruta de la pauta elegida.

    Raises:
        SystemExit: Si no se indicó una ruta y no hay pautas en el directorio.
    """
    if pauta:
        return Path(pauta)

    latest = find_latest_report()
    if latest is None:
        print(
            f"Error: no se encontró ninguna pauta en '{DEFAULT_REPORTS_DIR}/'. "
            "Genera una con 'report' o indica la ruta con --pauta.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"📄 Usando la pauta más reciente: {latest}")
    return latest


def resolve_article(article: str | None) -> Path:
    """Resuelve el artículo a usar, tomando el más reciente si no se indicó uno.

    Args:
        article: Ruta explícita al artículo, o None.

    Returns:
        Path: Ruta del artículo elegido.

    Raises:
        SystemExit: Si no se indicó una ruta y no hay artículos en el directorio.
    """
    if article:
        return Path(article)

    latest = find_latest_article()
    if latest is None:
        print(
            f"Error: no se encontró ningún artículo en "
            f"'{DEFAULT_ARTICLES_DIR}/'. Escribe uno con 'article' o indica "
            "la ruta con --article.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"📄 Usando el artículo más reciente: {latest}")
    return latest


# ---------------------------------------------------------------------------
# Selección de la propuesta
# ---------------------------------------------------------------------------


def prompt_for_proposal(
    proposals: Sequence[dict[str, Any]],
    ask: Callable[[str], str] | None = None,
) -> int:
    """Pregunta por la terminal qué propuesta de la pauta desarrollar.

    Args:
        proposals: Propuestas parseadas, con las claves ``number`` y ``title``.
        ask: Función de lectura de una línea, inyectable en los tests. Si es
            None, se usa la entrada estándar.

    Returns:
        int: Número de la propuesta elegida.

    Raises:
        KeyboardInterrupt: Si el usuario cancela con 'q' o con Ctrl+C.
        EOFError: Si la entrada estándar se agota antes de una respuesta válida.
    """
    reader = ask if ask is not None else input

    print("\n¿Qué propuesta quieres desarrollar?")
    for proposal in proposals:
        print(f"  {proposal['number']}. {proposal['title']}")

    valid = {proposal["number"] for proposal in proposals}
    while True:
        answer = reader(
            f"Elige un número del 1 al {NUM_PROPOSALS} "
            "o 'q' para cancelar: "
        ).strip()

        if answer.lower() in {"q", "quit", "salir"}:
            raise KeyboardInterrupt

        if answer.isdigit() and int(answer) in valid:
            return int(answer)

        print("Opción inválida. Intenta nuevamente.")


def resolve_article_number(number: int | None, pauta_path: Path) -> int:
    """Determina qué propuesta desarrollar.

    Si no se indicó un número por línea de comandos y la entrada no es una
    terminal interactiva, se falla con un error de uso en lugar de esperar
    una respuesta que nunca llegará (por ejemplo, en un cron).

    Args:
        number: Número indicado con --number, o None.
        pauta_path: Ruta de la pauta desde la cual elegir la propuesta.

    Returns:
        int: Número de la propuesta elegida.

    Raises:
        SystemExit: Si falta el número y no hay terminal interactiva, o si la
        pauta no se puede parsear.
    """
    if number is not None:
        return number

    if not sys.stdin.isatty():
        print(
            "Error: la selección interactiva necesita una terminal. "
            "Indica la propuesta con --number N.",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        proposals = parse_pauta_file(pauta_path)
    except PautaParseError as exc:
        print(f"Error al leer la pauta: {exc}", file=sys.stderr)
        sys.exit(1)

    return prompt_for_proposal(proposals)


# ---------------------------------------------------------------------------
# Helpers de ejecución
# ---------------------------------------------------------------------------


def resolve_output_dir(
    requested: str | Path | None,
    default: str | None = None,
) -> Path:
    """Resuelve y prepara el directorio de salida de un flujo.

    Nunca devuelve el directorio actual. Cuando no se pide una ruta se usa el
    directorio por defecto del flujo y, cuando la ruta pedida apunta al
    directorio actual, se rechaza. Así ninguna ejecución ensucia la raíz del
    proyecto con pautas, notas o bundles sueltos.

    Args:
        requested: Ruta pedida por el usuario, o None.
        default: Directorio a usar cuando no se pidió una ruta.

    Returns:
        Path: Directorio, ya creado, listo para escribir.

    Raises:
        OutputDirectoryError: Si no hay ruta ni directorio por defecto, o si
            la ruta resuelta es el directorio actual.
    """
    if requested:
        target = Path(requested)
    elif default:
        target = Path(default)
    else:
        raise OutputDirectoryError(
            "Falta el directorio de salida y no hay uno por defecto."
        )

    if target.resolve() == Path.cwd().resolve():
        raise OutputDirectoryError(
            f"El directorio de salida no puede ser el directorio actual "
            f"({target}). Usa una carpeta propia, por ejemplo "
            f"'{default or DEFAULT_REPORTS_DIR}/'."
        )

    target.mkdir(parents=True, exist_ok=True)
    return target


def _display_path(path: Path | str) -> str:
    """Devuelve la ruta relativa al directorio actual cuando es posible.

    Args:
        path: Ruta a mostrar.

    Returns:
        str: Ruta corta para el usuario.
    """
    candidate = Path(path)
    try:
        return str(candidate.relative_to(Path.cwd()))
    except ValueError:
        return str(candidate)


def print_report_summary(result: dict[str, Any]) -> None:
    """Muestra el resumen de la pauta generada.

    Args:
        result: Resumen devuelto por ``run_pipeline``.
    """
    print("\n✅ Reporte generado exitosamente:")
    print(f"   📄 {result['report_path']}")
    print(
        f"   📊 {result['item_count']} artículos analizados de "
        f"{result['feed_count']} fuentes."
    )
    if result.get("debug_path"):
        print(f"   🔍 Archivo de depuración: {result['debug_path']}")
    if result.get("companion_path"):
        print(f"   📎 Fuentes acompañantes: {result['companion_path']}")


def print_article_summary(result: dict[str, Any]) -> None:
    """Muestra el resumen de la nota escrita.

    Args:
        result: Resumen devuelto por ``write_article``.
    """
    print("\n✅ Artículo escrito exitosamente:")
    print(f"   📄 {result['article_path']}")
    print(f"   📝 \"{result['title']}\"")


def print_social_summary(result: dict[str, Any]) -> None:
    """Muestra el resumen del bundle de redes sociales.

    Args:
        result: Resumen devuelto por ``run_socialize``.
    """
    print("\n✅ Bundle de RRSS generado exitosamente:")
    print(f"   📁 {result['bundle_dir']}")
    print(f"   📝 \"{result['title']}\"")
    print(f"   📊 Plataformas: {', '.join(result['platforms'])}")
    print(f"   🖼️  Banners generados: {result['banner_count']}")
    if result["banner_failed"]:
        print(f"   ⚠️  Banners fallidos: {result['banner_failed']}")
    if result["prompts_path"]:
        print(f"   🎨 Prompts visuales: {result['prompts_path']}")
    print(f"   🗂️  Copys: {result['copy_path']}")
    print(f"   🧾 Manifiesto: {result['manifest_path']}")


def _write_article_step(
    pauta_path: Path,
    number: int,
    output_dir: Path,
    verbose: bool,
) -> dict[str, Any]:
    """Ejecuta la escritura de la nota traduciendo sus errores a mensajes.

    Args:
        pauta_path: Ruta de la pauta.
        number: Número de propuesta a desarrollar.
        output_dir: Directorio donde guardar la nota.
        verbose: Si es True, activa logging DEBUG.

    Returns:
        dict[str, Any]: Resumen devuelto por ``write_article``.

    Raises:
        SystemExit: Si la pauta es inválida o el número no existe.
    """
    try:
        return write_article(
            pauta_path=pauta_path,
            article_number=number,
            output_dir=output_dir,
            verbose=verbose,
        )
    except PautaParseError as exc:
        print(f"Error al leer la pauta: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def run_socialize_step(
    article_path: str | Path,
    output_dir: str | Path,
    platforms: str | None,
    config_path: str | None,
    verbose: bool,
    skip_banners: bool,
    skip_prompts: bool,
) -> dict[str, Any]:
    """Ejecuta el orquestador de RRSS sobre un artículo.

    La importación del subsistema es diferida a propósito: depende de Pillow y
    el resto del CLI debe seguir funcionando si no está instalado.

    Args:
        article_path: Ruta al artículo Markdown.
        output_dir: Directorio base de los bundles.
        platforms: Plataformas pedidas separadas por comas, o None para todas.
        config_path: Ruta a la configuración de marca, o None para la default.
        verbose: Si es True, activa logging DEBUG.
        skip_banners: Si es True, omite el renderizado de banners.
        skip_prompts: Si es True, omite los prompts visuales.

    Returns:
        dict[str, Any]: Resumen devuelto por ``run_socialize``.

    Raises:
        SystemExit: Si falta Pillow, la plataforma es desconocida o el
        artículo no se puede procesar.
    """
    try:
        from .social.orchestrator import run_socialize
    except ImportError as exc:
        print(
            "Error: no se pudo cargar el subsistema de RRSS. Verifica que "
            f"Pillow esté instalado (pip install -e .). Detalle: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        selected_platforms = parse_platforms(platforms)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        return run_socialize(
            article_path=article_path,
            output_dir=output_dir,
            config_path=config_path,
            platforms=selected_platforms,
            verbose=verbose,
            skip_banners=skip_banners,
            skip_prompts=skip_prompts,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------------------
# Handlers de los subcomandos
# ---------------------------------------------------------------------------


def _handle_report(args: argparse.Namespace) -> None:
    """Ejecuta el subcomando ``report``.

    Args:
        args: Argumentos ya parseados.
    """
    output_dir = resolve_output_dir(args.output, DEFAULT_REPORTS_DIR)
    result = run_pipeline(
        feeds_path=args.feeds,
        output_dir=output_dir,
        verbose=args.verbose,
        save_intermediate_data=args.debug,
    )
    print_report_summary(result)


def _handle_article(args: argparse.Namespace) -> None:
    """Ejecuta el subcomando ``article``.

    Args:
        args: Argumentos ya parseados.
    """
    pauta_path = resolve_pauta(args.pauta)
    number = resolve_article_number(args.number, pauta_path)
    output_dir = resolve_output_dir(args.output, DEFAULT_ARTICLES_DIR)

    result = _write_article_step(pauta_path, number, output_dir, args.verbose)
    print_article_summary(result)


def _handle_social(args: argparse.Namespace) -> None:
    """Ejecuta el subcomando ``social``.

    Args:
        args: Argumentos ya parseados.
    """
    article_path = resolve_article(args.article)
    output_dir = resolve_output_dir(args.output, DEFAULT_SOCIAL_OUTPUT_DIR)

    result = run_socialize_step(
        article_path=article_path,
        output_dir=output_dir,
        platforms=args.platforms,
        config_path=args.social_config,
        verbose=args.verbose,
        skip_banners=args.skip_banners,
        skip_prompts=args.skip_prompts,
    )
    print_social_summary(result)


def _handle_all(args: argparse.Namespace) -> None:
    """Ejecuta el subcomando ``all`` (pauta, nota y redes sociales).

    Args:
        args: Argumentos ya parseados.
    """
    base = Path(args.base)

    print("\n▶️  Paso 1/3: generando la pauta editorial...")
    reports_dir = resolve_output_dir(base / DEFAULT_REPORTS_DIR)
    pipeline_result = run_pipeline(
        feeds_path=args.feeds,
        output_dir=reports_dir,
        verbose=args.verbose,
        save_intermediate_data=args.debug,
    )
    print_report_summary(pipeline_result)

    pauta_path = Path(pipeline_result["report_path"])
    number = resolve_article_number(args.number, pauta_path)

    print("\n▶️  Paso 2/3: escribiendo la nota...")
    articles_dir = resolve_output_dir(base / DEFAULT_ARTICLES_DIR)
    article_result = _write_article_step(
        pauta_path, number, articles_dir, args.verbose
    )
    print_article_summary(article_result)

    print("\n▶️  Paso 3/3: generando las piezas para redes sociales...")
    social_dir = resolve_output_dir(base / DEFAULT_SOCIAL_OUTPUT_DIR)
    social_result = run_socialize_step(
        article_path=article_result["article_path"],
        output_dir=social_dir,
        platforms=args.platforms,
        config_path=args.social_config,
        verbose=args.verbose,
        skip_banners=args.skip_banners,
        skip_prompts=args.skip_prompts,
    )
    print_social_summary(social_result)

    print("\n✅ Secuencia completa finalizada.")


def _confirm(question: str, ask: Callable[[str], str] | None = None) -> bool:
    """Pide confirmación por consola.

    Args:
        question: Pregunta a mostrar.
        ask: Función de lectura de una línea, inyectable en los tests. Si es
            None, se usa la entrada estándar.

    Returns:
        bool: True si el usuario responde afirmativamente.
    """
    reader = ask if ask is not None else input
    answer = reader(f"{question} [s/N]: ").strip().lower()
    return answer in {"s", "si", "sí", "y", "yes"}


def _print_stale_entries(
    entries: Sequence[StaleEntry],
    max_age_days: int,
) -> None:
    """Lista los artefactos que se van a eliminar.

    Args:
        entries: Entradas detectadas como antiguas.
        max_age_days: Antigüedad mínima usada en la detección.
    """
    total_bytes = sum(entry.size_bytes for entry in entries)
    print(
        f"\n🗑️  {len(entries)} artefacto(s) con más de {max_age_days} días "
        f"({format_size(total_bytes)}):"
    )
    for entry in entries:
        print(
            f"   • {_display_path(entry.path)}  "
            f"({entry.age.days} días, {format_size(entry.size_bytes)})"
        )
    print(
        "\n   Nota: la caché de contenido y los assets de la marca nunca "
        "se eliminan."
    )


def _handle_clean(args: argparse.Namespace) -> None:
    """Ejecuta el subcomando ``clean``.

    Args:
        args: Argumentos ya parseados.
    """
    if args.days < 1:
        print(
            "Error: --days debe ser un número entero mayor o igual a 1.",
            file=sys.stderr,
        )
        sys.exit(2)

    targets = ALL_TARGETS if args.target == "all" else (args.target,)
    entries = find_stale_entries(
        args.base,
        targets=targets,
        max_age_days=args.days,
    )

    if not entries:
        print(f"No hay artefactos con más de {args.days} días en '{args.base}'.")
        return

    _print_stale_entries(entries, args.days)

    if args.dry_run:
        print("\n🔍 Modo simulación: no se eliminó ningún archivo.")
        return

    if not args.yes and not _confirm(
        f"\n¿Eliminar estos {len(entries)} artefactos?"
    ):
        print("Limpieza cancelada.")
        return

    removed, failed = remove_entries(entries)
    print(f"\n✅ Artefactos eliminados: {removed}.")
    if failed:
        print(f"⚠️  No se pudieron eliminar: {failed}.")


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def run(argv: Sequence[str]) -> None:
    """Ejecuta el subcomando indicado en los argumentos.

    Args:
        argv: Argumentos de la línea de comandos, sin el nombre del programa.

    Raises:
        SystemExit: Con el código del error cuando la ejecución falla.
    """
    parser = build_cli_parser()
    args = parser.parse_args(list(argv))

    try:
        args.handler(args)
    except OutputDirectoryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print(CANCELLED_MESSAGE, file=sys.stderr)
        sys.exit(130)
