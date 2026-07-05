"""Punto de entrada del agente: python -m news_agent.

Permite ejecutar el pipeline de curaduría de pauta editorial y la escritura
de artículos completos desde la línea de comandos.

Uso:
    # Generar pauta semanal
    python -m news_agent --feeds rss_feeds.json --output ./reportes

    # Escribir artículo desde una pauta existente
    python -m news_agent --write-article reportes/pauta_semanal_2026_07_04.md \\
                         --article 1 --output ./articulos
"""

import argparse
import sys

from .article_writer import PautaParseError, write_article
from .orchestrator import run_pipeline


def main() -> None:
    """Función principal del CLI del agente de noticias."""
    parser = argparse.ArgumentParser(
        description="Agente Inteligente de Pauta Editorial - La Chispa Sur",
        epilog=(
            "Ejemplos:\n"
            "  python -m news_agent --feeds rss_feeds.json --output ./reportes\n"
            "  python -m news_agent --write-article reportes/pauta_semanal_2026_07_04.md "
            "--article 1 --output ./articulos"
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
        choices=[1, 2, 3],
        metavar="N",
        help="Número de propuesta a desarrollar (1, 2 o 3). "
        "Usar junto con --write-article.",
    )

    args = parser.parse_args()

    # -------------------------------------------------------------------
    # Modo: Escritura de artículo desde pauta
    # -------------------------------------------------------------------
    if args.write_article:
        if args.article is None:
            print(
                "Error: Debes especificar --article N (1, 2 o 3) "
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
            print("\nEjecución cancelada por el usuario.", file=sys.stderr)
            sys.exit(130)

        print("\n✅ Artículo escrito exitosamente:")
        print(f"   📄 {result['article_path']}")
        print(f"   📝 \"{result['title']}\"")
        return

    # -------------------------------------------------------------------
    # Modo: Pipeline completo de generación de pauta (comportamiento default)
    # -------------------------------------------------------------------
    try:
        result = run_pipeline(
            feeds_path=args.feeds,
            output_dir=args.output,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        print("\nEjecución cancelada por el usuario.", file=sys.stderr)
        sys.exit(130)

    print("\n✅ Reporte generado exitosamente:")
    print(f"   📄 {result['report_path']}")
    print(f"   📊 {result['item_count']} artículos analizados de "
           f"{result['feed_count']} fuentes.")


if __name__ == "__main__":
    main()
