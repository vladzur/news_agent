"""Punto de entrada del agente: python -m news_agent.

Permite ejecutar el pipeline de curaduría de pauta editorial directamente
desde la línea de comandos.
"""

import argparse
import sys

from .orchestrator import run_pipeline


def main() -> None:
    """Función principal del CLI del agente de noticias."""
    parser = argparse.ArgumentParser(
        description="Agente Inteligente de Pauta Editorial - La Chispa Sur",
        epilog="Ejemplo: python -m news_agent --feeds rss_feeds.json --output ./reportes",
    )
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
        help="Directorio de salida para el reporte generado (por defecto: .).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Activa logging en modo DEBUG para diagnóstico detallado.",
    )

    args = parser.parse_args()

    try:
        result = run_pipeline(
            feeds_path=args.feeds,
            output_dir=args.output,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        print("\nEjecución cancelada por el usuario.", file=sys.stderr)
        sys.exit(130)

    print(f"\n✅ Reporte generado exitosamente:")
    print(f"   📄 {result['report_path']}")
    print(f"   📊 {result['item_count']} artículos analizados de "
           f"{result['feed_count']} fuentes.")


if __name__ == "__main__":
    main()
