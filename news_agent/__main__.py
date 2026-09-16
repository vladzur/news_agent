"""Punto de entrada del agente: python -m news_agent.

Permite ejecutar el pipeline de curaduría de pauta editorial, la escritura de
artículos completos desde una pauta y el repurposing de un artículo para redes
sociales, todo desde la línea de comandos.

Uso:
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

from .article_writer import PautaParseError, write_article
from .config import NUM_PROPOSALS
from .orchestrator import run_pipeline
from .social.platform_specs import ALL_PLATFORMS, parse_platforms

# Mensaje común al interrumpir la ejecución con Ctrl+C
CANCELLED_MESSAGE = "\nEjecución cancelada por el usuario."


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos del CLI.

    Returns:
        argparse.ArgumentParser: Parser con todos los modos del agente.
    """
    parser = argparse.ArgumentParser(
        description="Agente Inteligente de Contenidos - La Chispa Sur",
        epilog=(
            "Ejemplos:\n"
            "  python -m news_agent --feeds rss_feeds.json --output ./reportes\n"
            "  python -m news_agent --write-article reportes/pauta_semanal_2026_07_04.md "
            "--article 1 --output ./articulos\n"
            "  python -m news_agent --socialize articulos/articulo_1_slug.md "
            "--output ./social"
        ),
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
        default=".",
        help="Directorio de salida para los archivos generados (por defecto: .).",
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

    try:
        result = run_socialize(
            article_path=args.socialize,
            output_dir=args.output,
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

    try:
        result = write_article(
            pauta_path=args.write_article,
            article_number=args.article,
            output_dir=args.output,
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

    print("\n✅ Artículo escrito exitosamente:")
    print(f"   📄 {result['article_path']}")
    print(f"   📝 \"{result['title']}\"")


def _run_pipeline_mode(args: argparse.Namespace) -> None:
    """Ejecuta el pipeline completo de generación de pauta.

    Args:
        args: Argumentos ya parseados del CLI.
    """
    try:
        result = run_pipeline(
            feeds_path=args.feeds,
            output_dir=args.output,
            verbose=args.verbose,
            save_intermediate_data=args.debug,
        )
    except KeyboardInterrupt:
        print(CANCELLED_MESSAGE, file=sys.stderr)
        sys.exit(130)

    print("\n✅ Reporte generado exitosamente:")
    print(f"   📄 {result['report_path']}")
    print(f"   📊 {result['item_count']} artículos analizados de "
           f"{result['feed_count']} fuentes.")
    if result.get("debug_path"):
        print(f"   🔍 Archivo de depuración: {result['debug_path']}")
    if result.get("companion_path"):
        print(f"   📎 Fuentes acompañantes: {result['companion_path']}")


def main(argv: list[str] | None = None) -> None:
    """Función principal del CLI del agente de contenidos.

    Args:
        argv: Argumentos de línea de comandos. Si es None, se usan los de
              ``sys.argv``.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

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
