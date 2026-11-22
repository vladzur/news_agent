"""Orquestador del subsistema de repurposing para redes sociales.

Coordina el flujo completo a partir de un artículo ya publicado:
configuración de marca → parseo del artículo → copys con el LLM → prompt
visual en inglés para Midjourney → banners con Pillow → bundle en disco.

Cada etapa posterior a los copys es tolerante a fallos: si el prompt
visual o los banners fallan, el bundle se escribe igualmente con lo que sí
se pudo producir, y el manifiesto deja constancia de lo que quedó pendiente.
"""

import logging
import sys
from pathlib import Path
from typing import Any

from ..config import (
    DEFAULT_SOCIAL_OUTPUT_DIR,
    SOCIAL_MAX_TOKENS,
    SOCIAL_MIN_ARTICLE_WORDS,
    SOCIAL_REASONING_EFFORT,
    SOCIAL_TEMPERATURE,
    SOCIAL_VISUAL_MAX_TOKENS,
    SOCIAL_VISUAL_REASONING_EFFORT,
    ConfigurationError,
    get_api_key,
    load_social_config,
)
from ..llm_client import LLMClient, LLMClientError
from ..orchestrator import setup_logging
from .article_source import ArticleParseError, parse_article_file
from .banner_renderer import render_all_banners
from .copy_generator import SocialCopyValidationError, generate_social_copy
from .instagram_renderer import (
    InstagramRenderError,
    render_instagram_carousel,
    resolve_carousel_layout,
)
from .models import (
    ArticleSource,
    BannerSpec,
    InstagramSlideSpec,
    SocialCopy,
    VisualPrompt,
)
from .platform_specs import ALL_PLATFORMS
from .visual_prompts import VisualPromptGenerationError, generate_visual_prompt
from .writer import (
    assets_dir,
    build_bundle_dir,
    instagram_dir,
    save_copy_json,
    save_manifest,
    save_platform_markdown,
    save_visual_prompt_json,
    save_visual_prompt_text,
    slug_for_title,
)

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class SocializeError(Exception):
    """Excepción para errores fatales del subsistema de RRSS."""


# ---------------------------------------------------------------------------
# Helpers de preparación
# ---------------------------------------------------------------------------


def normalize_platforms(platforms: list[str] | None) -> list[str]:
    """Valida y ordena la lista de plataformas pedidas.

    Args:
        platforms: Plataformas pedidas. Si es None o está vacía, se devuelven
                   todas las soportadas.

    Returns:
        list[str]: Plataformas válidas, en el orden editorial habitual.

    Raises:
        ValueError: Si se pidió una plataforma desconocida.
    """
    if not platforms:
        return list(ALL_PLATFORMS)

    requested = {str(platform).strip().lower() for platform in platforms}
    unknown = sorted(requested - set(ALL_PLATFORMS))
    if unknown:
        raise ValueError(
            f"Plataforma(s) desconocida(s): {', '.join(unknown)}. "
            f"Opciones válidas: {', '.join(ALL_PLATFORMS)}."
        )

    return [name for name in ALL_PLATFORMS if name in requested]


def _load_config(config_path: str | Path | None) -> dict[str, Any]:
    """Carga la configuración de marca, abortando con un error claro.

    Args:
        config_path: Ruta al archivo de configuración de marca.

    Returns:
        dict[str, Any]: Configuración cargada.
    """
    try:
        return load_social_config(config_path)
    except ConfigurationError as exc:
        logger.error("Error de configuración de RRSS: %s", exc)
        sys.exit(1)


def _build_client(
    api_key: str,
    max_tokens: int,
    reasoning_effort: str | None,
    response_format: dict[str, Any] | None,
) -> LLMClient:
    """Construye un cliente LLM configurado para el subsistema de RRSS.

    Args:
        api_key: Clave API de DeepSeek.
        max_tokens: Presupuesto de tokens de salida.
        reasoning_effort: Esfuerzo de razonamiento.
        response_format: Formato de respuesta pedido (JSON), o None.

    Returns:
        LLMClient: Cliente listo para generar contenido.
    """
    return LLMClient(
        api_key=api_key,
        temperature=SOCIAL_TEMPERATURE,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        response_format=response_format,
    )


