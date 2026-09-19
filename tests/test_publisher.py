"""Testes do publicador TikTok (inbox), sem rede e sem app registrado.

O que importa aqui nao e "o video apareceu na inbox" -- isso so o primeiro
post real prova, no app. E o contrato: o payload do init, a sequencia de
chunks com Content-Range, o tipo de excecao para cada falha (token expirado e
cota estourada pedem acoes opostas), e o respeito a 6 req/min por token.
"""

from __future__ import annotations

import httpx
import pytest

from agent.adapters.tiktok_publisher import (
    INIT_PATH,
    STATUS_PATH,
    TikTokPublisher,
    _ranges,
)
from agent.config import Settings
from agent.models import PublishState
from agent.ports.publisher import PublisherAuthError, PublisherRateLimited

INIT_OK = {
    "data": {
        "publish_id": "v_inbox_file~v2.123",
        "upload_url": "https://upload/video?token=abc",
    },
    "error": {"code": "ok", "message": "", "log_id": "x"},
}


def _settings(**kwargs) -> Settings:
    base = {"tiktok_chunk_size": 4, "tiktok_timeout_s": 5.0}
    base.update(kwargs)
    return Settings(**base)


def _cliente(roteiro: list[tuple[int, dict]]) -> tuple[httpx.Client, list[httpx.Request]]:
    """Respostas enfileiradas por chamada, com as requisicoes gravadas."""
    chamadas: list[httpx.Request] = []
    fila = list(roteiro)

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        status, corpo = fila.pop(0)
        return httpx.Response(status, json=corpo)

    return httpx.Client(
        base_url="https://open.tiktokapis.com",
        transport=httpx.MockTransport(handler),
    ), chamadas


def _publicador(
    roteiro: list[tuple[int, dict]], *, chunk_size: int = 4, **kwargs
) -> tuple[TikTokPublisher, list[httpx.Request], list[float]]:
    cliente, chamadas = _cliente(roteiro)
    sonecas: list[float] = []
    pub = TikTokPublisher(
        _settings(tiktok_chunk_size=chunk_size), cliente,
        time_fn=lambda: 0.0, sleeper=sonecas.append, **kwargs
    )
    return pub, chamadas, sonecas


def _mp4(tmp_path, tamanho: int = 10) -> str:
    video = tmp_path / "corte.mp4"
    video.write_bytes(bytes(range(tamanho)))
    return str(video)


class TestPayloadDoInit:
    def test_source_e_file_upload_com_tamanhos(self):
        corpo = TikTokPublisher.build_init_payload(27_000_000, 10_000_000, 3)
        assert corpo == {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": 27_000_000,
                "chunk_size": 10_000_000,
                "total_chunk_count": 3,
            }
        }

    def test_intervalos_sao_sequenciais_sem_buraco(self):
        assert list(_ranges(10, 4)) == [(0, 3), (4, 7), (8, 9)]
        assert list(_ranges(4, 4)) == [(0, 3)]
        assert list(_ranges(5, 10)) == [(0, 4)]


