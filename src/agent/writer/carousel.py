"""Roteirista de carrossel: dossie para 5 slides + legenda.

Receita validada dos canais (2026): slide 1 com promessa numerada, revelacao
progressiva com value bomb no meio, slide 5 com conclusao + CTA de save, 10-15
palavras por slide, legenda com pergunta para puxar comentario. Tudo que e
contavel vira portao mecanico aqui; gancho e progressao sao do juiz.

Mesmo laco do roteirista de video: ate 3 tentativas, defeito medido de volta
ao modelo em texto, tentativa reprovada gravada para calibrar o prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from agent.models import (
    CAROUSEL_MAX_WORDS_PER_SLIDE,
    CAROUSEL_SLIDES,
    Carousel,
    Dossier,
    Slide,
)
from agent.ports.llm import LLM, Completion, LLMError, Usage, parse_json_object
from agent.research.grounding import missing_numbers
from agent.writer.humanize import scan as scan_tells
from agent.writer.visuals import brief as visual_brief
from agent.writer.visuals import suggest_pillar, validate_terms
from agent.writer.writer import _resolver_fatos

MAX_TENTATIVAS = 3

SISTEMA = (
    "Voce roteiriza carrosseis de um canal brasileiro dark de tech, IA e "
    "ciencia. Cada slide e uma frase curta que se le em 3 segundos. Voce so "
    "afirma o que esta no dossie que recebe."
)

SCHEMA_CARROSSEL: dict[str, Any] = {
    "type": "object",
    "properties": {
        "slides": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"n": {"type": "integer"},
                                     "headline": {"type": "string"},
                                     "text": {"type": "string"},
                                     "visual": {"type": "string"}},
                      "required": ["n", "headline", "text", "visual"]},
        },
        "caption": {"type": "string"},
        "used_facts": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["slides", "caption", "used_facts"],
}

_DIGITO = re.compile(r"\d")


@dataclass
class CarouselAttempt:
    violations: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    latency_s: float = 0.0


@dataclass
class CarouselReport:
    topic: str
    carousel: Carousel | None = None
    attempts: list[CarouselAttempt] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    refusal: str = ""

    @property
    def ok(self) -> bool:
        return self.carousel is not None

    @property
    def usage(self) -> Usage:
        total = Usage()
        for a in self.attempts:
            total = total + a.usage
        return total

    @property
    def latency_s(self) -> float:
        return round(sum(a.latency_s for a in self.attempts), 3)


def write_carousel(dossier: Dossier, llm: LLM,
                   max_attempts: int = MAX_TENTATIVAS,
                   notes: list[str] | None = None) -> CarouselReport:
    """Escreve o carrossel com correcao propria do que e mecanico."""
    report = CarouselReport(
        topic=dossier.topic,
        model=getattr(llm, "model", ""),
        provider=getattr(llm, "provider", ""),
    )
    from agent.writer.writer import thin_dossier_reason
    report.refusal = thin_dossier_reason(dossier)
    if report.refusal:
        return report

    correcao: list[str] = list(notes or [])
    for _ in range(max_attempts):
        try:
            resposta = llm.complete(
                build_prompt(dossier, correcao),
                system=SISTEMA,
                schema=SCHEMA_CARROSSEL,
                temperature=0.6,
                max_output_tokens=2048,
            )
        except LLMError:
            raise
        tentativa, carrossel = _avaliar(resposta, dossier)
        report.attempts.append(tentativa)
        if not tentativa.violations:
            report.carousel = carrossel
            return report
        correcao = tentativa.violations
    return report


def _avaliar(resposta: Completion, dossier: Dossier
             ) -> tuple[CarouselAttempt, Carousel | None]:
    tentativa = CarouselAttempt(usage=resposta.usage, latency_s=resposta.latency_s)
    if resposta.truncated:
        tentativa.violations.append(
            "a resposta foi cortada por limite de tokens; escreva mais curto")
        return tentativa, None
    try:
        corpo = parse_json_object(resposta.text)
    except LLMError as exc:
        tentativa.violations.append(f"a resposta nao veio como objeto JSON: {exc}")
        return tentativa, None

    usados, fora = _resolver_fatos(corpo.get("used_facts"), dossier.facts)
    try:
        slides = [Slide(n=int(s.get("n", i + 1)),
                        headline=_texto(s.get("headline")),
                        text=_texto(s.get("text")),
                        visual=_texto(s.get("visual")))
                  for i, s in enumerate(corpo.get("slides") or [])]
        carrossel = Carousel(topic=dossier.topic, slides=slides,
                             caption=_texto(corpo.get("caption")), facts=usados)
    except (ValidationError, ValueError, AttributeError) as exc:
        tentativa.violations.append(f"o carrossel nao respeita o contrato: {exc}")
        return tentativa, None

    tentativa.violations.extend(_violacoes(carrossel, dossier, fora))
    return tentativa, (carrossel if not tentativa.violations else None)


def _violacoes(carrossel: Carousel, dossier: Dossier, fora: list[int]) -> list[str]:
    problemas: list[str] = []
    for s in carrossel.slides:
        if s.word_count > CAROUSEL_MAX_WORDS_PER_SLIDE:
            problemas.append(
                f"slide {s.n} tem {s.word_count} palavras (teto "
                f"{CAROUSEL_MAX_WORDS_PER_SLIDE}): slide se le em 3 segundos.")
    s1 = carrossel.slides[0]
    if not _DIGITO.search(f"{s1.headline} {s1.text}"):
        problemas.append(
            "slide 1 sem numero: a promessa numerada ('5 IAs que...') e o que "
            "faz a pessoa arrastar. Sem numero nao ha payoff finito.")
    s5 = carrossel.slides[-1]
    if "salv" not in f"{s5.headline} {s5.text}".lower():
        problemas.append(
            "slide 5 sem CTA de save ('salve'): save/view e o indicador lider "
            "do formato; sem ele o carrossel nao acumula distribuicao.")
    if "?" not in carrossel.caption:
        problemas.append(
            "legenda sem pergunta: a legenda carrega o convite ao comentario, "
            "e comentario e onde o carrossel ganha do video.")
    if fora:
        problemas.append(
            f"used_facts aponta indice que nao existe no dossie: {fora}.")
    if not carrossel.facts:
        problemas.append("used_facts vazio: carrossel tambem ancora em fonte.")
    problemas.extend(
        "visual: " + v for v in validate_terms([s.visual for s in carrossel.slides]))
    fontes = "\n".join(f"{f.claim}\n{f.quote}" for f in dossier.facts)
    texto = "\n".join(f"{s.headline} {s.text}" for s in carrossel.slides)
    # Contagem estrutural (o "5" da promessa) nao e afirmacao factual: sao os
    # proprios slides, verificados acima pela ordem 1-5. So numero acima disso
    # precisa existir no dossie.
    soltos = [n for n in missing_numbers(texto, fontes)
              if not (n.isdigit() and int(n) <= CAROUSEL_SLIDES)]
    if soltos:
        problemas.append(
            f"slide cita numero que nao esta no dossie: {', '.join(soltos)}.")
    tells = scan_tells(texto)
    if tells:
        problemas.append(
            "slide com vicio de IA (" + "; ".join(tells[:3]) + "): reescreva "
            "como fala curta de pessoa.")
    return problemas


def build_prompt(dossier: Dossier, correcoes: list[str] | None = None) -> str:
    fatos = "\n".join(
        f"[{i}] {f.claim}\n    fonte: {f.source_name}"
        for i, f in enumerate(dossier.facts))
    partes = [
        f"TEMA: {dossier.topic}\n",
        f"DOSSIE (use o indice para citar):\n{fatos}\n",
        "TAREFA\nEscreva um carrossel de 5 slides para TikTok photo mode.\n"
        "- slide 1: promessa NUMERADA ('5 IAs que...'). Sem numero, sem swipe.\n"
        "- slides 2-4: revelacao progressiva, um dado novo por slide; o melhor "
        "dado no 3 ou 4 (value bomb).\n"
        "- slide 5: conclusao + 'salve para depois'.\n"
        "- cada slide: headline curta + text de no maximo 15 palavras.\n"
        "- caption: uma linha com a palavra-chave + UMA pergunta.\n"
        "- visual: tag COPIADA da lista de ESTETICA, um pilar so.\n"
        "- used_facts: indices do dossie.\n",
        visual_brief(suggest_pillar(dossier.topic)),
        "REGRAS\n"
        "- So dado do dossie. Sem emoji, sem hashtag no slide.\n"
        "- pt-BR falado, frase curta.",
    ]
    if correcoes:
        partes.append(
            "CORRIJA A TENTATIVA ANTERIOR\n"
            + "\n".join(f"- {c}" for c in correcoes)
            + "\nMantenha o que estava bom e conserte apenas o apontado.")
    return "\n".join(partes)


def _texto(valor: object) -> str:
    return " ".join(str(valor).split()) if isinstance(valor, str) else ""


__all__ = ["CarouselAttempt", "CarouselReport", "build_prompt", "write_carousel"]