def _resolve_api_key() -> str:
    """Obtiene la API key, abortando con un error claro si falta.

    Returns:
        str: Clave API de DeepSeek.
    """
    try:
        return get_api_key()
    except ConfigurationError as exc:
        logger.error("Error de configuración: %s", exc)
        sys.exit(1)


def _load_article(article_path: str | Path) -> ArticleSource:
    """Parsea el artículo de origen, abortando con un error claro.

    Args:
        article_path: Ruta al artículo Markdown.

    Returns:
        ArticleSource: Artículo parseado.
    """
    try:
        return parse_article_file(article_path)
    except ArticleParseError as exc:
        logger.error("No se pudo leer el artículo de origen: %s", exc)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Etapas
# ---------------------------------------------------------------------------


def _generate_copy_stage(
    article: ArticleSource,
    config: dict[str, Any],
    client: LLMClient,
) -> SocialCopy:
    """Genera los copys del artículo.

    Args:
        article: Artículo de origen.
        config: Configuración de marca.
        client: Cliente LLM configurado para copys.

    Returns:
        SocialCopy: Copys validados.
    """
    try:
        return generate_social_copy(article, config, client)
    except (SocialCopyValidationError, LLMClientError) as exc:
        logger.error("No se pudieron generar los copys de RRSS: %s", exc)
        sys.exit(1)


def _generate_prompt_stage(
    article: ArticleSource,
    copy: SocialCopy,
    config: dict[str, Any],
    client: LLMClient,
) -> tuple[VisualPrompt | None, str | None]:
    """Genera el prompt visual, sin abortar el bundle si falla.

    Args:
        article: Artículo de origen.
        copy: Copys ya generados.
        config: Configuración de marca.
        client: Cliente LLM configurado para el prompt visual.

    Returns:
        tuple[VisualPrompt | None, str | None]: Prompt generado y motivo del
        fallo, o ``(None, error)`` si no se pudo generar.
    """
    try:
        return generate_visual_prompt(article, copy, config, client), None
    except (VisualPromptGenerationError, LLMClientError) as exc:
        logger.error(
            "No se pudo generar el prompt visual: %s. "
            "El bundle se escribirá sin él.",
            exc,
        )
        return None, str(exc)


def _render_banner_stage(
    copy: SocialCopy,
    config: dict[str, Any],
    bundle_dir: Path,
    platforms: list[str],
) -> list[BannerSpec]:
    """Renderiza los banners, sin abortar el bundle si falla el lote.

    Args:
        copy: Copys generados.
        config: Configuración de marca.
        bundle_dir: Directorio del bundle.
        platforms: Plataformas habilitadas.

    Returns:
        list[BannerSpec]: Banners generados (con o sin archivo).
    """
    try:
        destination = assets_dir(bundle_dir)
    except OSError as exc:
        logger.error("No se pudo preparar la carpeta de assets: %s", exc)
        return []

    try:
        return render_all_banners(copy, config, destination, platforms)
    except OSError as exc:
        logger.error(
            "No se pudieron renderizar los banners: %s. "
            "El bundle se escribirá sin assets.",
            exc,
        )
        return []


