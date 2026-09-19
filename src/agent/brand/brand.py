"""Vetor de marca: carrega `brand/brand.json` e distribui para as camadas.

Toda camada agentica le daqui, ninguem copia valor para dentro do codigo:
cor, tag, formula de gancho e hashtag existem em UM lugar. Se o guia mudar,
muda o JSON e os testes de conformidade acusam onde o codigo divergiu.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from agent.config import PROJECT_ROOT

BRAND_JSON = PROJECT_ROOT / "brand" / "brand.json"


@dataclass(frozen=True)
class ContentPillar:
    id: str
    tag: str
    accent: str
    duration: str
    hook_formula: str
    example: str
    beats: tuple[str, ...]
    visual: str
    cta: str
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class Brand:
    name: str
    handle: str
    tagline: str
    bio_default: str
    background: str
    surface: str
    ink: str
    muted: str
    accent_primary: str
    accent_secondary: str
    hashtags: tuple[str, ...]
    pillars: dict[str, ContentPillar] = field(default_factory=dict)
    banned: tuple[str, ...] = ()

    def accent_for(self, pillar_id: str) -> str:
        """Um acento por peca: o do pilar, ou o verde padrao."""
        pillar = self.pillars.get(pillar_id)
        return pillar.accent if pillar is not None else self.accent_primary


@lru_cache(maxsize=1)
def load(path: str | Path = BRAND_JSON) -> Brand:
    """O vetor de marca. Falha alto se o JSON sumir: marca ausente nao gera."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    pillars = {
        p["id"]: ContentPillar(
            id=p["id"], tag=p["tag"], accent=p["accent"], duration=p["duration"],
            hook_formula=p["hook_formula"], example=p["example"],
            beats=tuple(p["beats"]), visual=p["visual"], cta=p["cta"],
            keywords=tuple(p.get("keywords", ())))
        for p in raw["pillars"]
    }
    return Brand(
        name=raw["identity"]["name"],
        handle=raw["identity"]["handle"],
        tagline=raw["identity"]["tagline"],
        bio_default=raw["identity"]["bio_default"],
        background=raw["palette"]["background"],
        surface=raw["palette"]["surface"],
        ink=raw["palette"]["ink"],
        muted=raw["palette"].get("muted", "#8B93A1"),
        accent_primary=raw["palette"]["accent_primary"],
        accent_secondary=raw["palette"]["accent_secondary"],
        hashtags=tuple(raw["caption"]["hashtags"]),
        pillars=pillars,
        banned=tuple(raw["voice"]["banned"]),
    )


def voice_brief() -> str:
    """Bloco de voz da marca para o system prompt do roteirista."""
    return (
        "VOZ SEU CANAL (@seucanal): informativo e preciso, provocador sem "
        "ser raivoso, enigmatico no gancho, futurista no fechamento. "
        "Uma ideia por video. Maximo um numero por frase. Gancho com ate 12 "
        "palavras. Nunca prometa o que o video nao entrega. "
        "Nunca emoji, nunca 'fala galera', nunca 'se inscreva'.")


def suggest_content_pillar(topic: str) -> str:
    """Pilar de conteudo pelo assunto. Orientacao; o roteirista escolhe."""
    brand = load()
    baixo = topic.lower()
    pontos: dict[str, int] = {}
    for pid, p in brand.pillars.items():
        pontos[pid] = sum(1 for kw in p.keywords if kw in baixo)
    melhor = max(sorted(pontos), key=lambda pid: pontos[pid])
    return melhor if pontos[melhor] else "news"


__all__ = ["BRAND_JSON", "Brand", "ContentPillar", "load", "suggest_content_pillar",
           "voice_brief"]
