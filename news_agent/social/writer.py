"""Escritura del bundle de artefactos del subsistema RRSS.

Cada ejecución produce una carpeta autocontenida con todo lo necesario para
publicar la pieza: el JSON de copys, el JSON de prompts visuales, un Markdown
listo para copiar y pegar por plataforma, los PNG de los banners y un
manifiesto que registra qué se generó y qué quedó pendiente.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import SOCIAL_X_MAX_CHARS
from ..report_writer import _slugify
from .models import (
    ArticleSource,
    BannerSpec,
    InstagramSlideSpec,
    SocialCopy,
    VisualPrompt,
)
from .platform_specs import platform_spec
from .text_utils import render_hashtags

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# Nombre de la subcarpeta de assets y de los archivos del bundle
ASSETS_DIR_NAME = "assets"
INSTAGRAM_DIR_NAME = "instagram"
COPY_FILE_NAME = "social_copy.json"
PROMPTS_FILE_NAME = "visual_prompts.json"
PROMPT_TEXT_FILE_NAME = "visual_prompt.txt"
MANIFEST_FILE_NAME = "manifest.json"

# Nombre del archivo Markdown por plataforma
MARKDOWN_FILE_NAMES: dict[str, str] = {
    "x": "x_thread.md",
    "facebook": "facebook_post.md",
    "instagram": "instagram_caption.md",
}


# ---------------------------------------------------------------------------
# Estructura del bundle
# ---------------------------------------------------------------------------


def build_bundle_dir(
    output_dir: str | Path,
    slug: str,
    when: datetime | None = None,
) -> Path:
    """Crea y devuelve el directorio del bundle de una pieza.

    El nombre combina la fecha de ejecución y el slug del titular, igual que
    los reportes de pauta, para que la carpeta sea identificable y ordenable.

    Args:
        output_dir: Directorio base de salida (ej: "social").
        slug: Slug del titular del artículo.
        when: Momento de la generación. Por defecto, el actual en UTC.

    Returns:
        Path: Ruta absoluta al directorio del bundle, ya creado.
    """
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    moment = when or datetime.now(timezone.utc)
    folder = f"{moment.strftime('%Y_%m_%d')}_{slug or 'sin-titulo'}"
    bundle_dir = (base / folder).resolve()

    if bundle_dir.exists():
        logger.info(
            "El bundle ya existía y será sobrescrito: %s", bundle_dir
        )
    bundle_dir.mkdir(parents=True, exist_ok=True)

    return bundle_dir


def assets_dir(bundle_dir: str | Path) -> Path:
    """Crea y devuelve la subcarpeta de assets del bundle.

    Args:
        bundle_dir: Directorio del bundle.

    Returns:
        Path: Ruta absoluta a la carpeta de assets.
    """
    path = Path(bundle_dir) / ASSETS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def instagram_dir(bundle_dir: str | Path) -> Path:
    """Crea y devuelve el subdirectorio exclusivo del carrusel de Instagram.

    Las cinco piezas verticales viven juntas aquí, separadas del resto de los
    banners del bundle, para que se publiquen como un carrusel y no se mezclen
    con las imágenes de otras plataformas.

    Args:
        bundle_dir: Directorio del bundle.

    Returns:
        Path: Ruta absoluta a la carpeta del carrusel.
    """
    path = Path(bundle_dir) / INSTAGRAM_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def slug_for_title(title: str) -> str:
    """Genera el slug del bundle a partir del titular del artículo.

    Args:
        title: Titular del artículo.

    Returns:
        str: Slug apto para nombre de carpeta.
    """
    return _slugify(title) or "sin-titulo"


# ---------------------------------------------------------------------------
# Escritura de JSON
# ---------------------------------------------------------------------------


def _dump_json(payload: Any, file_path: Path) -> Path:
    """Escribe un payload como JSON legible en UTF-8.

    Args:
        payload: Datos serializables.
        file_path: Ruta del archivo de destino.

    Returns:
        Path: Ruta absoluta del archivo escrito.
    """
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    logger.info("JSON guardado: %s", file_path.resolve())
    return file_path.resolve()


def save_copy_json(copy: SocialCopy, bundle_dir: str | Path) -> Path:
    """Guarda el JSON estructurado de copys.

    Args:
        copy: Copys generados.
        bundle_dir: Directorio del bundle.

    Returns:
        Path: Ruta absoluta del archivo escrito.
    """
    return _dump_json(copy.to_dict(), Path(bundle_dir) / COPY_FILE_NAME)


def save_visual_prompt_json(prompt: VisualPrompt, bundle_dir: str | Path) -> Path:
    """Guarda el JSON con los metadatos del prompt visual.

    Args:
        prompt: Prompt visual generado.
        bundle_dir: Directorio del bundle.

    Returns:
        Path: Ruta absoluta del archivo escrito.
    """
    return _dump_json(prompt.to_dict(), Path(bundle_dir) / PROMPTS_FILE_NAME)


def save_visual_prompt_text(prompt: VisualPrompt, bundle_dir: str | Path) -> Path:
    """Guarda el comando de Midjourney como texto plano, listo para pegar.

    Midjourney no admite comillas escapadas ni JSON: el archivo contiene
    únicamente el comando, con sus tags (``--ar``, ``--style``, ``--v``,
    ``--no``) y sin ningún carácter de escape.

    Args:
        prompt: Prompt visual generado.
        bundle_dir: Directorio del bundle.

    Returns:
        Path: Ruta absoluta del archivo escrito.
    """
    target = Path(bundle_dir).resolve() / PROMPT_TEXT_FILE_NAME
    target.write_text(f"{prompt.midjourney_prompt}\n", encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Escritura de Markdown por plataforma
# ---------------------------------------------------------------------------


def _header(title: str, platform: str, source_path: str) -> list[str]:
    """Compone la cabecera de un archivo Markdown de plataforma.

    Args:
        title: Titular del artículo.
        platform: Nombre de la plataforma.
        source_path: Ruta del artículo de origen.

    Returns:
        list[str]: Líneas de la cabecera.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return [
        f"# {platform} — {title}",
        "",
        f"**Generado:** {timestamp}  ",
        f"**Origen:** {source_path}",
        "",
        "---",
        "",
    ]


