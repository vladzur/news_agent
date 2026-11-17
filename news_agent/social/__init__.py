"""Subsistema de repurposing de artículos para redes sociales (RRSS).

Convierte un artículo Markdown ya publicado en piezas multiplataforma:

- Copys estructurados (hooks, síntesis ejecutiva e hilos) para X, Facebook
  e Instagram.
- Un prompt visual en inglés para Midjourney, con tratamiento fotorrealista
  documental o caricatura según el contenido de la columna.
- Banners promocionales renderizados localmente con Pillow.

El punto de entrada es :func:`news_agent.social.orchestrator.run_socialize`.
"""

__all__: list[str] = []
