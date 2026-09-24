"""Punto de entrada del agente: python -m news_agent.

Ofrece dos interfaces sobre el mismo motor:

1. **CLI simplificado por subcomandos** (recomendado para el uso diario):
     report   Genera la pauta editorial semanal.
     article  Escribe una nota completa desde una propuesta de la pauta.
     social   Genera el bundle de redes sociales de un artículo.
     all      Encadena los tres pasos anteriores en una sola ejecución.
     clean    Elimina los artefactos generados con más de N días.

2. **Modos clásicos por banderas**, que se mantienen por compatibilidad con
   scripts y cron.

Uso con subcomandos:
    python -m news_agent report --feeds rss_feeds.json
    python -m news_agent article --number 2
    python -m news_agent social --platforms x,instagram
    python -m news_agent all --number 1
    python -m news_agent clean --days 30 --dry-run

Uso clásico:
    # Generar pauta semanal
    python -m news_agent --feeds rss_feeds.json --output ./reportes

    # Escribir artículo desde una pauta existente
    python -m news_agent --write-article reportes/pauta_semanal_2026_07_04.md \\
                         --article 1 --output ./articulos

    # Repurposing de un artículo para redes sociales
    python -m news_agent --socialize articulos/articulo_1_slug.md \\
                         --output ./social
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import cli
from .article_writer import PautaParseError, write_article
from .cli import (
    CANCELLED_MESSAGE,
    print_article_summary,
    print_report_summary,
    print_social_summary,
)
from .config import (
    DEFAULT_ARTICLES_DIR,
    DEFAULT_REPORTS_DIR,
    DEFAULT_SOCIAL_OUTPUT_DIR,
    NUM_PROPOSALS,
)
from .orchestrator import run_pipeline
from .social.platform_specs import ALL_PLATFORMS, parse_platforms


def _build_legacy_epilog() -> str:
    """Construye el pie de ayuda de los modos clásicos.

    Returns:
        str: Listado de los subcomandos simplificados y ejemplos del modo
        clásico.
    """
    lines = ["Comandos simplificados (recomendados):", ""]
    lines.extend(
        f"  {name:<8} {cli.COMMAND_DESCRIPTIONS[name]}" for name in cli.COMMANDS
    )
    lines.extend(
        [
            "",
            "Usa '-h' después de un comando para ver sus opciones.",
            "",
            "Ejemplos del modo clásico:",
            "  python -m news_agent --feeds rss_feeds.json --output ./reportes",
            (
                "  python -m news_agent --write-article "
                "reportes/pauta_semanal_2026_07_04.md --article 1 "
                "--output ./articulos"
            ),
            (
                "  python -m news_agent --socialize articulos/articulo_1_slug.md "
                "--output ./social"
            ),
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos del CLI.

    Returns:
        argparse.ArgumentParser: Parser con todos los modos del agente.
    """
    parser = argparse.ArgumentParser(
        description="Agente Inteligente de Contenidos - La Chispa Sur",
        epilog=_build_legacy_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # --- Argumentos para generar pauta ---
    parser.add_argument(
        "--feeds",
        type=str,
        default=None,
        help="Ruta al archivo JSON de configuración de feeds RSS "
        "(por defecto: rss_feeds.json).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Directorio de salida de los archivos generados. Si se omite se "
        f"usa {DEFAULT_REPORTS_DIR}/, {DEFAULT_ARTICLES_DIR}/ o "
        f"{DEFAULT_SOCIAL_OUTPUT_DIR}/ según el modo. Nunca se escribe en "
        "el directorio actual.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Activa logging en modo DEBUG para diagnóstico detallado.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Guarda un archivo JSON intermedio con los artículos procesados "
        "en debug/articulos_procesados_YYYY_MM_DD.json para depuración "
        "y comparación manual.",
    )

    # --- Argumentos para escribir artículos desde pauta existente ---
    parser.add_argument(
        "--write-article",
        type=str,
        default=None,
        metavar="RUTA_PAUTA",
        help="Ruta al archivo de pauta semanal desde el cual escribir un artículo.",
    )
    parser.add_argument(
        "--article",
        type=int,
        default=None,
        choices=list(range(1, NUM_PROPOSALS + 1)),
        metavar="N",
        help=f"Número de propuesta a desarrollar (1 a {NUM_PROPOSALS}). "
        "Usar junto con --write-article.",
    )

    # --- Argumentos para el repurposing de redes sociales ---
    parser.add_argument(
        "--socialize",
        type=str,
        default=None,
        metavar="RUTA_ARTICULO",
        help="Ruta al artículo Markdown (ej: articulos/articulo_1_slug.md) "
        "del cual generar copys, prompts visuales y banners para redes sociales.",
    )
    parser.add_argument(
        "--platforms",
        type=str,
        default=None,
        metavar="LISTA",
        help="Plataformas a preparar, separadas por comas "
        f"({', '.join(ALL_PLATFORMS)}). Por defecto, todas. "
        "Usar junto con --socialize.",
    )
    parser.add_argument(
        "--social-config",
        type=str,
        default=None,
        metavar="RUTA_CONFIG",
        help="Ruta al archivo JSON de configuración de marca y plantillas "
        "(por defecto: social_config.json). Usar junto con --socialize.",
    )
    parser.add_argument(
        "--skip-banners",
        action="store_true",
        help="Omite el renderizado de banners con Pillow. "
        "Usar junto con --socialize.",
    )
    parser.add_argument(
        "--skip-prompts",
        action="store_true",
        help="Omite la generación de prompts visuales en inglés. "
        "Usar junto con --socialize.",
    )

    return parser


def _validate_socialize_args(args: argparse.Namespace) -> None:
    """Valida la coherencia de los argumentos del modo --socialize.

    Args:
        args: Argumentos ya parseados.

    Raises:
        SystemExit: Si la combinación de argumentos es inválida.
    """
    social_only_flags = {
        "--platforms": args.platforms is not None,
        "--social-config": args.social_config is not None,
        "--skip-banners": args.skip_banners,
        "--skip-prompts": args.skip_prompts,
    }

    if args.socialize:
        conflicting = [
            flag
            for flag, present in (
                ("--feeds", args.feeds is not None),
                ("--debug", args.debug),
                ("--write-article", args.write_article is not None),
                ("--article", args.article is not None),
            )
            if present
        ]
        if conflicting:
            print(
                "Error: --socialize no se puede combinar con "
                f"{', '.join(conflicting)}. Ejecuta cada modo por separado.",
                file=sys.stderr,
            )
            sys.exit(2)
        return

    # Estas banderas solo tienen sentido junto con --socialize
    orphans = [flag for flag, present in social_only_flags.items() if present]
    if orphans:
        print(
            f"Error: {', '.join(orphans)} requiere el flag --socialize.",
            file=sys.stderr,
        )
        sys.exit(2)


def _resolve_legacy_output(args: argparse.Namespace, default: str) -> Path:
    """Resuelve el directorio de salida de un modo clásico.

    Los modos clásicos tampoco escriben en el directorio actual: si no se pasó
    --output se usa el directorio por defecto del modo, y una ruta que apunte
    al directorio actual se rechaza.

    Args:
        args: Argumentos ya parseados.
        default: Directorio a usar cuando no se pasó --output.

    Returns:
        Path: Directorio, ya creado, listo para escribir.

    Raises:
        SystemExit: Si la ruta pedida es inválida o es el directorio actual.
    """
    try:
        return cli.resolve_output_dir(args.output, default)
    except cli.OutputDirectoryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


def _run_socialize_mode(args: argparse.Namespace) -> None:
    """Ejecuta el modo de repurposing para redes sociales.

    Args:
        args: Argumentos ya validados del CLI.
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
        platforms = parse_platforms(args.platforms)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    output_dir = _resolve_legacy_output(args, DEFAULT_SOCIAL_OUTPUT_DIR)

    try:
        result = run_socialize(
            article_path=args.socialize,
            output_dir=output_dir,
            config_path=args.social_config,
            platforms=platforms,
            verbose=args.verbose,
            skip_banners=args.skip_banners,
            skip_prompts=args.skip_prompts,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print(CANCELLED_MESSAGE, file=sys.stderr)
        sys.exit(130)

    print_social_summary(result)


def _run_article_mode(args: argparse.Namespace) -> None:
    """Ejecuta el modo de escritura de artículo desde una pauta.

    Args:
        args: Argumentos ya parseados del CLI.
    """
    if args.article is None:
        print(
            f"Error: Debes especificar --article N (1 a {NUM_PROPOSALS}) "
            "junto con --write-article.",
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir = _resolve_legacy_output(args, DEFAULT_ARTICLES_DIR)

    try:
        result = write_article(
            pauta_path=args.write_article,
            article_number=args.article,
            output_dir=output_dir,
            verbose=args.verbose,
        )
    except PautaParseError as exc:
        print(f"Error al leer la pauta: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print(CANCELLED_MESSAGE, file=sys.stderr)
        sys.exit(130)

    print_article_summary(result)


def _run_pipeline_mode(args: argparse.Namespace) -> None:
    """Ejecuta el pipeline completo de generación de pauta.

    Args:
        args: Argumentos ya parseados del CLI.
    """
    output_dir = _resolve_legacy_output(args, DEFAULT_REPORTS_DIR)

    try:
        result = run_pipeline(
            feeds_path=args.feeds,
            output_dir=output_dir,
            verbose=args.verbose,
            save_intermediate_data=args.debug,
        )
    except KeyboardInterrupt:
        print(CANCELLED_MESSAGE, file=sys.stderr)
        sys.exit(130)

    print_report_summary(result)


def _extract_command(argv: Sequence[str]) -> str | None:
    """Devuelve el subcomando cuando la invocación usa el CLI simplificado.

    El subcomando se reconoce solo en la primera posición: los modos clásicos
    siempre empiezan con una bandera, así que un valor que coincida con el
    nombre de un comando (por ejemplo ``--output social``) no se confunde.

    Args:
        argv: Argumentos de la línea de comandos, sin el nombre del programa.

    Returns:
        str | None: Nombre del subcomando, o None si la invocación es clásica.
    """
    if not argv or argv[0].startswith("-"):
        return None
    return argv[0]


def main(argv: list[str] | None = None) -> None:
    """Función principal del CLI del agente de contenidos.

    Sin argumentos no se ejecuta ningún flujo: se muestra la ayuda y se sale
    con error de uso, para no consumir tokens de la API ni escribir archivos
    por accidente.

    Args:
        argv: Argumentos de línea de comandos. Si es None, se usan los de
              ``sys.argv``.
    """
    raw = list(sys.argv[1:] if argv is None else argv)

    command = _extract_command(raw)
    if command is not None:
        if command not in cli.COMMANDS:
            print(
                f"Error: comando desconocido '{command}'. "
                f"Comandos disponibles: {', '.join(cli.COMMANDS)}.",
                file=sys.stderr,
            )
            sys.exit(2)

        cli.run(raw)
        return

    parser = build_parser()

    # Ejecutar el pipeline sin argumentos escribiría la pauta y consumiría
    # tokens de la API sin que el usuario lo haya pedido.
    if not raw:
        parser.print_help()
        sys.exit(2)

    args = parser.parse_args(raw)

    _validate_socialize_args(args)

    if args.socialize:
        _run_socialize_mode(args)
        return

    if args.write_article:
        _run_article_mode(args)
        return

    _run_pipeline_mode(args)


if __name__ == "__main__":
    main()