def render_x_thread_markdown(
    copy: SocialCopy, limit: int = SOCIAL_X_MAX_CHARS
) -> str:
    """Compone el Markdown del hilo de X, con conteo de caracteres por tweet.

    Args:
        copy: Copys generados.
        limit: Límite de caracteres de la plataforma, para mostrar el conteo.

    Returns:
        str: Contenido del archivo ``x_thread.md``.
    """
    lines = _header(copy.title, "Hilo para X", copy.source_path)

    lines.extend(
        [
            "## Hilo completo (copiar y pegar)",
            "",
        ]
    )
    for tweet in copy.x.thread:
        lines.extend([tweet, ""])

    lines.extend(
        [
            "---",
            "",
            "## Tweet por tweet",
            "",
            f"**Cantidad de tweets:** {len(copy.x.thread)}",
            "",
        ]
    )
    for index, tweet in enumerate(copy.x.thread, start=1):
        lines.extend(
            [
                f"### Tweet {index} · {len(tweet)}/{limit} caracteres",
                "",
                tweet,
                "",
            ]
        )

    if copy.x.hashtags:
        lines.extend(
            [
                "---",
                "",
                f"**Hashtags:** {render_hashtags(copy.x.hashtags)}  ",
                "_Ya incluidos en el tweet de cierre._",
                "",
            ]
        )

    if copy.hooks:
        lines.extend(["---", "", "## Ganchos alternativos", ""])
        for index, hook in enumerate(copy.hooks, start=1):
            lines.extend([f"{index}. {hook}", ""])

    if copy.summary:
        lines.extend(["---", "", "## Síntesis ejecutiva", ""])
        for bullet in copy.summary:
            lines.extend([f"- {bullet}", ""])

    return "\n".join(lines).rstrip() + "\n"


