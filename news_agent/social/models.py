"""Modelos de datos del subsistema de repurposing para redes sociales.

Todos los artefactos que produce el subsistema (copys, prompts visuales y
banners) se representan aquí como dataclasses, de modo que el resto de los
módulos trabaje con tipos explícitos en lugar de diccionarios sueltos y la
serialización a JSON sea determinista.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Material de origen
# ---------------------------------------------------------------------------


@dataclass
class ArticleSection:
    """Sección del artículo con su subtítulo y cuerpo.

    Attributes:
        heading: Subtítulo de la sección (sin el prefijo '##').
        body: Texto completo de la sección.
    """

    heading: str
    body: str


@dataclass
class ArticleSource:
    """Artículo de origen ya parseado, listo para alimentar los prompts.

    Attributes:
        path: Ruta al archivo Markdown de origen.
        title: Titular del artículo (encabezado de nivel 1).
        byline: Firma del artículo (ej: "Por La Chispa Sur"). Vacía si no existe.
        lead: Primer bloque de párrafos, antes del primer subtítulo.
        sections: Secciones del artículo en orden de aparición.
        paragraphs: Todos los párrafos del cuerpo, sin subtítulos ni fuentes.
        sources: Fuentes listadas al final del artículo.
        quote_candidates: Oraciones extraídas del cuerpo, aptas para una
                          tarjeta de cita, ordenadas por potencial.
        key_figures: Expresiones numéricas detectadas en el cuerpo (cifras,
                     porcentajes, montos), usadas como pista para el LLM.
        word_count: Cantidad de palabras del cuerpo.
        raw_text: Texto Markdown completo del archivo.
    """

    path: Path
    title: str
    byline: str
    lead: str
    sections: list[ArticleSection]
    paragraphs: list[str]
    sources: list[str]
    quote_candidates: list[str]
    key_figures: list[str]
    word_count: int
    raw_text: str

    def body_text(self) -> str:
        """Devuelve el cuerpo del artículo sin encabezados ni bloque de fuentes.

        Returns:
            str: Lead más el texto de todas las secciones.
        """
        parts = [self.lead] if self.lead else []
        parts.extend(section.body for section in self.sections if section.body)
        return "\n\n".join(parts)

    def contains_verbatim(self, quote: str, min_length: int = 40) -> bool:
        """Comprueba si una cita aparece literalmente en el artículo.

        La comparación ignora diferencias de espacios, comillas tipográficas y
        marcas de énfasis de Markdown, de modo que una cita copiada por el LLM
        se valide aunque normalice comillas o colapse espacios.

        Args:
            quote: Texto citado que se quiere verificar.
            min_length: Largo mínimo de la cita para considerar la verificación
                        significativa. Citas más cortas se aceptan sin revisar,
                        porque una coincidencia tan breve no prueba nada.

        Returns:
            bool: True si la cita proviene del artículo.
        """
        normalized_quote = normalize_for_match(quote)
        if len(normalized_quote) < min_length:
            return False
        return normalized_quote in normalize_for_match(self.raw_text)


def normalize_for_match(text: str) -> str:
    """Normaliza un texto para comparaciones de coincidencia literal.

    Elimina marcas de énfasis de Markdown, unifica comillas y guiones
    tipográficos, colapsa espacios y recorta los extremos.

    Args:
        text: Texto a normalizar.

    Returns:
        str: Texto normalizado.
    """
    import re

    normalized = text or ""
    # Quitar marcas de énfasis y encabezados de Markdown
    normalized = re.sub(r"[*_`#]+", "", normalized)
    # Unificar comillas y apóstrofos tipográficos
    normalized = (
        normalized.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )
    # Unificar guiones largos y medios
    normalized = normalized.replace("—", "-").replace("–", "-")
    # Colapsar espacios en blanco (incluidos saltos de línea)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


# ---------------------------------------------------------------------------
# Copys por plataforma
# ---------------------------------------------------------------------------


@dataclass
class XCopy:
    """Copy para X/Twitter.

    Attributes:
        hook_tweet: Tweet gancho, siempre dentro del límite de caracteres.
        thread: Hilo completo, con el tweet gancho en la primera posición.
        hashtags: Hashtags sugeridos para el cierre del hilo.
    """

    hook_tweet: str
    thread: list[str]
    hashtags: list[str] = field(default_factory=list)


@dataclass
class FacebookCopy:
    """Copy para Facebook.

    Attributes:
        post: Texto del post, con gancho inicial y desarrollo en párrafos.
        hashtags: Hashtags sugeridos.
    """

    post: str
    hashtags: list[str] = field(default_factory=list)


@dataclass
class InstagramCopy:
    """Copy para Instagram.

    Attributes:
        caption: Texto de la publicación, con primera línea como gancho.
        hashtags: Hashtags para el bloque final.
    """

    caption: str
    hashtags: list[str] = field(default_factory=list)


@dataclass
class QuoteCard:
    """Cita destacada para la tarjeta gráfica.

    Attributes:
        quote: Cita textual tomada del artículo.
        attribution: Atribución mostrada bajo la cita.
        verbatim: True si la cita se verificó literalmente contra el artículo.
    """

    quote: str
    attribution: str
    verbatim: bool = False


@dataclass
class SocialCopy:
    """Conjunto completo de copys derivados de un artículo.

    Attributes:
        title: Titular del artículo de origen.
        slug: Slug del titular, usado para nombrar el bundle de salida.
        source_path: Ruta del artículo de origen.
        generated_at: Marca temporal ISO 8601 de la generación.
        hooks: Titulares alternativos y ganchos breves.
        summary: Síntesis ejecutiva en bullets.
        hook: Gancho transversal, reutilizable en cualquier plataforma.
        quote_card: Cita destacada para la tarjeta gráfica.
        key_figures: Cifras o datos duros destacados del artículo.
        cta: Llamado a la acción.
        alt_text: Textos alternativos por plataforma (accesibilidad).
        x: Copy para X/Twitter.
        facebook: Copy para Facebook.
        instagram: Copy para Instagram.
    """

    title: str
    slug: str
    source_path: str
    generated_at: str
    hooks: list[str]
    summary: list[str]
    hook: str
    quote_card: QuoteCard
    key_figures: list[str]
    cta: str
    alt_text: dict[str, str]
    x: XCopy
    facebook: FacebookCopy
    instagram: InstagramCopy

    def platform_copies(self) -> dict[str, Any]:
        """Devuelve los copys indexados por plataforma.

        Returns:
            dict[str, Any]: Mapa plataforma → copy (x, facebook, instagram).
        """
        return {"x": self.x, "facebook": self.facebook, "instagram": self.instagram}

    def to_dict(self) -> dict[str, Any]:
        """Serializa el copy completo a un diccionario apto para JSON.

        Returns:
            dict[str, Any]: Representación serializable.
        """
        return asdict(self)


# ---------------------------------------------------------------------------
# Prompts visuales
# ---------------------------------------------------------------------------


@dataclass
class VisualPrompt:
    """Prompt en inglés para generadores de imágenes.

    Attributes:
        aspect: Identificador del aspecto ("landscape", "square", "portrait").
        aspect_ratio: Proporción legible (ej: "16:9").
        platforms: Plataformas destinatarias de este aspecto.
        prompt: Prompt positivo, en inglés y sin referencias a texto.
        negative_prompt: Prompt negativo con los artefactos a evitar.
        midjourney_prompt: Prompt listo para Midjourney, con sus flags.
        settings: Parámetros sugeridos (pasos, guidance, sampler).
    """

    aspect: str
    aspect_ratio: str
    platforms: list[str]
    prompt: str
    negative_prompt: str
    midjourney_prompt: str
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializa el prompt visual a un diccionario apto para JSON.

        Returns:
            dict[str, Any]: Representación serializable.
        """
        return asdict(self)


