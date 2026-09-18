"""CLI do agente."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from agent.adapters.mpt_renderer import MptRenderer
from agent.config import settings
from agent.models import MAX_DURATION_S, MIN_DURATION_S, RenderState, Script
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
def health() -> None:
    """Verifica se o renderizador esta de pe."""
    alive = MptRenderer().health()
    typer.secho(
        f"{settings.renderer_url}: {'ok' if alive else 'fora do ar'}",
        fg=typer.colors.GREEN if alive else typer.colors.RED,
    )
    sys.exit(0 if alive else 1)


if __name__ == "__main__":
    app()