def render_facebook_markdown(copy: SocialCopy) -> str:
    """Compone el Markdown del post de Facebook.

    Args:
        copy: Copys generados.

    Returns:
        str: Contenido del archivo ``facebook_post.md``.
    """
    lines = _header(copy.title, "Post para Facebook", copy.source_path)
    lines.extend(["## Texto del post", "", copy.facebook.post, ""])

    if copy.facebook.hashtags:
        lines.extend(
            [
                "---",
                "",
                f"**Hashtags:** {render_hashtags(copy.facebook.hashtags)}",
                "",
            ]
        )

    if copy.alt_text.get("facebook"):
        lines.extend(
            [
                "---",
                "",
                f"**Texto alternativo de la imagen:** {copy.alt_text['facebook']}",
                "",
            ]
        )

    lines.extend(["---", "", f"**Llamado a la acción:** {copy.cta}", ""])
    return "\n".join(lines).rstrip() + "\n"


def render_instagram_markdown(copy: SocialCopy) -> str:
    """Compone el Markdown de la publicación de Instagram.

    Args:
        copy: Copys generados.

    Returns:
        str: Contenido del archivo ``instagram_caption.md``.
    """
    lines = _header(copy.title, "Publicación para Instagram", copy.source_path)
    lines.extend(["## Caption", "", copy.instagram.caption, ""])

    if copy.instagram.hashtags:
        lines.extend(
            [
                "---",
                "",
                "**Hashtags** (van aparte, en el primer comentario):",
                "",
                render_hashtags(copy.instagram.hashtags),
                "",
            ]
        )

    lines.extend(["---", "", "## Tarjeta de cita", ""])
    lines.extend(
        [
            f"> {copy.quote_card.quote}",
            "",
            f"— {copy.quote_card.attribution}",
            "",
        ]
    )
    if not copy.quote_card.verbatim:
        lines.extend(
            [
                ("> ⚠️ Esta cita no se pudo verificar palabra por palabra "
                "contra el artículo de origen."),
                "",
            ]
        )

    if copy.instagram.slides:
        lines.extend(
            [
                "---",
                "",
                "## Carrusel vertical · 3 slides de resumen",
                "",
                (
                    "Los PNG están en `instagram/`, en orden de publicación: "
                    "portada, tres resúmenes y firma de marca. Todas las "
                    "piezas son verticales de 1080×1920."
                ),
                "",
            ]
        )
        for index, slide in enumerate(copy.instagram.slides, start=1):
            lines.extend(
                [
                    f"### Slide {index}. {slide.title}",
                    "",
                    slide.body,
                    "",
                ]
            )
            if slide.figure:
                lines.extend([f"**Dato clave:** {slide.figure}", ""])

    if copy.alt_text.get("instagram"):
        lines.extend(
            [
                "---",
                "",
                f"**Texto alternativo de la imagen:** {copy.alt_text['instagram']}",
                "",
            ]
        )

    lines.extend(["---", "", f"**Llamado a la acción:** {copy.cta}", ""])
    return "\n".join(lines).rstrip() + "\n"


