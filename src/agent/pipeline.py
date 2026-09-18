"""Laco roteirista <-> juiz: escreve, julga, devolve para revisao, no maximo 2x.

Mora fora dos dois estagios de proposito. Se o roteirista soubesse do juiz, ele
passaria a escrever para a rubrica e o parecer deixaria de ser independente; se o
juiz soubesse do roteirista, ele julgaria a tentativa e nao o texto. O que
coordena os dois e uma terceira coisa, pequena, que so sabe contar rodadas.

O teto de duas revisoes nao e arbitrario: a partir da terceira, o que costuma
acontecer nao e o roteiro melhorar, e o modelo comecar a trocar de assunto para
agradar a rubrica. Melhor reprovar com o motivo gravado e escolher outro tema.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.judge.judge import Judge, ReviewReport
from agent.models import Dossier, Review, Script
from agent.ports.llm import Usage
from agent.writer.writer import Screenwriter, WriteReport

MAX_REVISOES = 2


@dataclass
class Round:
    """Uma rodada: o que foi escrito, com que notas, e o que o juiz achou."""

    notes_in: list[str] = field(default_factory=list)
    write: WriteReport | None = None
    review: ReviewReport | None = None

    @property
    def approved(self) -> bool:
        return self.review is not None and self.review.approved


@dataclass
class ProductionReport:
    """O resultado do laco, com as rodadas todas -- inclusive as reprovadas.

    A rodada reprovada e o dado mais util aqui: ela diz em que critério a
    rubrica bate com mais frequencia, e e por isso que o roteiro final nao chega
    sozinho.
    """

    topic: str
    rounds: list[Round] = field(default_factory=list)

    @property
    def approved(self) -> bool:
        return any(r.approved for r in self.rounds)

    @property
    def script(self) -> Script | None:
        """O roteiro aprovado, ou o ultimo escrito quando nenhum passou."""
        for r in self.rounds:
            if r.approved and r.write is not None:
                return r.write.script
        for r in reversed(self.rounds):
            if r.write is not None and r.write.script is not None:
                return r.write.script
        return None

    @property
    def review(self) -> Review | None:
        for r in self.rounds:
            if r.approved and r.review is not None:
                return r.review.review
        for r in reversed(self.rounds):
            if r.review is not None:
                return r.review.review
        return None

    @property
    def usage(self) -> Usage:
        total = Usage()
        for r in self.rounds:
            if r.write is not None:
                total = total + r.write.usage
            if r.review is not None:
                total = total + r.review.usage
        return total

    @property
    def latency_s(self) -> float:
        soma = 0.0
        for r in self.rounds:
            if r.write is not None:
                soma += r.write.latency_s
            if r.review is not None:
                soma += r.review.latency_s
        return round(soma, 3)


def produce(
    dossier: Dossier,
    writer: Screenwriter,
    judge: Judge,
    max_revisions: int = MAX_REVISOES,
) -> ProductionReport:
    report = ProductionReport(topic=dossier.topic)
    notas: list[str] = []

    for _ in range(max_revisions + 1):
        rodada = Round(notes_in=list(notas))
        rodada.write = writer.write(dossier, notes=notas or None)
        report.rounds.append(rodada)

        if rodada.write.script is None:
            # O roteirista nao passou nos proprios portoes mecanicos em tres
            # tentativas. Chamar o juiz agora seria pagar por um parecer sobre um
            # texto que ja se sabe fora da faixa de duracao.
            return report

        rodada.review = judge.review(rodada.write.script, dossier)
        if rodada.review.approved:
            return report

        notas = rodada.review.review.revision_notes if rodada.review.review else []

    return report