def _render_carousel_stage(
    copy: SocialCopy,
    config: dict[str, Any],
    bundle_dir: Path,
) -> tuple[str | None, Path | None, list[InstagramSlideSpec]]:
    """Renderiza el carrusel vertical de Instagram, sin abortar el bundle.

    Args:
        copy: Copys generados con los slides de resumen.
        config: Configuración de marca.
        bundle_dir: Directorio del bundle.

    Returns:
        tuple[str | None, Path | None, list[InstagramSlideSpec]]: Nombre del
        formato, subdirectorio del carrusel y slides renderizados. Si el
        formato no es utilizable o falla la preparación del directorio, se
        devuelve ``(None, None, [])``.
    """
    try:
        format_name, _width, _height, _safe_zone = resolve_carousel_layout(config)
    except InstagramRenderError as exc:
        logger.error(
            "No se pudo resolver el formato del carrusel de Instagram: %s",
            exc,
        )
        return None, None, []

    try:
        destination = instagram_dir(bundle_dir)
    except OSError as exc:
        logger.error(
            "No se pudo preparar la carpeta del carrusel de Instagram: %s", exc
        )
        return format_name, None, []

    try:
        slides = render_instagram_carousel(copy, config, destination)
    except (OSError, InstagramRenderError) as exc:
        logger.error(
            "No se pudo renderizar el carrusel de Instagram: %s. "
            "El bundle se escribirá sin los slides.",
            exc,
        )
        return format_name, destination, []

    return format_name, destination, slides


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def run_socialize(
    article_path: str | Path,
    output_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    platforms: list[str] | None = None,
    verbose: bool = False,
    skip_banners: bool = False,
    skip_prompts: bool = False,
) -> dict[str, Any]:
    """Ejecuta el flujo completo de repurposing de un artículo.

    Args:
        article_path: Ruta al artículo Markdown de origen.
        output_dir: Directorio base de salida. Por defecto ``social/``.
        config_path: Ruta a la configuración de marca. Por defecto
                     ``social_config.json``.
        platforms: Plataformas a preparar. Por defecto, todas.
        verbose: Si es True, activa logging DEBUG.
        skip_banners: Si es True, omite el renderizado con Pillow, incluido
                      el carrusel de Instagram.
        skip_prompts: Si es True, omite el prompt visual en inglés.

    Returns:
        dict con las claves:
            - bundle_dir (Path): Carpeta del bundle generado.
            - copy_path (Path): Ruta del JSON de copys.
            - prompts_path (Path | None): Ruta del JSON del prompt visual.
            - prompt_text_path (Path | None): Ruta del comando en texto plano.
            - manifest_path (Path): Ruta del manifiesto.
            - asset_paths (list[Path]): Rutas de los PNG generados.
            - markdown_paths (dict[str, Path]): Markdown por plataforma.
            - platforms (list[str]): Plataformas preparadas.
            - title (str): Titular del artículo.
            - prompt_count (int): 1 si se generó el prompt visual, 0 si no.
            - banner_count (int): Cantidad de banners renderizados.
            - banner_failed (int): Cantidad de banners que fallaron.
            - instagram_dir (Path | None): Subdirectorio exclusivo del
              carrusel, o None si no se generó.
            - carousel_paths (list[Path]): Rutas de los slides verticales.
            - carousel_count (int): Cantidad de slides renderizados.
            - carousel_failed (int): Cantidad de slides que fallaron.
            - carousel_format (str | None): Formato vertical usado.

    Raises:
        ValueError: Si se pidió una plataforma desconocida.
        SystemExit: Si falta la configuración, la API key, el artículo es
                    demasiado corto, o fallan los copys.
    """
    setup_logging(verbose)

    selected_platforms = normalize_platforms(platforms)

    logger.info("=== Iniciando repurposing de RRSS ===")

    config = _load_config(config_path)
    api_key = _resolve_api_key()

    article = _load_article(article_path)

    if article.word_count < SOCIAL_MIN_ARTICLE_WORDS:
        logger.error(
            "El artículo tiene %d palabras, por debajo del mínimo de %d "
            "necesario para derivar copys y banners con sentido. "
            "No se invoca a la API para evitar consumo innecesario de tokens.",
            article.word_count,
            SOCIAL_MIN_ARTICLE_WORDS,
        )
        sys.exit(1)

    logger.info(
        "Artículo cargado: \"%s\" (%d palabras).",
        article.title,
        article.word_count,
    )
    logger.info(
        "Plataformas a preparar: %s.", ", ".join(selected_platforms)
    )

    # -------------------------------------------------------------------
    # Copys
    # -------------------------------------------------------------------
    copy_client = _build_client(
        api_key,
        max_tokens=SOCIAL_MAX_TOKENS,
        reasoning_effort=SOCIAL_REASONING_EFFORT,
        response_format={"type": "json_object"},
    )
    copy = _generate_copy_stage(article, config, copy_client)
    logger.info(
        "Copys generados: %d tweet(s) en el hilo, %d gancho(s) alternativo(s).",
        len(copy.x.thread),
        len(copy.hooks),
    )

    # -------------------------------------------------------------------
    # Bundle y prompt visual
    # -------------------------------------------------------------------
    base_dir = Path(output_dir) if output_dir else Path(DEFAULT_SOCIAL_OUTPUT_DIR)
    bundle_dir = build_bundle_dir(base_dir, slug_for_title(copy.title))
    logger.info("Bundle de salida: %s", bundle_dir)

    prompt: VisualPrompt | None = None
    prompt_status = "skipped"
    prompt_error: str | None = None
    if skip_prompts:
        logger.info("Prompt visual omitido por flag de línea de comandos.")
    else:
        # Se hereda el formato de respuesta del cliente de copys: si la API ya
        # rechazó el JSON mode, no tiene sentido volver a pedirlo.
        prompt_client = _build_client(
            api_key,
            max_tokens=SOCIAL_VISUAL_MAX_TOKENS,
            reasoning_effort=SOCIAL_VISUAL_REASONING_EFFORT,
            response_format=copy_client.response_format,
        )
        prompt, prompt_error = _generate_prompt_stage(
            article, copy, config, prompt_client
        )
        prompt_status = "generated" if prompt else "failed"
        if prompt:
            logger.info("Prompt visual generado (tratamiento %s).", prompt.treatment)

    # -------------------------------------------------------------------
    # Banners
    # -------------------------------------------------------------------
    banners: list[BannerSpec] = []
    if skip_banners:
        logger.info("Banners omitidos por flag de línea de comandos.")
    else:
        banners = _render_banner_stage(copy, config, bundle_dir, selected_platforms)

    # -------------------------------------------------------------------
    # Carrusel vertical de Instagram
    # -------------------------------------------------------------------
    carousel_slides: list[InstagramSlideSpec] = []
    carousel_dir_path: Path | None = None
    carousel_format: str | None = None
    if skip_banners:
        logger.info("Carrusel de Instagram omitido junto con los banners.")
    elif "instagram" not in selected_platforms:
        logger.info(
            "Carrusel de Instagram omitido: la plataforma no fue solicitada."
        )
    else:
        carousel_format, carousel_dir_path, carousel_slides = (
            _render_carousel_stage(copy, config, bundle_dir)
        )
        if carousel_slides:
            rendered_slides = sum(
                1 for slide in carousel_slides if slide.path is not None
            )
            logger.info(
                "Carrusel de Instagram: %d/%d slide(s) en %s.",
                rendered_slides,
                len(carousel_slides),
                carousel_dir_path,
            )

    # -------------------------------------------------------------------
    # Escritura del bundle
    # -------------------------------------------------------------------
    copy_path = save_copy_json(copy, bundle_dir)

    prompts_path: Path | None = None
    prompt_text_path: Path | None = None
    if prompt:
        prompts_path = save_visual_prompt_json(prompt, bundle_dir)
        prompt_text_path = save_visual_prompt_text(prompt, bundle_dir)

    markdown_paths = save_platform_markdown(
        copy, bundle_dir, selected_platforms, config=config
    )

    manifest_path = save_manifest(
        bundle_dir=bundle_dir,
        copy=copy,
        prompt=prompt,
        banners=banners,
        markdown_files=markdown_paths,
        platforms=selected_platforms,
        article=article,
        prompt_status=prompt_status,
        prompt_error=prompt_error,
        carousel_slides=carousel_slides,
        carousel_dir_path=carousel_dir_path,
        carousel_format=carousel_format,
    )

    asset_paths = [banner.path for banner in banners if banner.path is not None]
    carousel_paths = [
        slide.path for slide in carousel_slides if slide.path is not None
    ]
    logger.info("=== Bundle de RRSS completado: %s ===", bundle_dir)

    return {
        "bundle_dir": bundle_dir,
        "copy_path": copy_path,
        "prompts_path": prompts_path,
        "prompt_text_path": prompt_text_path,
        "manifest_path": manifest_path,
        "asset_paths": asset_paths,
        "markdown_paths": markdown_paths,
        "platforms": selected_platforms,
        "title": copy.title,
        "prompt_count": 1 if prompt else 0,
        "banner_count": len(asset_paths),
        "banner_failed": len(banners) - len(asset_paths),
        "instagram_dir": carousel_dir_path,
        "carousel_paths": carousel_paths,
        "carousel_count": len(carousel_paths),
        "carousel_failed": len(carousel_slides) - len(carousel_paths),
        "carousel_format": carousel_format,
    }
