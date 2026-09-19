"""Fotos ilustrativas para os slides: Pexels pela tag do pilar, com cache.

Cada slide ja carrega um `visual` (tag verbatim do vocabulario do canal).
Este modulo resolve a tag para foto real: busca portrait no Pexels, baixa a
primeira, guarda em cache. Sem rede ou sem chave, o slide sai so com layout
-- foto e enriquecimento, nunca requisito que trave o render.

Cache em `output/fotos-cache/`: a mesma tag reusa o arquivo entre renders,
e a avaliacao local nao paga a busca duas vezes.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from pathlib import Path

PEXELS_SEARCH = "https://api.pexels.com/v1/search"


def _chave() -> str:
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        from agent.config import settings
        key = settings.pexels_api_key
    if not key:
        raise ValueError("sem chave Pexels (PEXELS_API_KEY ou AGENT_PEXELS_API_KEY); "
                         "slides saem sem foto")
    return key


def search(query: str, *, per_page: int = 3) -> list[dict]:
    """Fotos portrait para a tag. Devolve dicts crus do Pexels."""
    import json

    params = urllib.parse.urlencode({
        "query": query, "orientation": "portrait", "per_page": per_page})
    req = urllib.request.Request(
        f"{PEXELS_SEARCH}?{params}",
        headers={"Authorization": _chave(),
                 # A API barra o UA padrao do urllib (403): sem isso, toda
                 # busca falha em silencio e o slide sai sem foto.
                 "User-Agent": "tiktok-viral-generator/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        corpo = json.load(r)
    return list(corpo.get("photos", []))


def portrait_url(photo: dict, w: int = 1080, h: int = 1920) -> str:
    """URL ja no corte 9:16 (a API do Pexels redimensiona por parametro)."""
    base = photo.get("src", {}).get("portrait", "")
    if not base:
        raise ValueError("foto sem src.portrait")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}auto=compress&w={w}&h={h}&fit=crop"


def fetch(query: str, dest_dir: str | Path) -> Path | None:
    """Baixa a primeira foto da tag para o cache. None se falhar."""
    slug = "".join(c if c.isalnum() else "-" for c in query.lower()).strip("-")
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    destino = Path(dest_dir) / f"{slug}.jpg"
    if destino.exists():
        return destino
    try:
        fotos = search(query, per_page=1)
        if not fotos:
            return None
        req = urllib.request.Request(
            portrait_url(fotos[0]),
            headers={"User-Agent": "tiktok-viral-generator/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(destino, "wb") as f:
            f.write(r.read())
        return destino
    except Exception:
        return None


__all__ = ["fetch", "portrait_url", "search"]
