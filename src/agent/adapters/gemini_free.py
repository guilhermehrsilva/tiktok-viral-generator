"""Adaptador da porta LLM para a API Gemini (free tier do AI Studio).

Caminho padrao do projeto por tres razoes praticas, nao por preferencia:

1. chave gratuita sem cartao, com cota diaria que cobre folgado um video por dia;
2. saida estruturada nativa (`responseSchema`), que e o que impede o pesquisador
   de receber prosa onde esperava uma lista de fatos;
3. pt-BR decente -- o roteirista (M3, fatia 2) escreve narracao falada, e modelo
   que tropeca em concordancia gera audio que soa errado mesmo estando certo.

A cota do free tier e por minuto **e** por dia. Estourar devolve 429, que sobe
como LLMUnavailable: repetir na hora nao resolve e segurar a execucao esperando
a janela abrir custaria mais que perder a fonte.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from agent.ports.llm import Completion, LLMBlocked, LLMError, LLMUnavailable, Usage

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Tipos que o Gemini aceita em responseSchema sao um subconjunto do OpenAPI 3.0,
# com os nomes em maiuscula. JSON Schema puro passa em alguns casos e e recusado
# em outros, entao a traducao e explicita.
_TIPOS = {
    "object": "OBJECT", "array": "ARRAY", "string": "STRING",
    "number": "NUMBER", "integer": "INTEGER", "boolean": "BOOLEAN",
}
# Chaves de JSON Schema que o endpoint recusa com 400 em vez de ignorar.
_CHAVES_RECUSADAS = frozenset({"additionalProperties", "$schema", "title", "default"})


class GeminiFree:
    provider = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        client: httpx.Client | None = None,
        timeout_s: float = 60.0,
    ):
        if not api_key:
            raise LLMError(
                "AGENT_GEMINI_API_KEY vazia; a chave e gratuita em aistudio.google.com/apikey"
            )
        self.model = model
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            timeout=httpx.Timeout(timeout_s),
            headers={"x-goog-api-key": api_key, "content-type": "application/json"},
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
            prompt, system=system, schema=schema,
            temperature=temperature, max_output_tokens=max_output_tokens,
        )
        inicio = time.monotonic()
        try:
            r = self._client.post(f"/models/{self.model}:generateContent", json=payload)
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"gemini inacessivel: {exc}") from exc
        latencia = round(time.monotonic() - inicio, 3)

        if r.status_code == 429:
            raise LLMUnavailable(f"gemini negou cota (429){_retry_after(r)}")
        if r.status_code in (500, 502, 503, 504):
            raise LLMUnavailable(f"gemini instavel ({r.status_code})")
        if r.status_code != 200:
            raise LLMError(f"gemini devolveu {r.status_code}: {r.text[:300]}")

        try:
            corpo = r.json()
        except ValueError as exc:
            raise LLMError("gemini devolveu resposta nao-JSON") from exc

        return self.parse(corpo, model=self.model, latency_s=latencia)

    @staticmethod
    def build_payload(
        prompt: str, *, system: str, schema: dict | None,
        temperature: float, max_output_tokens: int,
    ) -> dict[str, Any]:
        """Monta o corpo do generateContent. Separado para ser testavel sem rede."""
        config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        }
        if schema is not None:
            config["responseMimeType"] = "application/json"
            config["responseSchema"] = to_openapi_schema(schema)

        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        return payload

    @staticmethod
    def parse(corpo: dict, *, model: str, latency_s: float) -> Completion:
        bloqueio = (corpo.get("promptFeedback") or {}).get("blockReason")
        if bloqueio:
            raise LLMBlocked(f"gemini bloqueou o prompt: {bloqueio}")

        candidatos = corpo.get("candidates") or []
        if not candidatos:
            raise LLMError("gemini devolveu resposta sem candidato")

        cand = candidatos[0]
        motivo = str(cand.get("finishReason") or "")
        if motivo.upper() == "SAFETY":
            raise LLMBlocked("gemini bloqueou a resposta por filtro de conteudo")

        partes = (cand.get("content") or {}).get("parts") or []
        texto = "".join(p.get("text", "") for p in partes)
        if not texto.strip():
            # Acontece com MAX_TOKENS logo apos o "thinking": o candidato volta
            # sem parte de texto. Dizer isso e melhor que devolver string vazia
            # e deixar o parser de JSON reclamar de outra coisa.
            raise LLMError(f"gemini devolveu candidato sem texto (finishReason={motivo})")

        uso = corpo.get("usageMetadata") or {}
        return Completion(
            text=texto,
            model=str(corpo.get("modelVersion") or model),
            provider=GeminiFree.provider,
            usage=Usage(
                input_tokens=int(uso.get("promptTokenCount") or 0),
                # O Gemini Flash cobra o raciocinio interno separado do texto
                # devolvido. Os dois saem do mesmo orcamento, entao entram juntos
                # -- ignorar o thinking subestimaria o custo no eval do M5.
                output_tokens=int(uso.get("candidatesTokenCount") or 0)
                + int(uso.get("thoughtsTokenCount") or 0),
            ),
            latency_s=latency_s,
            finish_reason=motivo,
        )


def to_openapi_schema(schema: dict) -> dict:
    """Converte JSON Schema para o dialeto OpenAPI que o Gemini aceita."""
    saida: dict[str, Any] = {}
    for chave, valor in schema.items():
        if chave in _CHAVES_RECUSADAS:
            continue
        if chave == "type" and isinstance(valor, str):
            saida["type"] = _TIPOS.get(valor.lower(), valor.upper())
        elif chave == "properties" and isinstance(valor, dict):
            saida["properties"] = {k: to_openapi_schema(v) for k, v in valor.items()}
            # Sem isso o modelo escolhe a ordem das chaves, e a ordem muda o que
            # ele escreve: pedir a afirmacao antes do numero produz fato solto.
            saida.setdefault("propertyOrdering", list(valor))
        elif chave == "items" and isinstance(valor, dict):
            saida["items"] = to_openapi_schema(valor)
        else:
            saida[chave] = valor
    return saida


def _retry_after(r: httpx.Response) -> str:
    valor = r.headers.get("retry-after")
    return f"; tente em {valor}s" if valor else ""
