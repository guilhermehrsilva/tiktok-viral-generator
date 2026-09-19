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
class Presenter:
    id: str
    name: str
    role: str
    formats: tuple[str, ...]
    gender: str
    seed: int
    voice_pitch: str
    voice_rate: float
    voice_note: str
    library_voice: str | None
    identity_prompt: str


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
    presenters: dict[str, Presenter] = field(default_factory=dict)
    presenter_formats: tuple[str, ...] = ()
    variation_prompt: str = ""
    variation_slots: dict[str, tuple[str, ...]] = field(default_factory=dict)
    negative_prompt: str = ""

    def accent_for(self, pillar_id: str) -> str:
        """Um acento por peca: o do pilar, ou o verde padrao."""
        pillar = self.pillars.get(pillar_id)
        return pillar.accent if pillar is not None else self.accent_primary

    def presenter_for(self, pillar_id: str) -> Presenter | None:
        """Elenco por formato. Fora dos 4: None -- o video roda sem avatar."""
        for p in self.presenters.values():
            if pillar_id in p.formats:
                return p
        return None


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
    pres = raw.get("presenters", {})
    presenters = {
        c["id"]: Presenter(
            id=c["id"], name=c["name"], role=c["role"],
            formats=tuple(c.get("formats", ())), gender=c.get("gender", ""),
            seed=int(c.get("seed", 0)),
            voice_pitch=c.get("voice", {}).get("pitch", ""),
            voice_rate=float(c.get("voice", {}).get("rate", 1.0)),
            voice_note=c.get("voice", {}).get("note", ""),
            library_voice=c.get("voice", {}).get("library_voice"),
            identity_prompt=c.get("identity_prompt", ""))
        for c in pres.get("cast", [])
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
        presenters=presenters,
        presenter_formats=tuple(pres.get("usage", {}).get("formats", ())),
        variation_prompt=pres.get("variation_prompt", ""),
        variation_slots={k: tuple(v) for k, v in
                         pres.get("variation_slots", {}).items()},
        negative_prompt=pres.get("negative_prompt", ""),
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


def avatar_prompt(presenter_id: str, *, angulo: str = "frontal",
                  expressao: str = "neutra", gesto: str = "parada") -> str:
    """Prompt pronto de geracao do avatar: identidade travada + 3 variaveis.

    So as 3 variaveis mudam por video -- qualquer outro ajuste e deriva do
    rosto e reprova no QA contra os retratos mestres.
    """
    brand = load()
    if presenter_id not in brand.presenters:
        raise ValueError(f"apresentador {presenter_id!r} desconhecido")
    for nome, valor in (("angulo", angulo), ("expressao", expressao),
                        ("gesto", gesto)):
        opcoes = brand.variation_slots.get(nome, ())
        if opcoes and valor not in opcoes:
            raise ValueError(f"{nome} {valor!r} fora de {list(opcoes)}")
    base = brand.variation_prompt
    p = brand.presenters[presenter_id]
    texto = base.replace("{prompt_de_identidade}", p.identity_prompt)
    texto = texto.replace("{frontal | 3/4 esquerda | 3/4 direita}", angulo)
    texto = texto.replace("{neutra | concentrada | uma sobrancelha erguida}",
                          expressao)
    texto = texto.replace("{parada | leve inclinação de cabeça | mão aberta "
                          "na altura do peito}", gesto)
    return texto


__all__ = ["BRAND_JSON", "Brand", "ContentPillar", "Presenter", "avatar_prompt",
           "load", "suggest_content_pillar", "voice_brief"]