def save_platform_markdown(
    copy: SocialCopy,
    bundle_dir: str | Path,
    platforms: list[str],
    config: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Guarda un Markdown por cada plataforma habilitada.

    Args:
        copy: Copys generados.
        bundle_dir: Directorio del bundle.
        platforms: Plataformas para las que escribir archivo.
        config: Configuración de marca, usada para resolver el límite de X
                cuando la plataforma lo sobrescribe.

    Returns:
        dict[str, Path]: Mapa plataforma → ruta del archivo escrito.
    """
    renderers = {
        "x": render_x_thread_markdown,
        "facebook": render_facebook_markdown,
        "instagram": render_instagram_markdown,
    }
    x_limit = int(platform_spec(config, "x")["max_chars"])

    written: dict[str, Path] = {}
    for platform in platforms:
        renderer = renderers.get(platform)
        if renderer is None:
            logger.warning(
                "No hay plantilla Markdown para la plataforma '%s': se omite.",
                platform,
            )
            continue

        file_path = Path(bundle_dir) / MARKDOWN_FILE_NAMES[platform]
        if platform == "x":
            content = render_x_thread_markdown(copy, limit=x_limit)
        else:
            content = renderer(copy)
        file_path.write_text(content, encoding="utf-8")
        logger.info("Markdown guardado: %s", file_path.resolve())
        written[platform] = file_path.resolve()

    return written


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------


def save_manifest(
    bundle_dir: str | Path,
    copy: SocialCopy,
    prompt: VisualPrompt | None,
    banners: list[BannerSpec],
    markdown_files: dict[str, Path],
    platforms: list[str],
    article: ArticleSource,
    prompt_status: str | None = None,
    prompt_error: str | None = None,
    carousel_slides: list[InstagramSlideSpec] | None = None,
    carousel_dir_path: Path | None = None,
    carousel_format: str | None = None,
) -> Path:
    """Guarda el manifiesto del bundle con todo lo generado.

    Args:
        bundle_dir: Directorio del bundle.
        copy: Copys generados.
        prompt: Prompt visual generado, o None si falló o se omitió.
        banners: Banners renderizados.
        markdown_files: Archivos Markdown escritos, por plataforma.
        platforms: Plataformas habilitadas en la ejecución.
        article: Artículo de origen.
        prompt_status: Estado explícito del prompt visual: ``generated``,
                       ``skipped`` o ``failed``. Si se omite, se deduce de
                       ``prompt``.
        prompt_error: Motivo del fallo cuando ``prompt_status`` es ``failed``.
        carousel_slides: Slides del carrusel de Instagram renderizados.
        carousel_dir_path: Subdirectorio exclusivo del carrusel, si se generó.
        carousel_format: Nombre del formato vertical usado por el carrusel.

    Returns:
        Path: Ruta absoluta del manifiesto escrito.
    """
    rendered = [banner for banner in banners if banner.path is not None]
    failed = [banner for banner in banners if banner.path is None]

    if prompt is not None:
        status = "generated"
    elif prompt_status in {"skipped", "failed"}:
        status = prompt_status
    else:
        status = "skipped"

    carousel_items = list(carousel_slides or [])
    carousel_rendered = [slide for slide in carousel_items if slide.path is not None]
    carousel_failed = [slide for slide in carousel_items if slide.path is None]
    if carousel_rendered:
        carousel_status = "generated" if not carousel_failed else "partial"
    elif carousel_failed:
        carousel_status = "failed"
    else:
        carousel_status = "skipped"

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platforms": platforms,
        "article": {
            "title": article.title,
            "source_path": str(article.path),
            "word_count": article.word_count,
            "sections": len(article.sections),
            "sources": len(article.sources),
        },
        "files": {
            "copy": COPY_FILE_NAME,
            "visual_prompts": PROMPTS_FILE_NAME if prompt else None,
            "visual_prompt_text": PROMPT_TEXT_FILE_NAME if prompt else None,
            "markdown": {
                platform: path.name for platform, path in markdown_files.items()
            },
            "instagram_carousel": (
                INSTAGRAM_DIR_NAME if carousel_dir_path else None
            ),
        },
        "visual_prompts": {
            "status": status,
            "error": prompt_error if status == "failed" else None,
            "count": 1 if prompt else 0,
            "treatment": prompt.treatment if prompt else None,
            "aspect_ratio": prompt.aspect_ratio if prompt else None,
        },
        "banners": {
            "rendered": len(rendered),
            "failed": len(failed),
            "items": [banner.to_dict() for banner in banners],
        },
        "instagram_carousel": {
            "status": carousel_status,
            "directory": (
                carousel_dir_path.name if carousel_dir_path else None
            ),
            "format": carousel_format,
            "width": carousel_items[0].width if carousel_items else None,
            "height": carousel_items[0].height if carousel_items else None,
            "slides": len(carousel_items),
            "rendered": len(carousel_rendered),
            "failed": len(carousel_failed),
            "items": [slide.to_dict() for slide in carousel_items],
        },
        "verified_quote": copy.quote_card.verbatim,
    }

    return _dump_json(payload, Path(bundle_dir) / MANIFEST_FILE_NAME)
