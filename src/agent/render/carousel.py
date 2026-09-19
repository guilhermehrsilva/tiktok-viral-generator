"""Slides 1080x1920 do carrossel, no vetor de marca Seu Canal.

Uma peca, um acento: o pilar de conteudo decide (verde padrao, ciano nas
pecas de ruptura fato/futuro). Fundo #0A0A0C sempre, metade do quadro
respirando, numeracao n/5 como indicador de swipe, tag do pilar no slide 1.
Tipografia da marca (Space Grotesk nos titulos, Plex Mono nos numeros) com
fallback para a BeVietnamPro quando o glifo nao existir -- tofu nunca.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from agent.brand.brand import load as load_brand
from agent.models import Carousel

W, H = 1080, 1920

BRAND_FONTS = ("SpaceGrotesk-Bold.ttf", "IBMPlexMono-SemiBold.ttf",
               "IBMPlexMono-Medium.ttf")
FALLBACK_TTF = ".renderer/resource/fonts/BeVietnamPro-Bold.ttf"


def _hex(cor: str) -> tuple[int, int, int]:
    cor = cor.lstrip("#")
    return (int(cor[0:2], 16), int(cor[2:4], 16), int(cor[4:6], 16))


def _cobre(font_path: str, texto: str) -> bool:
    """Todo caractere do texto tem glifo na fonte."""
    try:
        from fontTools.ttLib import TTFont
        cmap = TTFont(font_path).getBestCmap()
        return all(ord(c) in cmap or c.isspace() for c in texto)
    except Exception:
        return False


def _fontes_dir() -> Path:
    from agent.config import PROJECT_ROOT
    return PROJECT_ROOT / "brand" / "assets" / "fonts"


def _fonte(nome: str, tamanho: int, texto: str = ""):
    cands = [_fontes_dir() / nome]
    if FALLBACK_TTF:
        from agent.config import PROJECT_ROOT
        cands.append(PROJECT_ROOT / FALLBACK_TTF)
    for cand in cands:
        try:
            if cand.is_file() and (not texto or _cobre(str(cand), texto)):
                return ImageFont.truetype(str(cand), tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def _quebrar(draw: ImageDraw.ImageDraw, texto: str, fonte, largura: int) -> list[str]:
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
                 pillar: str = "news") -> Path:
    """Um slide em PNG, no acento do pilar de conteudo."""
    brand = load_brand()
    slide = next(s for s in carrossel.slides if s.n == n)
    fundo = _hex(brand.background)
    tinta = _hex(brand.ink)
    apagada = _hex(brand.muted)
    acento = _hex(brand.accent_for(pillar))
    tag = brand.pillars[pillar].tag if pillar in brand.pillars else ""

    img = Image.new("RGB", (W, H), fundo)
    draw = ImageDraw.Draw(img)
    for i in range(H):
        t = i / H
        draw.line([(0, i), (26, i)],
                  fill=tuple(int(fundo[k] + (acento[k] - fundo[k]) * (1 - t) * 0.55)
                             for k in range(3)))

    f_num = _fonte("IBMPlexMono-SemiBold.ttf", 54)
    f_tag = _fonte("IBMPlexMono-SemiBold.ttf", 44)
    f_head = _fonte("SpaceGrotesk-Bold.ttf", 96, slide.headline)
    f_text = _fonte("SpaceGrotesk-Bold.ttf", 58, slide.text)

    draw.text((70, 120), f"{slide.n}/5", font=f_num, fill=acento)
    draw.text((70, 210), "DESLIZE →", font=f_num, fill=apagada)
    if n == 1 and tag:
        draw.text((70, 300), tag, font=f_tag, fill=acento)

    y = 620
    for linha in _quebrar(draw, slide.headline, f_head, W - 140):
        draw.text((70, y), linha, font=f_head, fill=tinta)
        y += 118
    y += 60
    for linha in _quebrar(draw, slide.text, f_text, W - 140):
        draw.text((70, y), linha, font=f_text, fill=apagada)
        y += 78

    draw.text((70, H - 140), f"{brand.name} · {brand.handle}",
              font=f_tag, fill=apagada)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def render_carousel(carrossel: Carousel, out_dir: Path | str,
                    pillar: str = "news") -> list[Path]:
    """Os 5 slides + caption.txt (gancho + contexto + hashtags da marca)."""
    brand = load_brand()
    destino = Path(out_dir)
    slides = [render_slide(carrossel, s.n, destino / f"slide-{s.n}.png", pillar)
              for s in carrossel.slides]
    legenda = f"{carrossel.caption}\n\n{' '.join(brand.hashtags)}\n"
    (destino / "caption.txt").write_text(legenda, encoding="utf-8")
    return slides


__all__ = ["render_carousel", "render_slide"]
