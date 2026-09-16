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
from .models import ArticleSource, BannerSpec, SocialCopy, VisualPrompt
from .text_utils import render_hashtags

# ---------------------------------------------------------------------------
# Logger del módulo
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# Nombre de la subcarpeta de assets y de los archivos del bundle
ASSETS_DIR_NAME = "assets"
COPY_FILE_NAME = "social_copy.json"
PROMPTS_FILE_NAME = "visual_prompts.json"
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


def save_visual_prompts_json(
    prompts: list[VisualPrompt], bundle_dir: str | Path
) -> Path:
    """Guarda el JSON de prompts visuales en inglés.

    Args:
        prompts: Prompts visuales generados.
        bundle_dir: Directorio del bundle.

    Returns:
        Path: Ruta absoluta del archivo escrito.
    """
    payload = {
        "count": len(prompts),
        "prompts": [prompt.to_dict() for prompt in prompts],
    }
    return _dump_json(payload, Path(bundle_dir) / PROMPTS_FILE_NAME)


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
) -> dict[str, Path]:
    """Guarda un Markdown por cada plataforma habilitada.

    Args:
        copy: Copys generados.
        bundle_dir: Directorio del bundle.
        platforms: Plataformas para las que escribir archivo.

    Returns:
        dict[str, Path]: Mapa plataforma → ruta del archivo escrito.
    """
    renderers = {
        "x": render_x_thread_markdown,
        "facebook": render_facebook_markdown,
        "instagram": render_instagram_markdown,
    }

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
        file_path.write_text(renderer(copy), encoding="utf-8")
        logger.info("Markdown guardado: %s", file_path.resolve())
        written[platform] = file_path.resolve()

    return written


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------


def save_manifest(
    bundle_dir: str | Path,
    copy: SocialCopy,
    prompts: list[VisualPrompt],
    banners: list[BannerSpec],
    markdown_files: dict[str, Path],
    platforms: list[str],
    article: ArticleSource,
) -> Path:
    """Guarda el manifiesto del bundle con todo lo generado.

    Args:
        bundle_dir: Directorio del bundle.
        copy: Copys generados.
        prompts: Prompts visuales generados.
        banners: Banners renderizados.
        markdown_files: Archivos Markdown escritos, por plataforma.
        platforms: Plataformas habilitadas en la ejecución.
        article: Artículo de origen.

    Returns:
        Path: Ruta absoluta del manifiesto escrito.
    """
    rendered = [banner for banner in banners if banner.path is not None]
    failed = [banner for banner in banners if banner.path is None]

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
            "visual_prompts": PROMPTS_FILE_NAME if prompts else None,
            "markdown": {
                platform: path.name for platform, path in markdown_files.items()
            },
        },
        "visual_prompts": {
            "count": len(prompts),
            "aspects": [prompt.aspect for prompt in prompts],
        },
        "banners": {
            "rendered": len(rendered),
            "failed": len(failed),
            "items": [banner.to_dict() for banner in banners],
        },
        "verified_quote": copy.quote_card.verbatim,
    }

    return _dump_json(payload, Path(bundle_dir) / MANIFEST_FILE_NAME)
