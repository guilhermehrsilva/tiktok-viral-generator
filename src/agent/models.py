"""Contratos entre estagios do pipeline.

Cada estagio recebe e devolve um destes modelos. Sao a fronteira que permite
testar um estagio sem levantar os outros, e sao o que fica gravado na memoria.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

# Ritmo de fala medido para narracao pt-BR em video curto. Usado apenas para
# estimativa antes do TTS; a duracao real vem do renderizador.
WORDS_PER_SECOND = 2.5

# Faixa exigida pelo Creator Rewards: video abaixo de 60s nao e elegivel a
# monetizacao, e acima de ~90s a retencao cai sem ganho de receita.
MIN_DURATION_S = 60
MAX_DURATION_S = 90


class Fact(BaseModel):
    """Uma afirmacao factual e a fonte que a sustenta.

    Nao existe Fact sem URL: e o que separa conteudo original de alucinacao, e
    e o que o juiz verifica no criterio 2 da rubrica.
    """

    claim: str = Field(min_length=10)
    source_url: HttpUrl
    source_name: str = Field(min_length=2)


class Dossier(BaseModel):
    """Resultado do estagio de pesquisa: o que sabemos e de onde."""

    topic: str
    facts: list[Fact]
    collected_at: datetime

    @field_validator("facts")
    @classmethod
    def _pelo_menos_um_fato(cls, v: list[Fact]) -> list[Fact]:
        if not v:
            raise ValueError("dossie sem fato nao autoriza roteiro")
        return v

    @property
    def source_urls(self) -> set[str]:
        return {str(f.source_url) for f in self.facts}


class Script(BaseModel):
    """Roteiro pronto para producao.

    `search_terms` vai direto para o parametro `query` do Pexels, sem passar por
    traducao: precisa estar **em ingles** e em **ordem cronologica** casando com
    a narracao, porque o material do primeiro termo abre o video.
    """

    topic: str = Field(min_length=3)
    hook: str = Field(min_length=10, description="primeiros ~1,5s; abre lacuna de informacao")
    body: str = Field(min_length=50)
    closing: str = Field(min_length=10)
    search_terms: list[str] = Field(min_length=3, max_length=12)
    facts: list[Fact] = Field(default_factory=list)

    @field_validator("search_terms")
    @classmethod
    def _termos_em_ascii(cls, v: list[str]) -> list[str]:
        # Heuristica deliberadamente simples: acento em termo de busca quase
        # sempre significa que o modelo respondeu em pt-BR, e o Pexels devolve
        # resultado ruim ou vazio. Falhar aqui e mais barato que renderizar
        # um video com material errado.
        for termo in v:
            if not termo.isascii():
                raise ValueError(
                    f"termo de busca {termo!r} nao e ASCII; o Pexels espera ingles"
                )
            if not termo.strip():
                raise ValueError("termo de busca vazio")
        return v

    @property
    def narration(self) -> str:
        """Texto que o TTS vai falar, na ordem em que sera falado."""
        return "\n\n".join(p.strip() for p in (self.hook, self.body, self.closing))

    @property
    def word_count(self) -> int:
        return len(self.narration.split())

    @property
    def estimated_duration_s(self) -> float:
        """Estimativa pre-TTS. A duracao que vale e a do MP4 renderizado."""
        return self.word_count / WORDS_PER_SECOND

    @property
    def unsourced(self) -> list[str]:
        """Nao implementado aqui de proposito.

        Casar afirmacao com fonte exige julgamento semantico, nao string match:
        e trabalho do juiz (M3), com o dossie em maos. Este modelo so carrega
        os fatos para que o juiz possa fazer isso.
        """
        raise NotImplementedError("verificacao de fonte e responsabilidade do juiz (M3)")


class RenderState(StrEnum):
    processing = "processing"
    complete = "complete"
    failed = "failed"


class RenderResult(BaseModel):
    """O que o renderizador devolve. `duration_s` e medida, nao estimada."""

    state: RenderState
    video_path: str | None = None
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    # Medido com ffprobe. Um MP4 sem trilha de narracao passa em qualquer
    # checagem de dimensao e duracao, e nao serve para nada.
    has_audio: bool = False
    task_id: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _coerencia(self) -> RenderResult:
        if self.state is RenderState.complete and not self.video_path:
            raise ValueError("render completo sem video_path")
        if self.state is RenderState.failed and not self.error:
            raise ValueError("render falhou sem mensagem de erro")
        return self

    @property
    def is_portrait_1080x1920(self) -> bool:
        return (self.width, self.height) == (1080, 1920)

    @property
    def duration_in_monetizable_range(self) -> bool:
        if self.duration_s is None:
            return False
        return MIN_DURATION_S <= self.duration_s <= MAX_DURATION_S


class NewsItem(BaseModel):
    """Materia ja associada a um termo pela propria fonte.

    O Google Trends RSS entrega isso de graca junto de cada tema, o que adianta
    parte do trabalho do pesquisador (M3) sem custar uma requisicao a mais.
    """

    title: str = Field(min_length=3)
    url: HttpUrl
    source_name: str = ""


class Signal(BaseModel):
    """Um termo em alta, como uma fonte o reporta.

    `volume` esta sempre na unidade nativa da fonte -- pontos do HN, buscas
    estimadas do Trends, pageviews da Wikipedia. Nao sao comparaveis entre si e
    o radar nao tenta normalizar: converter escalas diferentes numa nota unica e
    julgamento, e julgamento e trabalho do curador (M2). O radar so coleta e
    mede.

    `velocity` e a unica grandeza comparavel em forma, porque e sempre a mesma
    derivada: unidade por hora. Fica `None` quando a fonte nao permite calcula-la
    -- e `None` significa "desconhecido", nunca zero.
    """

    term: str = Field(min_length=2)
    source: str = Field(min_length=2)
    volume: float = Field(ge=0)
    unit: str = Field(min_length=1)
    velocity: float | None = None
    seen_at: datetime
    url: HttpUrl | None = None
    news_items: list[NewsItem] = Field(default_factory=list)

    @field_validator("term")
    @classmethod
    def _termo_normalizado(cls, v: str) -> str:
        return " ".join(v.split()).strip()

    @property
    def key(self) -> str:
        """Chave estavel para casar a mesma historia entre coletas."""
        return f"{self.source}:{self.term.casefold()}"

    @property
    def has_velocity(self) -> bool:
        return self.velocity is not None