# ---------------------------------------------------------------------------
# Banners y resultado del bundle
# ---------------------------------------------------------------------------


@dataclass
class BannerSpec:
    """Especificación de un banner renderizado.

    Attributes:
        template: Nombre de la plantilla usada (ej: "headline_card").
        platform: Formato de plataforma (ej: "instagram_story").
        width: Ancho en píxeles.
        height: Alto en píxeles.
        path: Ruta del PNG generado. None si el render falló.
    """

    template: str
    platform: str
    width: int
    height: int
    path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa la especificación del banner a un diccionario.

        Returns:
            dict[str, Any]: Representación serializable (la ruta como texto).
        """
        data = asdict(self)
        data["path"] = str(self.path) if self.path else None
        return data


@dataclass
class SocialPackage:
    """Resultado completo de una ejecución de repurposing.

    Attributes:
        bundle_dir: Directorio del bundle generado.
        copy: Copys derivados del artículo.
        visual_prompts: Prompts visuales generados.
        banners: Banners renderizados (vacío si se omitieron).
        copy_path: Ruta del JSON de copys.
        prompts_path: Ruta del JSON de prompts visuales, o None si se omitió.
        manifest_path: Ruta del manifiesto del bundle.
    """

    bundle_dir: Path
    copy: SocialCopy
    visual_prompts: list[VisualPrompt]
    copy_path: Path
    manifest_path: Path
    banners: list[BannerSpec] = field(default_factory=list)
    prompts_path: Path | None = None