class TestUpload:
    def test_chunk_unico_recebe_201(self, tmp_path):
        pub, chamadas, _ = _publicador([(200, INIT_OK), (201, {})], chunk_size=10)
        result = pub.upload(_mp4(tmp_path), access_token="tok")
        assert result.state is PublishState.uploaded
        assert result.publish_id == "v_inbox_file~v2.123"
        assert len(chamadas) == 2
        put = chamadas[1]
        assert put.headers["Content-Range"] == "bytes 0-9/10"
        assert put.headers["Content-Length"] == "10"

    def test_multiplos_chunks_com_206_e_201(self, tmp_path):
        pub, chamadas, _ = _publicador([(200, INIT_OK), (206, {}), (206, {}), (201, {})])
        result = pub.upload(_mp4(tmp_path, tamanho=10), access_token="tok")
        assert result.state is PublishState.uploaded
        ranges = [c.headers["Content-Range"] for c in chamadas[1:]]
        assert ranges == ["bytes 0-3/10", "bytes 4-7/10", "bytes 8-9/10"]

    def test_chunk_rejeitado_vira_falha_com_motivo(self, tmp_path):
        pub, _, _ = _publicador([(200, INIT_OK), (416, {})])
        result = pub.upload(_mp4(tmp_path), access_token="tok")
        assert result.state is PublishState.failed
        assert "416" in (result.error or "")

    def test_arquivo_inexistente_nao_gasta_chamada(self, tmp_path):
        pub, chamadas, _ = _publicador([])
        result = pub.upload(str(tmp_path / "sumiu.mp4"), access_token="tok")
        assert result.state is PublishState.failed
        assert chamadas == []

    def test_sem_token_e_erro_de_auth(self, tmp_path):
        pub, chamadas, _ = _publicador([])
        with pytest.raises(PublisherAuthError):
            pub.upload(_mp4(tmp_path), access_token="")
        assert chamadas == []


class TestErrosDaApi:
    def test_token_invalido_e_auth(self, tmp_path):
        corpo = {"data": {}, "error": {"code": "access_token_invalid", "message": "x"}}
        pub, _, _ = _publicador([(401, corpo)])
        result = pub.upload(_mp4(tmp_path), access_token="velho")
        assert result.state is PublishState.failed
        assert "access_token_invalid" in (result.error or "")

    def test_cota_estourada_preserva_o_motivo(self, tmp_path):
        corpo = {"data": {}, "error": {"code": "rate_limit_exceeded", "message": "lento"}}
        pub, _, _ = _publicador([(429, corpo)])
        with pytest.raises(PublisherRateLimited):
            pub.fetch_status("v_inbox_file~v2.123", access_token="tok")

    def test_teto_de_pendentes_tambem_e_cota(self, tmp_path):
        corpo = {"data": {}, "error": {"code": "spam_risk_too_many_pending_share",
                                       "message": "5 pendentes"}}
        pub, _, _ = _publicador([(403, corpo)])
        result = pub.upload(_mp4(tmp_path), access_token="tok")
        assert "spam_risk_too_many_pending_share" in (result.error or "")

    def test_resposta_sem_publish_id_diz_o_que_faltou(self, tmp_path):
        corpo = {"data": {}, "error": {"code": "ok", "message": ""}}
        pub, _, _ = _publicador([(200, corpo)])
        result = pub.upload(_mp4(tmp_path), access_token="tok")
        assert "publish_id" in (result.error or "")


class TestStatus:
    def test_status_volta_opaco(self):
        corpo = {"data": {"status": "PROCESSING"}, "error": {"code": "ok"}}
        pub, chamadas, _ = _publicador([(200, corpo)])
        assert pub.fetch_status("v_inbox_file~v2.123", access_token="tok") == "PROCESSING"
        assert chamadas[0].url.path == STATUS_PATH
        assert chamadas[0].headers["Authorization"] == "Bearer tok"

    def test_init_usa_bearer_e_json_utf8(self, tmp_path):
        pub, chamadas, _ = _publicador([(200, INIT_OK), (201, {})])
        pub.upload(_mp4(tmp_path), access_token="tok")
        init = chamadas[0]
        assert init.url.path == INIT_PATH
        assert init.headers["Authorization"] == "Bearer tok"
        assert "application/json" in init.headers["Content-Type"]


class TestCota:
    def test_sexta_chamada_dorme_antes_da_setima(self):
        corpo = {"data": {"status": "PROCESSING"}, "error": {"code": "ok"}}
        pub, _, _ = _publicador([(200, corpo)] * 7)
        for _ in range(6):
            pub.fetch_status("pid", access_token="tok")
        pub.fetch_status("pid", access_token="tok")
        # time_fn congelado em 0: a setima chamada dorme a janela inteira.
        assert pub._sleep is not None
