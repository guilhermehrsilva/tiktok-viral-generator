"""Vocabulario visual do canal: 4 pilares esteticos, tags fixas em ingles.

Canal dark vive de identidade repetida: quem assiste tres videos precisa
reconhecer o quarto pelo visual antes da primeira palavra. Busca generica
("server rack blue lights") rende material aleatorio a cada render e nunca
constrói essa assinatura. Por isso `search_terms` nao e texto livre: sai
verbatim de um dos quatro pilares abaixo, todos de um unico pilar por roteiro.

As tags vao direto para o Pexels sem traducao, entao valem as mesmas regras do
`Script.search_terms`: ASCII e cena filmavel concreta. Tag fora do pool e
defeito mecanico -- volta ao modelo com a lista, como contagem de palavra.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pillar:
    id: str
    nome: str
    tags: tuple[str, ...]


PILLARS: dict[str, Pillar] = {
    "A": Pillar(
        id="A",
        nome="IA Sombria / Consciencia de Maquina (Dark AI / Sci-Fi)",
        tags=(
            "cybernetic brain",
            "sentient ai",
            "android activation",
            "dark tech laboratory",
            "humanoid robot close up",
            "bionic eye neon",
        ),
    ),
    "B": Pillar(
        id="B",
        nome="Programacao / Hacking / Dados (Cyberpunk Code)",
        tags=(
            "matrix code rain",
            "cyberpunk hacking terminal",
            "server room blinking lights",
            "cyber security breach",
            "holographic data glitch",
        ),
    ),
    "C": Pillar(
        id="C",
        nome="Redes Neurais / Deep Web / Conectividade (Abstract Tech)",
        tags=(
            "neural network nodes",
            "abstract digital plexus",
            "ai deep learning loop",
            "quantum computing laser",
            "data stream tunnel",
        ),
    ),
    "D": Pillar(
        id="D",
        nome='Estilo "Futuro Proximo" / Corporativo High-Tech (Sleek Tech)',
        tags=(
            "futuristic clean UI",
            "augmented reality hud",
            "smart city wireframe",
            "minimalist tech laboratory",
        ),
    ),
}

def normalize(term: str) -> str:
    """Minuscula e espaco simples: '  Bionic  Eye NEON ' casa com o pool."""
    return " ".join(term.lower().split())


_TAG_TO_PILLAR: dict[str, str] = {
    normalize(tag): pid for pid, p in PILLARS.items() for tag in p.tags
}


def pillar_of(terms: list[str]) -> str | None:
    """O pilar com mais tags entre os termos, ou None se nenhum casa.

    Derivavel a qualquer momento dos `search_terms` gravados -- por isso o
    pilar nao e coluna no banco: e funcao do roteiro, nao dado novo.
    """
    contagem: dict[str, int] = {}
    for t in terms:
        pid = _TAG_TO_PILLAR.get(normalize(t))
        if pid is not None:
            contagem[pid] = contagem.get(pid, 0) + 1
    if not contagem:
        return None
    return max(sorted(contagem), key=lambda pid: contagem[pid])


def validate_terms(terms: list[str]) -> list[str]:
    """Violoes de vocabulario, em texto que volta ao modelo como correcao."""
    problemas: list[str] = []
    fora = sorted({t for t in terms if normalize(t) not in _TAG_TO_PILLAR})
    if fora:
        problemas.append(
            "search_terms fora do vocabulario visual: "
            + ", ".join(f"{t!r}" for t in fora) + ". "
            "Use tags EXATAS de um unico pilar da lista de ESTETICA."
        )
    pilares = sorted({_TAG_TO_PILLAR[normalize(t)] for t in terms
                      if normalize(t) in _TAG_TO_PILLAR})
    if len(pilares) > 1:
        problemas.append(
            "search_terms misturam pilares "
            + "/".join(pilares) + ": um roteiro, um pilar. "
            "Identidade visual se constrói por repeticao, nao por variedade."
        )
    return problemas


# Palavras do tema (pt e en) que puxam cada pilar. Ordem importa: A antes de B
# antes de C; o que nao casar cai no D, que e o pilar generico do canal.
_PALAVRAS: dict[str, tuple[str, ...]] = {
    "A": ("robo", "robô", "robot", "android", "humanoide", "humanoid",
          "consciencia", "consciência", "consciousness", "sentient",
          "bionic", "biônic", "cyborg", "ciborgue"),
    "B": ("codigo", "código", "code", "hack", "cyber", "seguranca",
          "segurança", "security", "servidor", "server", "terminal",
          "breach", "vazamento", "malware", "ransomware", "programa",
          "programador", "developer"),
    "C": ("neural", "quantum", "quantic", "quântic", "deep learning",
          "aprendizado", "network", "rede", "conectividade", "plexus",
          "stream", "dados", "data", "modelo", "model", "parametro",
          "parâmetro", "token", "treinamento", "training"),
}

_PILAR_SUGERIDO_POR_OMISSAO = "D"


def suggest_pillar(topic: str) -> str:
    """Pilar sugerido pelo assunto. Orientacao, nao decisao: o modelo escolhe."""
    baixo = topic.lower()
    for pid in ("A", "B", "C"):
        if any(p in baixo for p in _PALAVRAS[pid]):
            return pid
    return _PILAR_SUGERIDO_POR_OMISSAO


def brief(pilar_sugerido: str) -> str:
    """Bloco de ESTETICA do prompt, com as tags verbatim para copiar."""
    blocos = []
    for pid, p in PILLARS.items():
        marca = " <-- pilar sugerido para este tema" if pid == pilar_sugerido else ""
        tags = "\n".join(f"    - {t}" for t in p.tags)
        blocos.append(f"  Pilar {pid} ({p.nome}){marca}:\n{tags}")
    return (
        "ESTETICA (identidade do canal)\n"
        "O canal tem assinatura visual fixa: todo search_terms sai COPIADO, "
        "letra por letra, da lista de UM unico pilar abaixo, na ordem "
        "cronologica da narracao. Nada de sinonimo, traducao ou invencao -- "
        "termo fora da lista reprova o roteiro.\n"
        + "\n".join(blocos)
    )


__all__ = [
    "PILLARS",
    "Pillar",
    "brief",
    "normalize",
    "pillar_of",
    "suggest_pillar",
    "validate_terms",
]
