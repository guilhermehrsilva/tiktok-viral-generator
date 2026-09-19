"""Carrossel: 5 slides mecanicos, juiz proprio, memoria e PNG local."""

from __future__ import annotations

import json

from agent.adapters.scripted_llm import ScriptedLLM
from agent.judge.carousel import judge_carousel
from agent.memory.store import SignalStore
from agent.models import Carousel
from agent.render.carousel import render_carousel
from agent.writer.carousel import write_carousel
from tests.test_writer import dossie

VISUAIS = ["neural network nodes", "abstract digital plexus",
           "ai deep learning loop", "quantum computing laser",
           "data stream tunnel"]


def slides(headlines=None, texts=None, visuals=None, caption=None) -> str:
    heads = headlines or ["5 dados do Bonsai em 5,9 GB", "Pesa pouco",
                          "Rende muito", "Roda rapido", "Salve para depois"]
    txts = texts or ["Arraste e veja cada numero",
                     "Ocupa 5,9 GB no disco",
                     "Mantem 98,2% do desempenho",
                     "Chega a 143 tokens por segundo",
                     "Salve este resumo para rever"]
    return json.dumps({
        "topic": "Bonsai 2 27B: modelo de 27B em 5,9 GB",
        "slides": [{"n": i + 1, "headline": h, "text": t,
                    "visual": (visuals or VISUAIS)[i]}
                   for i, (h, t) in enumerate(zip(heads, txts, strict=True))],
        "caption": caption or "Modelo pequeno e forte: qual numero te surpreendeu?",
        "used_facts": [0, 1, 2],
    })


def parecer(**notas: int) -> str:
    return json.dumps({
        c: {"reason": f"motivo {c}", "score": notas.get(c, 2)}
        for c in ("hook", "fonte", "cta")})


class TestRoteirista:
    def test_valido_na_primeira(self):
        report = write_carousel(dossie(), ScriptedLLM(responses=[slides()]))
        assert report.ok and report.carousel is not None
        assert [s.n for s in report.carousel.slides] == [1, 2, 3, 4, 5]

    def test_slide_longo_volta_com_o_teto(self):
        longo = ["dado"] * 4 + [" ".join(["palavra"] * 20)]
        llm = ScriptedLLM(responses=[slides(texts=longo), slides()])
        report = write_carousel(dossie(), llm)
        assert report.ok
        assert any("teto 15" in v for v in report.attempts[0].violations)

    def test_slide1_sem_numero_reprova(self):
        heads = ["Resumo do modelo", "Pesa pouco", "Rende muito",
                 "Roda rapido", "Salve para depois"]
        llm = ScriptedLLM(responses=[slides(headlines=heads), slides()])
        report = write_carousel(dossie(), llm)
        assert report.ok
        assert any("numero" in v for v in report.attempts[0].violations)

    def test_slide5_sem_save_reprova(self):
        heads = ["5 dados do modelo", "Pesa pouco", "Rende muito",
                 "Roda rapido", "Fim"]
        txts = ["Arraste", "Ocupa 5,9 GB", "Mantem 98,2%", "143 por segundo",
                "Obrigado por ler"]
        llm = ScriptedLLM(responses=[
            slides(headlines=heads, texts=txts), slides()])
        report = write_carousel(dossie(), llm)
        assert report.ok
        assert any("save" in v for v in report.attempts[0].violations)

    def test_legenda_sem_pergunta_reprova(self):
        llm = ScriptedLLM(responses=[
            slides(caption="Resumo do modelo pequeno."), slides()])
        report = write_carousel(dossie(), llm)
        assert report.ok
        assert any("pergunta" in v for v in report.attempts[0].violations)

    def test_visual_fora_do_pool_reprova(self):
        llm = ScriptedLLM(responses=[
            slides(visuals=["innovation"] * 5), slides()])
        report = write_carousel(dossie(), llm)
        assert report.ok
        assert any("vocabulario" in v for v in report.attempts[0].violations)


class TestJuiz:
    def test_aprova_com_rubrica_boa(self):
        carrossel = Carousel.model_validate_json(slides())
        report = judge_carousel(carrossel, dossie(),
                                ScriptedLLM(responses=[parecer()]))
        assert report.approved and report.review is not None
        assert report.review.total == 8

    def test_politica_reprova_sem_modelo(self):
        txts = ["Arraste e veja", "Morte no laboratorio", "Mantem 98,2%",
                "143 por segundo", "Salve este resumo"]
        carrossel = Carousel.model_validate_json(slides(texts=txts))
        llm = ScriptedLLM(responses=[])
        report = judge_carousel(carrossel, dossie(), llm)
        assert not report.approved and llm.calls == []
        assert report.review is not None and report.review.short_circuited


class TestMemoria:
    def test_ida_e_volta_com_parecer(self, tmp_path):
        from agent.judge.carousel import judge_carousel as jc
        store = SignalStore(tmp_path / "agent.db")
        carrossel = Carousel.model_validate_json(slides())
        review = jc(carrossel, dossie(),
                    ScriptedLLM(responses=[parecer()])).review
        linha = store.record_carousel(
            carrossel, model="m", provider="p", usage=(10, 5),
            latency_s=1.0, attempts=[], review=review)
        assert store.latest_carousel().topic == carrossel.topic
        assert store.list_carousels()[0]["approved"] == 1
        assert linha == store.latest_carousel_id(carrossel.topic)


class TestSlides:
    def test_cinco_png_1080x1920(self, tmp_path):
        from PIL import Image
        carrossel = Carousel.model_validate_json(slides())
        saidas = render_carousel(carrossel, tmp_path / "car",
                                 font_path=None)
        assert len(saidas) == 5 and (tmp_path / "car" / "caption.txt").exists()
        for s in saidas:
            with Image.open(s) as img:
                assert img.size == (1080, 1920)
