"""Sujeito obrigatorio: o roteiro precisa dizer DE QUEM fala.

Falha que o piloto acusou: o video falava de "um modelo" sem nunca dizer o
nome, de onde e nem quem construiu -- e sem nome nao ha busca, nem
credibilidade, nem canal. A causa e estrutural: nada no caminho exigia o
sujeito, entao o modelo generalizava.

O portao e lexical e barato: os identificadores saem do proprio topico
(nome com letra+digito tipo "27B", proprio com 6+ letras tipo "Bonsai").
Numero puro ("5,9") nao e identidade -- e quantidade, e ja tem portao
proprio. Quem construiu vem do dossie via o roteirista (regra de prompt:
diga se o dossie disser, nunca invente).
"""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[A-Za-zÀ-ÿ0-9]+(?:[.,][A-Za-zÀ-ÿ0-9]+)*")

# Categoria gramatical, nao identidade: some do portao, fica no texto.
_STOP = frozenset({
    "modelo", "modelos", "video", "sobre", "como", "para", "com", "uma",
})


def subject_terms(topic: str) -> list[str]:
    """Identificadores do assunto, em ordem, sem repetir (minusculos)."""
    termos: list[str] = []
    for bruto in _TOKEN.findall(topic):
        t = bruto.lower()
        tem_digito = any(c.isdigit() for c in t)
        tem_letra = any(c.isalpha() for c in t)
        if tem_digito and tem_letra:
            pass  # 27b, gpt-4: nome, entra sempre
        elif len(t) < 6 or t in _STOP or not tem_letra:
            continue  # curto, gramatical ou numero puro: nao e identidade
        if t not in termos:
            termos.append(t)
    return termos


def missing_subject(text: str, topic: str, minimum: int = -1) -> list[str]:
    """Identificadores ausentes. `minimum` = quantos precisam aparecer.

    Video pede todos (minimum = total); carrossel pede 1 -- slide tem 12
    palavras e nao comporta a ficha completa, mas precisa ancorar o assunto.
    """
    termos = subject_terms(topic)
    if minimum < 0:
        minimum = len(termos)
    baixa = text.lower()
    ausentes = [t for t in termos if t not in baixa]
    if len(termos) - len(ausentes) >= minimum:
        return []
    return ausentes


__all__ = ["missing_subject", "subject_terms"]
