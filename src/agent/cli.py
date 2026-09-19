"""CLI do agente."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from agent.adapters.mpt_renderer import MptRenderer
from agent.config import settings
from agent.models import MAX_DURATION_S, MIN_DURATION_S, Decision, RenderState, Script
from agent.ports.renderer import RendererError

app = typer.Typer(add_completion=False, help="Agente de video curto para tech/IA/ciencia")


def _load_script(path: Path) -> Script:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("_comment", None)
    return Script.model_validate(raw)


@app.command()
def render(
    script_path: Path = typer.Option(..., "--script", "-s", exists=True, readable=True),
) -> None:
    """Renderiza um roteiro em MP4 vertical e confere o aceite do M0."""
    script = _load_script(script_path)
    typer.echo(f"tema      : {script.topic}")
    typer.echo(f"narracao  : {script.word_count} palavras "
               f"(~{script.estimated_duration_s:.0f}s estimados)")
    typer.echo(f"termos    : {', '.join(script.search_terms)}")
    typer.echo(f"fatos     : {len(script.facts)} com fonte")

    renderer = MptRenderer()
    if not renderer.health():
        typer.secho(
            f"renderizador nao responde em {settings.renderer_url}\n"
            "suba com: ./scripts/setup_renderer.sh --serve",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    typer.echo("renderizando (minutos, em CPU)...")
    try:
        result = renderer.render(script)
    except RendererError as exc:
        typer.secho(f"falha: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if result.state is RenderState.failed:
        typer.secho(f"renderizacao falhou: {result.error}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo(f"arquivo   : {result.video_path}")
    typer.echo(f"dimensoes : {result.width}x{result.height}")
    typer.echo(f"duracao   : {result.duration_s}s")
    typer.echo(f"narracao  : {'presente' if result.has_audio else 'AUSENTE'}")

    # Aceite do M0, medido e nao presumido.
    checks = [
        ("9:16 em 1080x1920", result.is_portrait_1080x1920),
        (f"duracao entre {MIN_DURATION_S}s e {MAX_DURATION_S}s",
         result.duration_in_monetizable_range),
        ("trilha de audio presente", result.has_audio),
    ]
    typer.echo("")
    ok = True
    for label, passed in checks:
        mark = "OK  " if passed else "FALHA"
        color = typer.colors.GREEN if passed else typer.colors.RED
        typer.secho(f"[{mark}] {label}", fg=color)
        ok = ok and passed

    if not ok:
        raise typer.Exit(code=1)


@app.command()
def radar(
    limit: int = typer.Option(15, "--limit", "-n", help="quantos sinais listar"),
) -> None:
    """Coleta sinais de tendencia das fontes gratuitas e grava a serie."""
    from agent.memory.store import SignalStore
    from agent.radar.collector import Radar, default_sources

    settings.ensure_dirs()
    report = Radar(default_sources(), SignalStore(settings.db_path)).collect()

    for nome, erro in report.failures.items():
        typer.secho(f"[fonte fora] {nome}: {erro}", fg=typer.colors.YELLOW)

    if not report.signals:
        typer.secho("nenhum sinal coletado", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # Ordena por velocidade; sem velocidade vai para o fim, porque "desconhecido"
    # nao pode competir de igual para igual com uma medida.
    ordenados = sorted(
        report.signals, key=lambda s: (s.has_velocity, s.velocity or 0), reverse=True
    )

    typer.echo("")
    typer.echo(f"{'velocidade':>12}  {'volume':>10}  {'fonte':<14}  termo")
    typer.echo("-" * 92)
    for s in ordenados[:limit]:
        vel = f"{s.velocity:,.1f}/h" if s.has_velocity else "-"
        typer.echo(f"{vel:>12}  {s.volume:>10,.0f}  {s.source:<14}  {s.term[:44]}")

    typer.echo("")
    typer.echo(f"{len(report.signals)} sinais de {len(report.sources_ok)} fontes "
               f"({len(report.with_velocity)} com velocidade) em {report.elapsed_s}s")
    if report.failures:
        typer.echo(f"{len(report.failures)} fonte(s) fora; a coleta seguiu sem elas")


@app.command()
def curate(
    show: int = typer.Option(8, "--show", help="quantos rejeitados detalhar"),
    dry_run: bool = typer.Option(False, "--dry-run", help="nao grava no ledger"),
) -> None:
    """Coleta sinais e escolhe UM tema, registrando o motivo de cada decisao."""
    from agent.curator.curator import Curator
    from agent.memory.store import SignalStore
    from agent.models import Verdict
    from agent.radar.collector import Radar, default_sources

    settings.ensure_dirs()
    store = SignalStore(settings.db_path)

    coleta = Radar(default_sources(), store).collect()
    for nome, erro in coleta.failures.items():
        typer.secho(f"[fonte fora] {nome}: {erro}", fg=typer.colors.YELLOW)
    if not coleta.signals:
        typer.secho("nenhum sinal coletado", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    ledger = store.recent_topics()
    report = Curator().curate(coleta.signals, ledger=ledger)

    contagem = report.tally()
    typer.echo("")
    typer.echo(f"{len(coleta.signals)} sinais -> "
               + "  ".join(f"{k}={v}" for k, v in contagem.items() if v))
    typer.echo(f"ledger: {len(ledger)} temas ja aprovados nos ultimos 30 dias")

    for verdict, cor in ((Verdict.rejected_policy, typer.colors.RED),
                         (Verdict.rejected_duplicate, typer.colors.YELLOW)):
        for d in report.by_verdict(verdict)[:show]:
            typer.secho(f"  [{verdict.value}] {d.term[:52]}", fg=cor)
            typer.secho(f"      {d.reason}", fg=typer.colors.BRIGHT_BLACK)

    escolhido = report.selected
    if escolhido is None:
        typer.secho("\nnenhum tema elegivel hoje", fg=typer.colors.RED)
        if not dry_run:
            store.record_decisions(report.decisions)
        raise typer.Exit(code=1)

    typer.echo("")
    typer.secho(f"TEMA: {escolhido.term}", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  {escolhido.reason}")
    if escolhido.url:
        typer.echo(f"  {escolhido.url}")
    if escolhido.news_items:
        typer.echo(f"  {len(escolhido.news_items)} materias ja associadas pela fonte")

    vice = [d for d in report.by_verdict(Verdict.not_selected)][:4]
    if vice:
        typer.echo("\n  proximos colocados:")
        for d in vice:
            typer.echo(f"    {d.score:.3f}  {d.term[:58]}")

    if dry_run:
        typer.secho("\n--dry-run: nada gravado no ledger", fg=typer.colors.YELLOW)
    else:
        n = store.record_decisions(report.decisions)
        typer.echo(f"\n{n} decisoes gravadas no ledger")


@app.command()
def research(
    topic: str = typer.Option(
        "", "--topic", "-t", help="pesquisa este tema; sem isso, roda o curador"
    ),
    url: list[str] = typer.Option(
        [], "--url", "-u", help="fonte explicita (repetivel); pula a descoberta"
    ),
    llm: str = typer.Option("", "--llm", help="gemini ou groq; padrao vem do .env"),
    max_sources: int = typer.Option(0, "--sources", help="teto de fontes a ler"),
    dry_run: bool = typer.Option(False, "--dry-run", help="nao grava o dossie"),
) -> None:
    """Monta o dossie de um tema: 3-5 fontes, cada fato com URL e trecho conferidos."""
    from datetime import UTC, datetime

    from agent.adapters.llm_factory import build_llm
    from agent.memory.store import SignalStore
    from agent.models import Verdict
    from agent.ports.llm import LLMError
    from agent.research.fetch import PageFetcher
    from agent.research.researcher import Researcher
    from agent.research.sources import Candidate

    settings.ensure_dirs()
    store = SignalStore(settings.db_path)
    teto = max_sources or settings.research_max_sources

    if topic:
        decision = Decision(
            term=topic, source="manual", verdict=Verdict.selected,
            reason="tema informado na linha de comando, sem passar pelo curador",
            score=0.0, niche_fit=0.0, decided_at=datetime.now(UTC),
        )
    else:
        decision = _curate_one(store)

    typer.echo(f"tema      : {decision.term}")
    typer.echo(f"origem    : {decision.source}")

    try:
        modelo = build_llm(llm or None)
    except LLMError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=2) from exc
    typer.echo(f"modelo    : {modelo.provider}/{modelo.model}")

    candidatos = (
        [Candidate(url=u, origin="manual") for u in url] if url else None
    )
    pesquisador = Researcher(
        modelo,
        fetcher=PageFetcher(max_chars=settings.research_page_chars),
        max_sources=teto,
        max_facts_per_source=settings.research_max_facts_per_source,
    )

    typer.echo("lendo fontes (uma chamada de modelo por fonte)...")
    report = pesquisador.research(decision, candidates=candidatos)

    for onde, motivo in report.failures.items():
        typer.secho(f"[fonte fora] {onde[:70]}: {motivo}", fg=typer.colors.YELLOW)

    if report.pages:
        typer.echo("")
        typer.echo("fontes lidas:")
        for pagina in report.pages:
            typer.echo(f"  {pagina.source_name:<22} {len(pagina.text):>6} car  {pagina.url[:70]}")

    # Descartado vem antes do dossie de proposito: e a parte que se perde se
    # ninguem olhar, e e o que diz se o portao esta calibrado ou estrangulando.
    if report.discarded:
        typer.echo("")
        typer.secho(f"{len(report.discarded)} fato(s) descartado(s) pelos portoes:",
                    fg=typer.colors.YELLOW)
        for d in report.discarded:
            typer.secho(f"  {d.claim[:76]}", fg=typer.colors.YELLOW)
            typer.secho(f"      {d.reason}", fg=typer.colors.BRIGHT_BLACK)

    custo = report.usage
    typer.echo("")
    typer.echo(f"custo     : {custo.input_tokens} tokens de entrada, "
               f"{custo.output_tokens} de saida, {report.latency_s}s de modelo")

    if not report.ok:
        typer.secho("nenhum fato com fonte sobreviveu; sem dossie", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    dossier = report.dossier
    typer.echo("")
    typer.secho(f"DOSSIE: {len(dossier.facts)} fatos de {report.source_count} fonte(s)",
                fg=typer.colors.GREEN, bold=True)
    for f in dossier.facts:
        typer.echo("")
        typer.secho(f"  {f.claim}", bold=True)
        typer.echo(f"      fonte : {f.source_name} — {f.source_url}")
        if f.quote:
            typer.secho(f'      trecho: "{f.quote[:100]}"', fg=typer.colors.BRIGHT_BLACK)

    if dry_run:
        typer.secho("\n--dry-run: dossie nao gravado", fg=typer.colors.YELLOW)
        return

    linha = store.record_dossier(
        dossier,
        model=modelo.model,
        provider=modelo.provider,
        usage=(custo.input_tokens, custo.output_tokens),
        latency_s=report.latency_s,
        source_count=report.source_count,
        discarded=[vars(d) for d in report.discarded],
        failures=report.failures,
    )
    typer.echo(f"\ndossie #{linha} gravado ({store.dossier_count()} na memoria)")


def _curate_one(store: Any) -> Decision:
    """Roda radar + curador e devolve o tema do dia, ou sai com erro."""
    from agent.curator.curator import Curator
    from agent.radar.collector import Radar, default_sources

    coleta = Radar(default_sources(), store).collect()
    for nome, erro in coleta.failures.items():
        typer.secho(f"[fonte fora] {nome}: {erro}", fg=typer.colors.YELLOW)
    if not coleta.signals:
        typer.secho("nenhum sinal coletado", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    report = Curator().curate(coleta.signals, ledger=store.recent_topics())
    store.record_decisions(report.decisions)
    escolhido = report.selected
    if escolhido is None:
        typer.secho("nenhum tema elegivel hoje", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    return escolhido


@app.command()
def write(
    topic: str = typer.Option("", "--topic", "-t", help="tema; sem isso, usa o ultimo dossie"),
    llm: str = typer.Option("", "--llm", help="gemini ou groq; padrao vem do .env"),
    out: Path = typer.Option(None, "--out", "-o", help="grava o roteiro em JSON para render"),
    dry_run: bool = typer.Option(False, "--dry-run", help="nao grava na memoria"),
) -> None:
    """Escreve o roteiro a partir de um dossie ja gravado."""
    from agent.adapters.llm_factory import build_llm
    from agent.memory.store import SignalStore
    from agent.ports.llm import LLMError
    from agent.writer.writer import Screenwriter

    settings.ensure_dirs()
    store = SignalStore(settings.db_path)

    dossier = store.latest_dossier(topic or None)
    if dossier is None:
        alvo = f" para o tema {topic!r}" if topic else ""
        typer.secho(
            f"nenhum dossie{alvo} na memoria. Rode `uv run agent research` primeiro.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    typer.echo(f"tema      : {dossier.topic}")
    typer.echo(f"dossie    : {len(dossier.facts)} fatos de "
               f"{len(dossier.source_urls)} fonte(s)")

    try:
        modelo = build_llm(llm or None)
    except LLMError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=2) from exc
    typer.echo(f"modelo    : {modelo.provider}/{modelo.model}")

    typer.echo("escrevendo (corrige sozinho o que e mecanico)...")
    try:
        report = Screenwriter(modelo).write(dossier)
    except LLMError as exc:
        typer.secho(f"falha do provedor: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if report.refusal:
        typer.secho(f"\n{report.refusal}", fg=typer.colors.RED)
        typer.echo("nenhuma chamada de modelo foi feita; custo zero")
        raise typer.Exit(code=1)

    # As tentativas corrigidas aparecem mesmo no sucesso: se toda execucao gasta
    # duas rodadas no mesmo defeito, o prompt e que esta fraco.
    for i, tentativa in enumerate(report.attempts, start=1):
        if tentativa.violations:
            typer.secho(f"tentativa {i} reprovada ({tentativa.word_count} palavras):",
                        fg=typer.colors.YELLOW)
            for v in tentativa.violations:
                typer.secho(f"  - {v}", fg=typer.colors.BRIGHT_BLACK)

    custo = report.usage
    typer.echo(f"custo     : {custo.input_tokens} tokens de entrada, "
               f"{custo.output_tokens} de saida, {report.latency_s}s de modelo, "
               f"{len(report.attempts)} tentativa(s)")

    if not report.ok:
        typer.secho("\nnenhum roteiro passou nos portoes mecanicos", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    script = report.script
    typer.echo("")
    typer.secho(f"ROTEIRO: {script.word_count} palavras "
                f"(~{script.estimated_duration_s:.0f}s estimados)",
                fg=typer.colors.GREEN, bold=True)
    typer.echo("")
    typer.secho("  HOOK", bold=True)
    typer.echo(f"  {script.hook}")
    typer.echo("")
    typer.secho("  CORPO", bold=True)
    for paragrafo in script.body.split("\n"):
        if paragrafo.strip():
            typer.echo(f"  {paragrafo.strip()}")
    typer.echo("")
    typer.secho("  FECHAMENTO", bold=True)
    typer.echo(f"  {script.closing}")
    typer.echo("")
    typer.echo(f"  termos: {', '.join(script.search_terms)}")
    typer.echo(f"  fatos : {len(script.facts)} do dossie")

    if out is not None:
        out.write_text(
            script.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
        )
        typer.echo(f"\ngravado em {out}")
        typer.echo(f"renderize com: uv run agent render --script {out}")

    if dry_run:
        typer.secho("\n--dry-run: roteiro nao gravado na memoria", fg=typer.colors.YELLOW)
        return

    linha = store.record_script(
        script,
        model=modelo.model,
        provider=modelo.provider,
        usage=(custo.input_tokens, custo.output_tokens),
        latency_s=report.latency_s,
        attempts=[
            {"violations": a.violations, "word_count": a.word_count} for a in report.attempts
        ],
        dossier_id=store.latest_dossier_id(dossier.topic),
    )
    typer.echo(f"\nroteiro #{linha} gravado ({store.script_count()} na memoria)")


def _mostrar_parecer(review) -> None:
    """Imprime a rubrica inteira, critério a critério.

    Sempre inteira, inclusive os criterios que tiraram 2: parecer resumido em
    "reprovado (9/14)" nao diz o que mudar, e e o motivo por criterio que volta
    ao roteirista na revisao.
    """
    from agent.models import RUBRIC_CUTOFF, RUBRIC_MAX

    typer.echo("")
    for s in review.scores:
        cor = (typer.colors.GREEN if s.score == 2
               else typer.colors.YELLOW if s.score == 1 else typer.colors.RED)
        # "julgado" para nota que nao foi julgada seria mentira no proprio
        # relatorio que existe para dar para auditar.
        marca = "pulado " if not s.evaluated else "medido " if s.measured else "julgado"
        typer.secho(f"  [{s.score}/2] {marca}  {s.criterion.value}", fg=cor)
        typer.secho(f"          {s.reason}", fg=typer.colors.BRIGHT_BLACK)

    typer.echo("")
    if review.approved:
        typer.secho(f"APROVADO: {review.total}/{RUBRIC_MAX} "
                    f"(corte {RUBRIC_CUTOFF}, nenhum criterio zerado)",
                    fg=typer.colors.GREEN, bold=True)
        return

    typer.secho(f"REPROVADO: {review.total}/{RUBRIC_MAX} (corte {RUBRIC_CUTOFF})",
                fg=typer.colors.RED, bold=True)
    for s in review.vetoed:
        typer.secho(f"  veto em {s.criterion.value}: e requisito, nao qualidade — "
                    "nota nos outros criterios nao compensa", fg=typer.colors.RED)
    for s in review.zeroed:
        if s not in review.vetoed:
            typer.secho(f"  zerado em {s.criterion.value}: criterio zerado reprova "
                        "mesmo com a soma no corte", fg=typer.colors.RED)


@app.command()
def judge(
    topic: str = typer.Option("", "--topic", "-t", help="tema; sem isso, usa o ultimo roteiro"),
    script_path: Path = typer.Option(
        None, "--script", "-s", exists=True, readable=True,
        help="julga este arquivo em vez do ultimo roteiro da memoria",
    ),
    llm: str = typer.Option("", "--llm", help="gemini ou groq; padrao vem do .env"),
    dry_run: bool = typer.Option(False, "--dry-run", help="nao grava o parecer"),
) -> None:
    """Aplica a rubrica de 7 critérios a um roteiro."""
    from datetime import UTC, datetime

    from agent.adapters.llm_factory import build_llm
    from agent.judge.judge import Judge, review_measured_only
    from agent.memory.store import SignalStore
    from agent.models import Dossier
    from agent.ports.llm import LLMError

    settings.ensure_dirs()
    store = SignalStore(settings.db_path)

    if script_path is not None:
        script = _load_script(script_path)
        # O Script carrega os fatos que o roteirista usou, então um arquivo se
        # autojulga: e o que permite rodar a fixture adversarial sem a memoria.
        dossier = Dossier(
            topic=script.topic, facts=script.facts, collected_at=datetime.now(UTC)
        )
    else:
        script = store.latest_script(topic or None)
        if script is None:
            typer.secho("nenhum roteiro na memoria. Rode `uv run agent write` primeiro.",
                        fg=typer.colors.RED)
            raise typer.Exit(code=2)
        dossier = store.latest_dossier(script.topic) or Dossier(
            topic=script.topic, facts=script.facts, collected_at=datetime.now(UTC)
        )

    if not dossier.facts:
        typer.secho("roteiro sem nenhum fato: nao ha dossie contra o que julgar",
                    fg=typer.colors.RED)
        raise typer.Exit(code=2)

    typer.echo(f"tema      : {script.topic}")
    typer.echo(f"roteiro   : {script.word_count} palavras, "
               f"{len(script.facts)} fatos, ~{script.estimated_duration_s:.0f}s")

    # Medida primeiro: se o roteiro ja reprova num criterio de requisito, nao ha
    # motivo para exigir chave de API para confirmar isso.
    antecipado = review_measured_only(script, dossier)
    if antecipado is not None:
        typer.echo("modelo    : nao consultado (reprovou na medida)")
        _mostrar_parecer(antecipado)
        typer.echo("\ncusto     : 0 tokens")
        if not dry_run:
            linha = store.record_review(antecipado, usage=(0, 0), latency_s=0.0)
            typer.echo(f"parecer #{linha} gravado")
        raise typer.Exit(code=1)

    try:
        modelo = build_llm(llm or None)
        typer.echo(f"modelo    : {modelo.provider}/{modelo.model}")
        report = Judge(modelo).review(script, dossier)
    except LLMError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=2) from exc

    _mostrar_parecer(report.review)
    typer.echo(f"\ncusto     : {report.usage.total_tokens} tokens, {report.latency_s}s")

    if not dry_run:
        linha = store.record_review(
            report.review,
            usage=(report.usage.input_tokens, report.usage.output_tokens),
            latency_s=report.latency_s,
        )
        typer.echo(f"parecer #{linha} gravado")

    raise typer.Exit(code=0 if report.approved else 1)


@app.command()
def produce(
    topic: str = typer.Option("", "--topic", "-t", help="tema; sem isso, usa o ultimo dossie"),
    out: Path = typer.Option(None, "--out", "-o", help="grava o roteiro aprovado em JSON"),
    revisions: int = typer.Option(2, "--revisions", help="teto de rodadas de revisao"),
    llm: str = typer.Option("", "--llm", help="gemini ou groq; padrao vem do .env"),
    dry_run: bool = typer.Option(False, "--dry-run", help="nao grava na memoria"),
) -> None:
    """Escreve, julga e revisa ate o roteiro passar na rubrica ou estourar as rodadas."""
    from agent.adapters.llm_factory import build_llm
    from agent.judge.judge import Judge
    from agent.memory.store import SignalStore
    from agent.pipeline import produce as rodar
    from agent.ports.llm import LLMError
    from agent.writer.writer import Screenwriter

    settings.ensure_dirs()
    store = SignalStore(settings.db_path)

    dossier = store.latest_dossier(topic or None)
    if dossier is None:
        typer.secho("nenhum dossie na memoria. Rode `uv run agent research` primeiro.",
                    fg=typer.colors.RED)
        raise typer.Exit(code=2)

    typer.echo(f"tema      : {dossier.topic}")
    typer.echo(f"dossie    : {len(dossier.facts)} fatos de "
               f"{len(dossier.source_urls)} fonte(s)")
    try:
        modelo = build_llm(llm or None)
    except LLMError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=2) from exc
    typer.echo(f"modelo    : {modelo.provider}/{modelo.model}")
    typer.echo(f"ate {revisions + 1} rodada(s) de roteiro + parecer...")

    report = rodar(dossier, Screenwriter(modelo), Judge(modelo), max_revisions=revisions)
    if report.failure:
        typer.secho(f"falha no meio do laco — {report.failure}", fg=typer.colors.RED)

    for i, rodada in enumerate(report.rounds, start=1):
        typer.echo("")
        typer.secho(f"--- rodada {i} ---", bold=True)
        if rodada.write is not None and rodada.write.refusal:
            typer.secho(f"roteirista recusou: {rodada.write.refusal}", fg=typer.colors.RED)
        elif rodada.write is not None:
            tentativas = len(rodada.write.attempts)
            typer.echo(f"roteirista: {tentativas} tentativa(s) mecanica(s)")
            for t in rodada.write.attempts:
                for v in t.violations:
                    typer.secho(f"  - {v}", fg=typer.colors.BRIGHT_BLACK)
        if rodada.review is not None and rodada.review.review is not None:
            _mostrar_parecer(rodada.review.review)

    custo = report.usage
    typer.echo("")
    typer.echo(f"custo total: {custo.input_tokens} tokens de entrada, "
               f"{custo.output_tokens} de saida, {report.latency_s}s de modelo")

    if not report.approved:
        typer.secho("nenhum roteiro aprovado nas rodadas disponiveis; "
                    "o motivo de cada reprovacao esta acima", fg=typer.colors.RED)
        if not dry_run and report.script is not None and report.review is not None:
            _gravar(store, report, dossier)
        raise typer.Exit(code=1)

    script = report.script
    typer.echo("")
    typer.secho(f"ROTEIRO APROVADO: {script.word_count} palavras "
                f"(~{script.estimated_duration_s:.0f}s)", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  {script.hook}")
    typer.echo(f"  termos: {', '.join(script.search_terms)}")

    if out is not None:
        out.write_text(
            script.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
        )
        typer.echo(f"\ngravado em {out}")
        typer.echo(f"renderize com: uv run agent render --script {out}")

    if dry_run:
        typer.secho("\n--dry-run: nada gravado na memoria", fg=typer.colors.YELLOW)
        return
    _gravar(store, report, dossier)


def _gravar(store: Any, report: Any, dossier: Any) -> None:
    """Grava roteiro e parecer ligados, inclusive quando reprovado.

    Reprovado tambem entra: e o registro de em que critério a rubrica bate com
    mais frequencia, e sem ele calibrar a rubrica seria chute.
    """
    ultima = report.rounds[-1]
    script_id = store.record_script(
        report.script,
        model=ultima.write.model,
        provider=ultima.write.provider,
        usage=(report.usage.input_tokens, report.usage.output_tokens),
        latency_s=report.latency_s,
        attempts=[
            {"violations": t.violations, "word_count": t.word_count}
            for rodada in report.rounds if rodada.write is not None
            for t in rodada.write.attempts
        ],
        dossier_id=store.latest_dossier_id(dossier.topic),
    )
    review_id = store.record_review(
        report.review,
        usage=(report.usage.input_tokens, report.usage.output_tokens),
        latency_s=report.latency_s,
        script_id=script_id,
    )
    typer.echo(f"\nroteiro #{script_id} e parecer #{review_id} gravados")


@app.command("llm-health")
def llm_health() -> None:
    """Confere se as chaves e os ids de modelo configurados ainda respondem.

    Id de modelo de free tier e descontinuado sem aviso, e o erro aparece no meio
    de uma pesquisa, depois de gastar tempo lendo paginas. Este comando gasta uma
    chamada minuscula e verifica o artefato: quem respondeu, em quanto tempo,
    cobrando quantos tokens.
    """
    from agent.adapters.llm_factory import build_llm, configured
    from agent.ports.llm import LLMError, parse_json_object

    provedores = configured()
    if not provedores:
        typer.secho(
            "nenhuma chave de LLM configurada. As duas sao gratuitas:\n"
            "  AGENT_GEMINI_API_KEY  -> aistudio.google.com/apikey\n"
            "  AGENT_GROQ_API_KEY    -> console.groq.com/keys\n"
            "Grave no .env (git-ignored).",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    ok = True
    for nome in provedores:
        try:
            modelo = build_llm(nome)
            resposta = modelo.complete(
                'Responda {"ok": "sim"} e nada mais.',
                schema={"type": "object", "properties": {"ok": {"type": "string"}},
                        "required": ["ok"]},
                max_output_tokens=256,
            )
            parse_json_object(resposta.text)
        except LLMError as exc:
            typer.secho(f"[FALHA] {nome}: {exc}", fg=typer.colors.RED)
            ok = False
            continue
        typer.secho(
            f"[OK  ] {nome}: {resposta.model} respondeu em {resposta.latency_s}s "
            f"({resposta.usage.total_tokens} tokens)",
            fg=typer.colors.GREEN,
        )

    if not ok:
        raise typer.Exit(code=1)


@app.command()
def health() -> None:
    """Verifica se o renderizador esta de pe."""
    alive = MptRenderer().health()
    typer.secho(
        f"{settings.renderer_url}: {'ok' if alive else 'fora do ar'}",
        fg=typer.colors.GREEN if alive else typer.colors.RED,
    )
    sys.exit(0 if alive else 1)


@app.command()
def publish(
    video: Path = typer.Option(..., "--video", "-v", exists=True, readable=True),
) -> None:
    """Sobe um MP4 para a inbox do TikTok (escopo video.upload, sem auditoria).

    O endpoint inbox so recebe os bytes: titulo, descricao e rotulo AIGC sao
    aplicados por voce no app, ao concluir o post pela notificacao da inbox.
    Por isso este comando termina com o checklist manual -- e o rotulo AIGC
    nao tem flag para desligar porque nao e opcional.
    """
    from agent.adapters.tiktok_publisher import TikTokPublisher
    from agent.memory.store import SignalStore
    from agent.models import PublishState

    token = settings.tiktok_access_token
    if not token:
        typer.secho(
            "sem AGENT_TIKTOK_ACCESS_TOKEN no .env (git-ignored).\n"
            "Registre o app em developers.tiktok.com, autorize o escopo "
            "video.upload e grave o token.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    typer.echo(f"video     : {video} ({video.stat().st_size} bytes)")
    typer.echo("subindo para a inbox (init + chunks)...")
    result = TikTokPublisher().upload(str(video), access_token=token)

    store = SignalStore(settings.db_path)
    store.record_post(
        result.publish_id or "",
        str(video),
        status=result.state.value,
        error=result.error,
    )

    if result.state is not PublishState.uploaded:
        typer.secho(f"subida falhou: {result.error}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"\npublish_id: {result.publish_id}", fg=typer.colors.GREEN)
    typer.echo("gravado em posts. Agora, no app do TikTok:")
    typer.echo("  1. abra a notificacao da inbox e conclua a edicao;")
    typer.echo("  2. LIGUE o rotulo de conteudo gerado por IA (obrigatorio);")
    typer.echo("  3. confira que a legenda cita as fontes do roteiro.")


@app.command("publish-status")
def publish_status(
    publish_id: str = typer.Option(..., "--publish-id"),
) -> None:
    """Consulta o estado de um post na API e atualiza a tabela posts."""
    from agent.adapters.tiktok_publisher import TikTokPublisher
    from agent.memory.store import SignalStore

    token = settings.tiktok_access_token
    if not token:
        typer.secho("sem AGENT_TIKTOK_ACCESS_TOKEN no .env.", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    try:
        estado = TikTokPublisher().fetch_status(publish_id, access_token=token)
    except Exception as exc:
        typer.secho(f"falha: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    SignalStore(settings.db_path).update_post_status(publish_id, status=estado)
    typer.echo(f"{publish_id}: {estado}")


@app.command("tiktok-auth-url")
def tiktok_auth_url(
    state: str = typer.Option("", "--state"),
) -> None:
    """Imprime a URL para autorizar o app no navegador (escopo video.upload)."""
    from agent.adapters.tiktok_oauth import authorize_url

    if not settings.tiktok_client_key or not settings.tiktok_redirect_uri:
        typer.secho(
            "configure AGENT_TIKTOK_CLIENT_KEY e AGENT_TIKTOK_REDIRECT_URI no .env.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    typer.echo(authorize_url(
        settings.tiktok_client_key, settings.tiktok_redirect_uri, state=state,
    ))


if __name__ == "__main__":
    app()
