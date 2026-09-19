"""Adaptador da porta LLM para o Groq (free tier, endpoint compativel com OpenAI).

Existe junto do Gemini desde o M3, e nao depois, porque uma porta com um unico
adaptador nao e porta -- e indirecao. Manter dois desde o inicio e o que prova
que trocar de provedor nao vaza para os estagios, e ja entrega metade do braco
livre do eval do M5.

Diferenca que importa contra o Gemini: aqui nao existe saida estruturada por
schema em todos os modelos. O que existe sempre e `response_format=json_object`,
que garante JSON valido mas **nao** garante o formato pedido. Entao o schema vai
tambem no prompt, como texto, e quem chama valida com Pydantic do mesmo jeito.

Os modelos sao open weights (GPT-OSS, Qwen). A latencia medida aqui e muito menor
que a do Gemini Flash -- 1,0s contra 6,6s na mesma chamada de teste, em
18/09/2026 -- e o custo no free tier e o mesmo zero. Se a escrita em pt-BR
compensa a diferenca e o que o eval do M5 mede; por enquanto e impressao, nao
resultado.

Id de modelo aqui e volatil: o padrao anterior (`llama-3.3-70b-versatile`) foi
descontinuado e devolve 404. Por isso ele vem da configuracao e existe o
`agent llm-health`, que confere contra o provedor em vez de confiar no padrao.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from agent.ports.llm import Completion, LLMBlocked, LLMError, LLMUnavailable, Usage

BASE_URL = "https://api.groq.com/openai/v1"


class Groq:
    provider = "groq"

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        client: httpx.Client | None = None,
        timeout_s: float = 120.0,
        reasoning_effort: str = "",
    ):
        if not api_key:
            raise LLMError("AGENT_GROQ_API_KEY vazia; a chave e gratuita em console.groq.com/keys")
        self.model = model
        self._reasoning_effort = reasoning_effort
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            timeout=httpx.Timeout(timeout_s),
            headers={
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
        )

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        schema: dict | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
    ) -> Completion:
        payload = self.build_payload(
            prompt, system=system, schema=schema, model=self.model,
            temperature=temperature, max_output_tokens=max_output_tokens,
            reasoning_effort=self._reasoning_effort,
        )
        inicio = time.monotonic()
        try:
            r = self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"groq inacessivel: {exc}") from exc
        latencia = round(time.monotonic() - inicio, 3)

        if r.status_code == 429:
            raise LLMUnavailable(f"groq negou cota (429){_retry_after(r)}")
        if r.status_code in (500, 502, 503, 504):
            raise LLMUnavailable(f"groq instavel ({r.status_code})")
        if r.status_code != 200:
            raise LLMError(f"groq devolveu {r.status_code}: {r.text[:300]}")

        try:
            corpo = r.json()
        except ValueError as exc:
            raise LLMError("groq devolveu resposta nao-JSON") from exc

        return self.parse(corpo, model=self.model, latency_s=latencia)

    @staticmethod
    def build_payload(
        prompt: str, *, system: str, schema: dict | None, model: str,
        temperature: float, max_output_tokens: int, reasoning_effort: str = "",
    ) -> dict[str, Any]:
        """Monta o corpo do chat/completions. Separado para ser testavel sem rede."""
        mensagens: list[dict[str, str]] = []
        instrucao = system
        if schema is not None:
            # O modo JSON do endpoint exige a palavra "json" no prompt e nao
            # aceita schema; anexar o schema como texto e o que sobra para pedir
            # um formato. Vai no system para nao competir com o conteudo.
            instrucao = (
                f"{system}\n\n" if system else ""
            ) + (
                "Responda apenas com um objeto json valido, sem texto em volta, "
                "obedecendo exatamente a este schema:\n"
                f"{json.dumps(schema, ensure_ascii=False)}"
            )
        if instrucao:
            mensagens.append({"role": "system", "content": instrucao})
        mensagens.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": mensagens,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if schema is not None:
            payload["response_format"] = {"type": "json_object"}
        if reasoning_effort:
            # Só os modelos de raciocinio aceitam; mandar para os outros devolve
            # 400, por isso o padrao e nao enviar.
            payload["reasoning_effort"] = reasoning_effort
        return payload

    @staticmethod
    def parse(corpo: dict, *, model: str, latency_s: float) -> Completion:
        escolhas = corpo.get("choices") or []
        if not escolhas:
            raise LLMError("groq devolveu resposta sem choice")

        escolha = escolhas[0]
        motivo = str(escolha.get("finish_reason") or "")
        if motivo == "content_filter":
            raise LLMBlocked("groq bloqueou a resposta por filtro de conteudo")

        texto = ((escolha.get("message") or {}).get("content") or "")
        if not texto.strip():
            raise LLMError(f"groq devolveu choice sem conteudo (finish_reason={motivo})")

        uso = corpo.get("usage") or {}
        return Completion(
            text=texto,
            model=str(corpo.get("model") or model),
            provider=Groq.provider,
            usage=Usage(
                input_tokens=int(uso.get("prompt_tokens") or 0),
                output_tokens=int(uso.get("completion_tokens") or 0),
            ),
            latency_s=latency_s,
            finish_reason=motivo,
        )


def _retry_after(r: httpx.Response) -> str:
    valor = r.headers.get("retry-after")
    return f"; tente em {valor}s" if valor else ""
