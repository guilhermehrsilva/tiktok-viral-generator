"""Roteirista: de um dossie gravado para um Script pronto para o renderizador.

O estagio tem duas metades de natureza diferente, e misturar as duas e o erro
que este arquivo evita.

A primeira e **julgamento**: hook que abre lacuna, ponto de vista proprio,
portugues falado. Isso e trabalho do juiz (fatia 3), com rubrica, e nao da para
decidir por regra.

A segunda e **mecanica**: contar palavra, conferir se o termo de busca esta
em ASCII e saiu do vocabulario visual do canal (um pilar so), conferir se o
indice de fato existe no dossie. Isso nao precisa de juiz
nenhum, e gastar uma rodada de revisao do juiz com erro de contagem seria
desperdicio de cota. Por isso o roteirista tem seu proprio laco de correcao, com
o defeito medido devolvido ao modelo em texto, e so entrega ao juiz um roteiro
que ja passa no que e verificavel.

A faixa de duracao e requisito de monetizacao, nao gosto: video abaixo de 60s
nao e elegivel ao Creator Rewards. Ela e estimada aqui pelo ritmo de fala
(WORDS_PER_SECOND) e **medida de verdade** so depois do TTS, pelo renderizador --
e e a medida que manda.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from agent.brand.brand import voice_brief
from agent.brand.checks import check_emoji_bordao, check_hook, check_numbers
from agent.models import (
    MAX_DURATION_S,
    MIN_DURATION_S,
    WORDS_PER_SECOND,
    Dossier,
    Fact,
    Script,
)
from agent.ports.llm import LLM, Completion, LLMError, Usage, parse_json_object
from agent.research.grounding import missing_numbers
from agent.research.subject import missing_subject
from agent.writer.humanize import humanize as humanize_narration
from agent.writer.visuals import brief as visual_brief
from agent.writer.visuals import suggest_pillar, validate_terms

# Faixa de palavras que corresponde a faixa de duracao exigida.
MIN_PALAVRAS = int(MIN_DURATION_S * WORDS_PER_SECOND)
MAX_PALAVRAS = int(MAX_DURATION_S * WORDS_PER_SECOND)

# short nao monetiza (15s << 60s): a funcao dele e alcance, nao receita.
# ~40 palavras a 2,5/s; final em loop para o replay automatico.
BANDS: dict[str, tuple[int, int]] = {
    "long": (MIN_PALAVRAS, MAX_PALAVRAS),
    "short": (30, 50),
}
TERMS_PER_MODE: dict[str, tuple[int, int]] = {
    "long": (4, 8),
    "short": (2, 4),
}

# "[0]", "[1, 2]": o indice do fato echoado dentro do texto. Medido na primeira
# execucao real (18/09/2026): o modelo escreveu "...no seu projeto [0]." e
# "...em um projeto [0, 3]." -- e o TTS leria "zero" e "um" em voz alta.
_MARCADOR_DE_CITACAO = re.compile(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]")

# Abaixo disto o dossie nao sustenta 60 segundos de narracao. Medido: um dossie
# de 4 fatos tirados de UMA frase de changelog levou o roteirista a tres
# tentativas, todas entre 104 e 157 palavras, sem nunca alcancar as 150 -- porque
# nao havia assunto, e nao porque a instrucao estava ruim.
MIN_FATOS_PARA_ROTEIRO = 3

# Tentativas totais, contando a primeira. Duas correcoes bastam para defeito
# mecanico; se o modelo nao acerta a contagem em tres tentativas, o problema nao
# e a instrucao, e insistir so queima cota do free tier.
MAX_TENTATIVAS = 3

SISTEMA = (
    "Voce e roteirista de um canal brasileiro de tech, IA e ciencia. Escreve para "
    "ser ouvido, nao lido: frase curta, voz ativa, zero jargao nao explicado. "
    "Voce so afirma o que esta no dossie que recebe. Numero que nao esta no "
    "dossie nao entra no roteiro, nem como aproximacao."
)

SCHEMA_ROTEIRO: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "body": {"type": "string"},
        "closing": {"type": "string"},
        "search_terms": {"type": "array", "items": {"type": "string"}},
        "used_facts": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["hook", "body", "closing", "search_terms", "used_facts"],
}


@dataclass
class Attempt:
    """Uma tentativa e o que ela violou. Vazio significa que ela foi aceita.

    `narration` guarda o texto reprovado. Sem ele, entender POR QUE um portao
    reprovou exige rodar de novo e pagar a cota outra vez -- foi o que aconteceu
    na primeira execucao real, com um portao acusando "numero 0, 1, 2" sem que
    houvesse como ver de onde os numeros vinham.
    """

    violations: list[str] = field(default_factory=list)
    word_count: int = 0
    narration: str = ""
    usage: Usage = field(default_factory=Usage)
    latency_s: float = 0.0


@dataclass
class WriteReport:
    """O roteiro, as tentativas que precisaram acontecer, e o custo de todas.

    As tentativas ficam gravadas porque elas dizem onde o prompt esta fraco: se
    toda execucao gasta duas rodadas para acertar a contagem de palavras, o
    defeito esta na instrucao, nao no modelo -- e isso so aparece se o intervalo
    for registrado em vez de descartado no sucesso.
    """

    topic: str
    script: Script | None = None
    attempts: list[Attempt] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    # Passada de humanizacao apos o aceite mecanico. Nao e tentativa: nao
    # reprova, so melhora -- ou mantem o original com motivo.
    humanized: bool = False
    humanize_notes: list[str] = field(default_factory=list)
    humanize_usage: Usage = field(default_factory=Usage)
    humanize_latency_s: float = 0.0
    # Motivo de nem ter tentado. Diferente de tentativa reprovada: aqui nenhuma
    # chamada foi feita, e o custo e zero.
    refusal: str = ""

    @property
    def ok(self) -> bool:
        return self.script is not None

    @property
    def usage(self) -> Usage:
        total = Usage()
        for a in self.attempts:
            total = total + a.usage
        return total + self.humanize_usage

    @property
    def latency_s(self) -> float:
        return round(
            sum(a.latency_s for a in self.attempts) + self.humanize_latency_s, 3)

    @property
    def violations(self) -> list[str]:
        """Violacoes da ultima tentativa: o motivo de ter falhado."""
        return self.attempts[-1].violations if self.attempts else []


class Screenwriter:
    def __init__(self, llm: LLM, max_attempts: int = MAX_TENTATIVAS):
        self._llm = llm
        self._max_attempts = max_attempts

    def write(self, dossier: Dossier, notes: list[str] | None = None,
              mode: str = "long", polish: bool = True) -> WriteReport:
        """Escreve o roteiro. `notes` sao as notas de revisao do juiz.

        Elas entram no mesmo canal das violacoes mecanicas -- o modelo recebe uma
        lista de defeitos a corrigir e nao precisa saber qual deles foi contado e
        qual foi julgado.
        """
        if mode not in BANDS:
            raise ValueError(f"modo desconhecido: {mode!r}; use long ou short")
        report = WriteReport(
            topic=dossier.topic,
            model=getattr(self._llm, "model", ""),
            provider=getattr(self._llm, "provider", ""),
        )

        report.refusal = thin_dossier_reason(dossier)
        if report.refusal:
            # Medir antes de pagar, como o curador e o juiz fazem: dossie que nao
            # sustenta 60s de narracao nao vira roteiro por insistencia, e tentar
            # tres vezes so gastaria cota para chegar na mesma parede.
            return report

        correcao: list[str] = list(notes or [])

        for _ in range(self._max_attempts):
            try:
                resposta = self._llm.complete(
                    build_prompt(dossier, correcao, mode),
                    system=SISTEMA,
                    schema=SCHEMA_ROTEIRO,
                    temperature=0.6,
                    max_output_tokens=2048,
                )
            except LLMError:
                # Cota estourada ou filtro de conteudo: nao ha o que corrigir no
                # prompt, entao sobe para quem chamou. Defeito de forma na
                # resposta e tratado em _avaliar, como violacao corrigivel.
                raise

            tentativa, script = self._avaliar(resposta, dossier, mode)
            report.attempts.append(tentativa)
            if not tentativa.violations:
                report.script = script
                if polish and script is not None:
                    self._polir(report, script, dossier, mode)
                return report
            correcao = tentativa.violations

        return report

    def _polir(self, report: WriteReport, script: Script,
               dossier: Dossier, mode: str) -> None:
        """Passada de humanizacao. Original intacto se a reescrita falhar."""
        minimo, maximo = BANDS[mode]
        rel = humanize_narration(
            script.hook, script.body, script.closing, dossier,
            self._llm, minimo, maximo)
        report.humanize_usage = rel.usage
        report.humanize_latency_s = rel.latency_s
        report.humanize_notes = rel.notes
        if rel.changed:
            report.script = Script(
                topic=script.topic, hook=rel.hook, body=rel.body,
                closing=rel.closing, search_terms=script.search_terms,
                facts=script.facts, format=script.format)
            report.humanized = True

    # ------------------------------------------------------------------ avaliacao

    def _avaliar(self, resposta: Completion, dossier: Dossier,
                 mode: str = "long") -> tuple[Attempt, Script | None]:
        tentativa = Attempt(usage=resposta.usage, latency_s=resposta.latency_s)
        if resposta.truncated:
            tentativa.violations.append(
                "a resposta foi cortada por limite de tokens; escreva mais curto"
            )
            return tentativa, None

        try:
            corpo = parse_json_object(resposta.text)
        except LLMError as exc:
            # Defeito de forma, nao de provedor: o laco conserta isso, e gastar
            # uma rodada do juiz com JSON quebrado seria desperdicio de cota.
            tentativa.violations.append(f"a resposta nao veio como objeto JSON: {exc}")
            return tentativa, None

        usados, fora = _resolver_fatos(corpo.get("used_facts"), dossier.facts)

        try:
            script = Script(
                topic=dossier.topic,
                hook=_texto(corpo.get("hook")),
                body=_texto(corpo.get("body")),
                closing=_texto(corpo.get("closing")),
                search_terms=_termos(corpo.get("search_terms")),
                facts=usados,
                format=mode,
            )
        except ValidationError as exc:
            tentativa.violations.extend(_violacoes_de_contrato(exc))
            return tentativa, None

        tentativa.word_count = script.word_count
        tentativa.narration = script.narration
        tentativa.violations.extend(_violacoes_mecanicas(script, dossier, fora, mode))
        return tentativa, (script if not tentativa.violations else None)


def _violacoes_mecanicas(script: Script, dossier: Dossier, fora: list[int],
                         mode: str = "long") -> list[str]:
    """O que da para conferir sem julgamento. Texto vai de volta ao modelo."""
    problemas: list[str] = []
    minimo, maximo = BANDS[mode]
    tmin, tmax = TERMS_PER_MODE[mode]

    marcadores = _MARCADOR_DE_CITACAO.findall(script.narration)
    if marcadores:
        problemas.append(
            f"a narracao contem marcador de citacao ({', '.join(marcadores[:4])}). "
            "O texto e falado por um sintetizador: ele leria esses numeros em voz "
            "alta. O indice do fato vai APENAS no campo used_facts."
        )

    if not (minimo <= script.word_count <= maximo):
        alvo = (minimo + maximo) // 2
        problemas.append(
            f"a narracao tem {script.word_count} palavras "
            f"(~{script.estimated_duration_s:.0f}s) e precisa ter entre {minimo} e "
            f"{maximo}. Reescreva com cerca de {alvo} palavras."
        )

    if not (tmin <= len(script.search_terms) <= tmax):
        problemas.append(
            f"search_terms tem {len(script.search_terms)} termos e o modo {mode} "
            f"pede entre {tmin} e {tmax}, em ordem cronologica."
        )

    if fora:
        problemas.append(
            f"used_facts aponta indice que nao existe no dossie: {fora}. "
            f"Os indices validos vao de 0 a {len(dossier.facts) - 1}."
        )
    if not script.facts:
        problemas.append(
            "used_facts esta vazio: todo roteiro precisa apoiar-se em pelo menos "
            "um fato do dossie, com fonte."
        )

    soltos = _numeros_sem_dossie(script, dossier)

    if soltos:
        problemas.append(
            f"a narracao cita numero que nao esta no dossie: {', '.join(soltos)}. "
            "Use so os numeros dos fatos, sem converter unidade e sem arredondar."
        )

    problemas.extend(validate_terms(script.search_terms))

    sem_sujeito = missing_subject(script.narration, dossier.topic)
    if sem_sujeito:
        problemas.append(
            "o roteiro fala de 'um modelo' sem nomear: cite "
            + ", ".join(f"{t!r}" for t in sem_sujeito) + " (nome e criador, "
            "conforme o dossie -- nunca invente). Sem nome nao ha busca nem "
            "credibilidade.")

    falha_gancho = check_hook(script.hook)
    if falha_gancho is not None:
        problemas.append(falha_gancho)
    problemas.extend(check_numbers(script.narration))
    problemas.extend(check_emoji_bordao(script.narration))

    return problemas


def _numeros_sem_dossie(script: Script, dossier: Dossier) -> list[str]:
    """Numero em digito na narracao precisa estar em algum fato do dossie.

    E o mesmo portao que o pesquisador usa para conferir fato contra pagina, com
    o dossie no lugar da pagina -- a pergunta e identica ("este numero existe na
    fonte?") e ter duas implementacoes dela garantiria duas respostas.

    Limite conhecido: pega so o que esta escrito em digito. A narracao boa
    escreve numero por extenso para o TTS ("cinco virgula nove gigabytes"), e
    conferir isso exigiria converter numeral em portugues de volta para digito.
    Quem cobre esse caso e o criterio 2 da rubrica do juiz, com o dossie em maos
    -- este portao so garante que o barato de conferir nunca passe errado.
    """
    fontes = "\n".join(f"{f.claim}\n{f.quote}" for f in dossier.facts)
    # O marcador de citacao sai antes da conta: ele tem violacao propria, e
    # deixa-lo aqui faria o portao acusar "numero 0, 1, 2 sem respaldo" -- que e
    # verdade e nao ajuda ninguem a entender o que fazer.
    narracao = _MARCADOR_DE_CITACAO.sub(" ", script.narration)
    return missing_numbers(narracao, fontes)


def thin_dossier_reason(dossier: Dossier) -> str:
    """Motivo para nao tentar escrever, ou string vazia se da para tentar.

    A faixa de 60-90s exige umas 150 palavras de conteudo. Dossie com dois fatos
    tirados da mesma frase nao tem isso, e o roteirista so tem duas saidas:
    encher de enrolacao, ou inventar. As duas sao piores que recusar com motivo.

    O numero de FONTES nao entra: uma fonte rica rende roteiro (o roteiro de
    referencia do M0 tem cinco fatos de um unico release). O que conta e quantos
    fatos distintos existem.
    """
    if len(dossier.facts) < MIN_FATOS_PARA_ROTEIRO:
        return (
            f"dossie fino: {len(dossier.facts)} fato(s), e a faixa de "
            f"{MIN_DURATION_S}-{MAX_DURATION_S}s pede pelo menos "
            f"{MIN_FATOS_PARA_ROTEIRO}. Pesquise outras fontes antes de roteirizar."
        )
    return ""


def _resolver_fatos(indices: object, facts: list[Fact]) -> tuple[list[Fact], list[int]]:
    """Traduz os indices que o modelo devolveu em fatos do dossie.

    O modelo aponta, nunca copia: se ele pudesse reescrever o fato, a afirmacao
    do roteiro deixaria de ser rastreavel ao que a fonte diz -- que e todo o
    ponto de o dossie existir.
    """
    if not isinstance(indices, list):
        return [], []

    usados: list[Fact] = []
    fora: list[int] = []
    for bruto in indices:
        if isinstance(bruto, bool) or not isinstance(bruto, int):
            continue
        if 0 <= bruto < len(facts):
            if facts[bruto] not in usados:
                usados.append(facts[bruto])
        else:
            fora.append(bruto)
    return usados, fora


def _violacoes_de_contrato(exc: ValidationError) -> list[str]:
    saida: list[str] = []
    for erro in exc.errors():
        campo = ".".join(str(p) for p in erro["loc"]) or "roteiro"
        saida.append(f"o campo {campo} nao respeita o contrato: {erro['msg']}")
    return saida


# Exemplo de 15s que cabe na faixa: o modelo imita o tamanho, nao so o tom.
SHORT_EXAMPLE = (
    "hook: Um modelo gigante cabe no seu bolso?\n"
    "body: O Bonsai 2 tem vinte e sete bilhões de parâmetros em só cinco "
    "vírgula nove gigabytes. Nove vezes menor, quase tudo do desempenho.\n"
    "closing: Gigante no bolso: o que mais vai encolher?")


def build_prompt(dossier: Dossier, correcoes: list[str] | None = None,
                 mode: str = "long") -> str:
    """Monta o prompt do roteiro. Funcao livre para o teste inspecionar o texto."""
    fatos = "\n".join(
        f"[{i}] {f.claim}\n    fonte: {f.source_name}"
        + (f'\n    trecho: "{f.quote}"' if f.quote else "")
        for i, f in enumerate(dossier.facts)
    )
    minimo, maximo = BANDS[mode]
    tmin, tmax = TERMS_PER_MODE[mode]
    alvo = (minimo + maximo) // 2
    fechamento = (
        "- closing: o fechamento com PONTO DE VISTA PROPRIO. Nao e resumo do que "
        "foi dito. O melhor fechamento aponta o que as fontes NAO dizem, ou a "
        "pergunta que elas deixam sem resposta, e devolve isso ao espectador. "
        "Encerre com uma chamada que nao seja 'siga para mais'.\n"
        if mode == "long" else
        "- closing: UMA frase que reconecta com a pergunta do hook E aponta a "
        "implicacao que a fonte nao desenvolve (ex.: 'Se sao dois orgaos, qual "
        "deles decide por voce?'). E o ponto de vista do video -- sem ele o "
        "roteiro e resumo. Sem 'siga para mais'.\n"
    )

    duracao_txt = (
        f"Isso equivale a {MIN_DURATION_S}-{MAX_DURATION_S}s falados e e "
        "requisito de monetizacao, nao preferencia.\n"
           if mode == "long" else
           "Video curto de alcance (~15s): nao monetiza, pesca publico. "
           "Uma ideia so, apoiada em 1 ou 2 fatos no maximo -- nao tente "
           "cobrir o dossie inteiro. Conte as palavras da narracao antes de "
           "responder: se passar do teto, corte frases inteiras ate caber -- "
           "nao entregue acima do teto.\n")

    partes = [
        f"TEMA: {dossier.topic}\n",
        f"DOSSIE (use o indice para citar):\n{fatos}\n",
        "TAREFA\n"
        "Escreva um roteiro de video vertical em portugues do Brasil, para ser "
        "narrado. Devolva:\n"
        "- hook: a abertura. A PRIMEIRA FRASE precisa abrir uma lacuna de "
        "informacao e nao responde-la -- e o que decide se a pessoa continua "
        "assistindo. Ate 12 palavras (regra da marca). Nada de 'hoje eu vou "
        "falar sobre'.\n"
        "- body: o desenvolvimento. Todo dado vem de um fato do dossie. Nomeie "
        "o assunto no hook ou na primeira frase do body (nome + quem construiu, "
        "SE o dossie disser).\n"
        + fechamento +
        f"- search_terms: de {tmin} a {tmax} termos de busca de video de banco "
        "de imagens, EM INGLES, na ordem cronologica da narracao -- o material "
        "do primeiro termo abre o video. Cada termo e COPIADO da lista de "
        "ESTETICA, nunca um conceito abstrato ('innovation').\n"
        "- used_facts: os indices dos fatos do dossie em que o roteiro se apoia.\n",
        visual_brief(suggest_pillar(dossier.topic)),
        *([] if mode != "short" else [
            "EXEMPLO DE TAMANHO (15s: copie a extensao, nao o texto)\n"
            + SHORT_EXAMPLE]),
        voice_brief(),
        "REGRAS\n"
        f"- A narracao inteira (hook + body + closing) precisa ter entre "
        f"{minimo} e {maximo} palavras, ou seja cerca de {alvo}. "
        + duracao_txt +
        "- Escreva numero por extenso quando ficar melhor de ouvir "
        "('cinco virgula nove gigabytes'), mas nunca mude o valor.\n"
        "- Nao invente numero, nome, data nem citacao. Se o dossie nao diz, o "
        "roteiro nao afirma.\n"
        "- NAO escreva os indices no texto. Nada de '[0]' ou '[1, 2]' no meio da "
        "frase: o texto vai ser lido por um sintetizador de voz, que falaria esses "
        "numeros em voz alta. O indice vai apenas no campo used_facts.\n"
        "- Sem emoji, sem hashtag, sem marcacao de cena. So o que sera falado.",
    ]

    if correcoes:
        partes.append(
            "CORRIJA A TENTATIVA ANTERIOR\n"
            + "\n".join(f"- {c}" for c in correcoes)
            + "\nMantenha o que estava bom e conserte apenas o apontado."
        )
    return "\n".join(partes)


def _texto(valor: object) -> str:
    return " ".join(str(valor).split()) if isinstance(valor, str) else ""


def _termos(valor: object) -> list[str]:
    if not isinstance(valor, list):
        return []
    return [" ".join(str(t).split()) for t in valor if isinstance(t, str) and t.strip()]
