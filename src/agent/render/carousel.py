"""Slides 1080x1920 do carrossel, na identidade do canal.

Tinta por pilar (o mesmo vocabulario do roteirista): o slide carrega a cor
do pilar do proprio visual, entao identidade se reconhece antes de ler.
Tipografia unica (BeVietnamPro-Bold, a que cobre pt-BR), numeracao n/5 como
indicador de swipe, headline grande + texto curto -- o slide se le em 3s.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from agent.models import Carousel
from agent.writer.visuals import pillar_of

W, H = 1080, 1920

# Fundo quase-preto + acento por pilar. Escuro de proposito: thumb de video
# treinou o polegar para claro; o escuro interrompe o padrao no feed.
BASE = (11, 14, 20)
TINTA: dict[str | None, tuple[int, int, int]] = {
    "A": (255, 45, 120),    # magenta neon
    "B": (57, 255, 140),    # verde terminal
    "C": (80, 140, 255),    # azul plexus
    "D": (150, 170, 200),   # prata sleek
    None: (150, 170, 200),
}
BRANCO = (245, 247, 250)
CINZA = (160, 170, 185)

FONT_CANDIDATES = (
    "BeVietnamPro-Bold.ttf",
    "/app/.renderer/resource/fonts/BeVietnamPro-Bold.ttf",
)


def _fonte(tamanho: int, extra: str | None = None,
           ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    cands = ((extra,) if extra else ()) + FONT_CANDIDATES
    for cand in cands:
        try:
            return ImageFont.truetype(str(cand), tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def _quebrar(draw: ImageDraw.ImageDraw, texto: str,
             fonte: ImageFont.FreeTypeFont | ImageFont.ImageFont,
             largura: int) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if draw.textlength(teste, font=fonte) <= largura:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def render_slide(carrossel: Carousel, n: int, out: Path,
                 font_path: str | None = None) -> Path:
    """Um slide em PNG. `font_path` permite apontar o ttf instalado."""
    slide = next(s for s in carrossel.slides if s.n == n)
    tinta = TINTA[pillar_of([slide.visual])]

    img = Image.new("RGB", (W, H), BASE)
    draw = ImageDraw.Draw(img)
    # Faixa vertical de acento a esquerda, gradiente simples por faixas.
    for i in range(H):
        t = i / H
        draw.line([(0, i), (26, i)],
                  fill=tuple(int(BASE[k] + (tinta[k] - BASE[k]) * (1 - t) * 0.55)
                             for k in range(3)))
    f_num = _fonte(54, font_path)
    f_head = _fonte(96, font_path)
    f_text = _fonte(58, font_path)

    draw.text((70, 120), f"{slide.n}/5", font=f_num, fill=tinta)
    draw.text((70, 210), "DESLIZE →", font=f_num, fill=CINZA)

    y = 560
    for linha in _quebrar(draw, slide.headline, f_head, W - 140):
        draw.text((70, y), linha, font=f_head, fill=BRANCO)
        y += 118
    y += 60
    for linha in _quebrar(draw, slide.text, f_text, W - 140):
        draw.text((70, y), linha, font=f_text, fill=CINZA)
        y += 78

    draw.text((70, H - 140), carrossel.topic[:48], font=f_num, fill=CINZA)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def render_carousel(carrossel: Carousel, out_dir: Path | str,
                    font_path: str | None = None) -> list[Path]:
    """Os 5 slides + caption.txt (legenda pronta para colar no app)."""
    destino = Path(out_dir)
    slides = [render_slide(carrossel, s.n, destino / f"slide-{s.n}.png",
                           font_path) for s in carrossel.slides]
    (destino / "caption.txt").write_text(carrossel.caption + "\n", encoding="utf-8")
    return slides


__all__ = ["render_carousel", "render_slide"]
