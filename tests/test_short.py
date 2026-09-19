"""Modo short (~15s, alcance): faixa propria, loop no fechamento, sem polish quebrado."""

from __future__ import annotations

import json

from agent.adapters.scripted_llm import ScriptedLLM
from agent.judge.judge import _notas_medidas
from agent.models import Script
from agent.writer.writer import Screenwriter, build_prompt
from tests.test_writer import dossie

TERMOS_SHORT = ["neural network nodes", "data stream tunnel"]


def resposta_short(total: int = 40) -> str:
    hook = "Um modelo gigante cabe no seu bolso?"
    closing = "Gigante no bolso: sera que cabe?"
    fixos = len((hook + " " + closing).split())
    return json.dumps({
        "hook": hook,
        "body": " ".join(["detalhe"] * max(total - fixos, 1)),
        "closing": closing,
        "search_terms": TERMOS_SHORT,
        "used_facts": [0],
    })


class TestShort:
    def test_faixa_curta_aprova_40_palavras(self):
        report = Screenwriter(ScriptedLLM(responses=[resposta_short()])).write(
            dossie(), mode="short", polish=False)
        assert report.ok
        assert report.script is not None and report.script.format == "short"
        assert 30 <= report.script.word_count <= 50

    def test_180_palavras_reprova_no_modo_short(self):
        from tests.test_writer import resposta as resposta_long
        report = Screenwriter(ScriptedLLM(responses=[resposta_long()] * 3)).write(
            dossie(), mode="short", polish=False)
        assert not report.ok

    def test_termos_de_longo_sao_muitos_para_short(self):
        report = Screenwriter(ScriptedLLM(responses=[
            resposta_short().replace('"data stream tunnel"',
                                     '"a", "b", "c", "d", "e", "f"'),
            resposta_short()])).write(dossie(), mode="short", polish=False)
        assert report.ok and len(report.attempts) == 2

    def test_prompt_pede_loop_e_faixa(self):
        texto = build_prompt(dossie(), None, "short")
        assert "replay" in texto and "30" in texto and "50" in texto

    def test_modo_desconhecido_falha_cedo(self):
        import pytest
        with pytest.raises(ValueError):
            Screenwriter(ScriptedLLM(responses=[])).write(dossie(), mode="tv")

    def test_duracao_medida_por_formato(self):
        curta = Script(topic="Tema curto de teste", hook="h " * 5, body="b " * 25, closing="c " * 5,
                       search_terms=["neural network nodes", "data stream tunnel"],
                       format="short")
        (duracao, _) = _notas_medidas(curta)
        assert duracao.score == 2  # ~14s na faixa 10-20s
