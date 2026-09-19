"""Escolhe o adaptador de LLM a partir da configuracao.

Existe para que nenhum estagio precise saber qual provedor esta em uso: o
pesquisador recebe uma porta `LLM` pronta e nao importa nada de `adapters/`. E
tambem o unico lugar que sabe qual variavel de ambiente carrega qual chave, o
que mantem a mensagem de erro de chave faltando em um lugar so.
"""

from __future__ import annotations

from agent.config import Settings
from agent.config import settings as default_settings
from agent.ports.llm import LLM, LLMError

PROVEDORES = ("gemini", "groq")


def build_llm(provider: str | None = None, settings: Settings | None = None) -> LLM:
    cfg = settings or default_settings
    nome = (provider or cfg.llm_provider).strip().lower()

    if nome == "gemini":
        from agent.adapters.gemini_free import GeminiFree

        return GeminiFree(
            api_key=cfg.gemini_api_key, model=cfg.gemini_model,
            timeout_s=cfg.llm_timeout_s, thinking_budget=cfg.gemini_thinking_budget,
        )
    if nome == "groq":
        from agent.adapters.groq import Groq

        return Groq(
            api_key=cfg.groq_api_key, model=cfg.groq_model,
            timeout_s=cfg.llm_timeout_s, reasoning_effort=cfg.groq_reasoning_effort,
        )
    raise LLMError(f"provedor de LLM desconhecido: {nome!r}; use um de {PROVEDORES}")


def configured(settings: Settings | None = None) -> list[str]:
    """Provedores que tem chave preenchida, na ordem de preferencia.

    Usado por `agent llm-health` para checar o que da para checar, em vez de
    falhar em quem o usuario nunca configurou.
    """
    cfg = settings or default_settings
    chaves = {"gemini": cfg.gemini_api_key, "groq": cfg.groq_api_key}
    return [p for p in PROVEDORES if chaves[p]]
