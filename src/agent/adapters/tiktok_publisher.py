"""Adaptador da porta Publisher para a Content Posting API do TikTok (inbox).

Fluxo, conforme a referencia `Upload` da API (atualizada em 04/08/2026):

1. `POST /v2/post/publish/inbox/video/init/` com `source_info` -> `publish_id`
   + `upload_url` (vale por 1h).
2. `PUT` do binario no `upload_url`, em chunks sequenciais com `Content-Range`.
   A API responde 206 por chunk parcial e 201 no ultimo.
3. Opcional: `POST /v2/post/publish/status/fetch/` com o `publish_id`.

Limites honrados aqui, nao na chamada (guia "Media Transfer" da API):
`total_chunk_count` e `video_size // chunk_size` (piso, nao teto); cada chunk
de 5 MB a 64 MB, exceto o ultimo, que absorve o resto (ate 128 MB); abaixo de
5 MB sobe inteiro com `chunk_size` igual ao arquivo; minimo 1, maximo 1000
chunks, sempre sequenciais.

O que este adaptador NAO faz, de proposito: titulo, descricao e `is_aigc` nao
existem no endpoint inbox -- tentar envia-los seria 400. Rotular como AIGC e
etapa manual no app, e a CLI cobra isso em vez de fingir que a API resolve.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from agent.config import Settings
from agent.config import settings as default_settings
from agent.models import PublishResult, PublishState
from agent.ports.publisher import (
    PublisherAuthError,
    PublisherError,
    PublisherRateLimited,
)

BASE_URL = "https://open.tiktokapis.com"
INIT_PATH = "/v2/post/publish/inbox/video/init/"
STATUS_PATH = "/v2/post/publish/status/fetch/"

# Abaixo disto, chunk unico com o tamanho do arquivo inteiro.
SINGLE_CHUNK_MAX = 5 * 1024 * 1024
# Acima disto, a API exige mais de um chunk.
MULTI_CHUNK_MIN = 64 * 1024 * 1024
MAX_CHUNKS = 1000

# 6 req/min por token = 1 a cada 10s. So contam chamadas a API (init, status);
# o PUT dos bytes vai para o host de upload, fora dessa cota.
RATE_LIMIT_PER_MINUTE = 6
RATE_WINDOW_S = 60.0


class TikTokPublisher:
    """Implementa a porta Publisher via HTTP contra a API oficial."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        *,
        time_fn: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ):
        self.settings = settings or default_settings
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            timeout=httpx.Timeout(self.settings.tiktok_timeout_s),
        )
        self._now = time_fn or time.monotonic
        self._sleep = sleeper or time.sleep
        self._api_calls: list[float] = []

    # ------------------------------------------------------------------ upload

    def upload(self, video_path: str, *, access_token: str) -> PublishResult:
        """Sobe o MP4 para a inbox e devolve o `publish_id` para rastrear."""
        if not access_token:
            raise PublisherAuthError(
                "sem access_token; autorize o app no TikTok e exporte AGENT_TIKTOK_ACCESS_TOKEN"
            )
        path = Path(video_path)
        if not path.is_file():
            return PublishResult(
                state=PublishState.failed,
                video_path=video_path,
                error=f"arquivo nao encontrado: {video_path}",
            )
        blob = path.read_bytes()
        if not blob:
            return PublishResult(
                state=PublishState.failed,
                video_path=video_path,
                error=f"arquivo vazio: {video_path}",
            )
        chunk_size, total_chunks = self._plan(len(blob))

        try:
            publish_id, upload_url = self._init(
                access_token,
                video_size=len(blob),
                chunk_size=chunk_size,
                total_chunks=total_chunks,
            )
            self._send_chunks(upload_url, blob, chunk_size, total_chunks)
        except PublisherError as exc:
            return PublishResult(
                state=PublishState.failed, video_path=video_path, error=str(exc)
            )
        return PublishResult(
            state=PublishState.uploaded, publish_id=publish_id, video_path=video_path
        )

    def fetch_status(self, publish_id: str, *, access_token: str) -> str:
        """Estado atual do post, como a API reporta (string opaca)."""
        if not access_token:
            raise PublisherAuthError("sem access_token")
        self._throttle()
        try:
            r = self._client.post(
                STATUS_PATH,
                json={"publish_id": publish_id},
                headers=self._auth(access_token),
            )
        except httpx.HTTPError as exc:
            raise PublisherError(f"falha de rede no status: {exc}") from exc
        corpo = _corpo(r)
        _checar_erro(corpo, status_http=r.status_code)
        try:
            return str(corpo["data"]["status"])
        except (KeyError, TypeError) as exc:
            raise PublisherError(
                f"resposta de status sem data.status: {corpo}"
            ) from exc

    # ------------------------------------------------------------------- init

    def _init(
        self, access_token: str, *, video_size: int, chunk_size: int, total_chunks: int
    ) -> tuple[str, str]:
        self._throttle()
        try:
            r = self._client.post(
                INIT_PATH,
                json=self.build_init_payload(video_size, chunk_size, total_chunks),
                headers={
                    **self._auth(access_token),
                    "Content-Type": "application/json; charset=UTF-8",
                },
            )
        except httpx.HTTPError as exc:
            raise PublisherError(f"falha de rede no init: {exc}") from exc
        corpo = _corpo(r)
        _checar_erro(corpo, status_http=r.status_code)
        try:
            return str(corpo["data"]["publish_id"]), str(corpo["data"]["upload_url"])
        except (KeyError, TypeError) as exc:
            raise PublisherError(
                f"resposta do init sem publish_id/upload_url: {corpo}"
            ) from exc

    @staticmethod
    def build_init_payload(
        video_size: int, chunk_size: int, total_chunks: int
    ) -> dict[str, Any]:
        """Corpo do init, separado para ser testavel sem rede."""
        return {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            }
        }

    # -------------------------------------------------------------------- PUT

    def _send_chunks(
        self, upload_url: str, blob: bytes, chunk_size: int, total_chunks: int
    ) -> None:
        total = len(blob)
        intervalos = chunk_ranges(total, chunk_size, total_chunks)
        for i, (primeiro, ultimo) in enumerate(intervalos):
            pedaço = blob[primeiro : ultimo + 1]
            ultimo_esperado = 201 if i == len(intervalos) - 1 else 206
            try:
                r = self._client.put(
                    upload_url,
                    content=pedaço,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(pedaço)),
                        "Content-Range": f"bytes {primeiro}-{ultimo}/{total}",
                    },
                )
            except httpx.HTTPError as exc:
                raise PublisherError(f"falha de rede no chunk {i + 1}: {exc}") from exc
            if r.status_code == 416:
                raise PublisherError(
                    f"chunk {i + 1} rejeitado (416): Content-Range fora do progresso"
                )
            if r.status_code >= 500:
                raise PublisherError(
                    f"erro do TikTok no chunk {i + 1} (HTTP {r.status_code}): tente de novo"
                )
            if r.status_code != ultimo_esperado:
                raise PublisherError(
                    f"chunk {i + 1} devolveu HTTP {r.status_code}, esperado {ultimo_esperado}"
                )

    # ------------------------------------------------------------------ apoio

    def _plan(self, total: int) -> tuple[int, int]:
        """`(chunk_size, total_chunk_count)` segundo o guia "Media Transfer".

        Abaixo de 5 MB: inteiro, `chunk_size` igual ao arquivo. Acima: piso da
        divisao, com o ultimo chunk absorvendo o resto (sempre < 2x o chunk, e
        o chunk nunca passa de 64 MB, entao o teto de 128 MB do ultimo vale).
        Configuracao fora da faixa 5-64 MB e trazida para dentro: chunk menor
        que 5 MB seria recusado chunk a chunk no servidor.
        """
        if total <= SINGLE_CHUNK_MAX:
            return total, 1
        size = min(max(int(self.settings.tiktok_chunk_size), SINGLE_CHUNK_MAX),
                   MULTI_CHUNK_MIN)
        # Teto de 1000 chunks: aumenta o chunk em vez de estourar a contagem.
        if total / size > MAX_CHUNKS:
            size = -(-total // MAX_CHUNKS)
        return size, max(1, total // size)

    def _chunk_size(self, total: int) -> int:
        return self._plan(total)[0]

    def _throttle(self) -> None:
        """Dorme o necessario para nao passar de 6 req/min por token.

        `time_fn` e `sleeper` sao injetaveis para o teste nao dormir de verdade.
        """
        agora = self._now()
        self._api_calls = [t for t in self._api_calls if agora - t < RATE_WINDOW_S]
        if len(self._api_calls) >= RATE_LIMIT_PER_MINUTE:
            espera = RATE_WINDOW_S - (agora - self._api_calls[0])
            if espera > 0:
                self._sleep(espera)
                agora = self._now()
                self._api_calls = [t for t in self._api_calls if agora - t < RATE_WINDOW_S]
        self._api_calls.append(agora)

    @staticmethod
    def _auth(access_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}


def chunk_ranges(total: int, chunk_size: int, total_chunks: int
                 ) -> list[tuple[int, int]]:
    """Intervalos [primeiro, ultimo] inclusivos, sequenciais, sem buraco.

    Os `total_chunks - 1` primeiros tem exatamente `chunk_size`; o ultimo vai
    ate o fim do arquivo, absorvendo o resto -- e o `total_chunk_count` do init
    que manda, nao o teto da divisao.
    """
    return [
        (i * chunk_size,
         (i + 1) * chunk_size - 1 if i < total_chunks - 1 else total - 1)
        for i in range(total_chunks)
    ]


def _corpo(resposta: httpx.Response) -> dict[str, Any]:
    try:
        corpo = resposta.json()
    except ValueError as exc:
        raise PublisherError(
            f"resposta nao-JSON da API (HTTP {resposta.status_code})"
        ) from exc
    return corpo if isinstance(corpo, dict) else {}


def _checar_erro(corpo: dict[str, Any], *, status_http: int) -> None:
    erro = corpo.get("error") or {}
    code = erro.get("code", "ok")
    mensagem = erro.get("message", "")
    if code == "ok" and status_http == 200:
        return
    if code in ("access_token_invalid", "scope_not_authorized"):
        raise PublisherAuthError(
            f"{code}: {mensagem or 'token invalido ou sem escopo video.upload'}"
        )
    if code == "rate_limit_exceeded" or status_http == 429:
        raise PublisherRateLimited(
            f"{code}: {mensagem or 'cota de 6 req/min estourada'}"
        )
    if code in ("spam_risk_too_many_pending_share", "spam_risk_user_banned_from_posting"):
        raise PublisherRateLimited(f"{code}: {mensagem}")
    raise PublisherError(f"{code} (HTTP {status_http}): {mensagem}")
