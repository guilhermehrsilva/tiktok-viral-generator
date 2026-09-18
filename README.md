# tiktok-viral-generator

Agente que detecta assunto em alta em **tech, IA e ciência**, ancora cada afirmação numa
fonte verificável, roteiriza e produz vídeo curto em pt-BR.

O recorte é deliberado. Já existe open source maduro que transforma um tema em MP4 —
o [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) (MIT) faz isso muito
bem. O que não existe é a metade de cima: **descobrir o que vale a pena falar, e provar
que o que se fala é verdade.** É essa metade que este repositório constrói.

> Estado atual: **M1 concluído** — o radar coleta e mede; o pipeline de produção
> fecha a custo zero. Veja [Marcos](#marcos).

## Por que grounding com citação não é enfeite

O Creator Rewards do TikTok exige vídeo de no mínimo 60 segundos, conta apenas *qualified
views*, e exclui explicitamente conteúdo "AI slop". Conteúdo assistido por IA é elegível
quando é **original, transformativo e rotulado**.

Ou seja: o estágio que extrai fatos com fonte e o estágio que exige ponto de vista próprio
no roteiro não são refinamento de engenharia — são o que separa um canal monetizável de um
canal desmonetizado. Por isso eles são critérios da rubrica do juiz, não sugestões.

## Arquitetura

O agente é dono do julgamento; tudo que é substituível fica atrás de uma porta.

```
radar → curador → pesquisador → roteirista → juiz → [Renderer] → [Publisher]
                      ↑              ↑         ↑
                  [LLM] ────────────────────────┘
                      ↑
                  memória (SQLite + embeddings locais)
```

O `Renderer` é uma porta porque a primeira implementação delega ao MoneyPrinterTurbo
rodando como serviço local. **Não fazemos fork nem vendorizamos:** `scripts/setup_renderer.sh`
clona o projeto em `.renderer/` (git-ignored) e sobe o FastAPI dele. Nosso agente passa
roteiro e termos de busca prontos, o que contorna o LLM dele por completo —
`task.py:generate_script` só chama o LLM quando `video_script` chega vazio.

## Restrição: custo zero

Todo o caminho de produção roda sem cartão de crédito:

| Camada | Implementação | Custo |
|---|---|---|
| Radar | Hacker News (Algolia), Google Trends RSS, Wikipedia pageviews | $0, sem chave |
| Narração | edge-tts, vozes `pt-BR-{Thalita,Francisca,Antonio}` | $0, sem chave |
| Legenda karaokê | tempos por palavra do próprio edge-tts (`SubMaker`) | $0 |
| Material | Pexels / Pixabay | $0, cadastro grátis |
| Montagem | ffmpeg | $0 |
| Publicação | Content Posting API oficial do TikTok | $0 |

O `upload-post.com` que o MoneyPrinterTurbo usa para publicar é um SaaS com free tier de
10 posts/mês — por isso o publicador é nosso.

## Rodando

Requer `ffmpeg`, `git` e [`uv`](https://docs.astral.sh/uv/) no PATH.

```bash
# 1. dependências do agente
uv sync

# 2. renderizador (clona ~340 MB em .renderer/, instala com Python 3.12)
#    A chave do Pexels é grátis: https://www.pexels.com/api/
PEXELS_API_KEY=sua-chave ./scripts/setup_renderer.sh

# 3. sobe o renderizador (deixe rodando)
./scripts/setup_renderer.sh --serve

# 4. em outro terminal: renderiza o roteiro de referência
uv run agent render --script fixtures/roteiro_manual.json
```

O comando imprime as dimensões e a duração **medidas com `ffprobe`** e falha se o MP4 não
sair em 1080x1920 ou fora da faixa de 60–90s. Aceite medido, não presumido.

```bash
uv run pytest          # 28 testes, sem rede
uv run ruff check .
```

### Sem chave do Pexels

Dá para fechar o caminho inteiro sem nenhuma chave, usando material local. Os clipes
são gerados por ffmpeg (não versionados — são ~9 MB de gradiente) e servem só para
provar a cadeia de produção (narração, legenda, montagem) sem rede:

```bash
./scripts/make_test_material.sh

AGENT_VIDEO_SOURCE=local \
AGENT_LOCAL_MATERIALS='["fixtures/material/placeholder-1.mp4","fixtures/material/placeholder-2.mp4","fixtures/material/placeholder-3.mp4"]' \
uv run agent render --script fixtures/roteiro_manual.json
```

Os arquivos sobem por HTTP (`POST /api/v1/video_materials`) em vez de serem copiados
para o disco do renderizador — é o que mantém a porta válida se ele sair desta máquina.

### Fedora: o ffmpeg do sistema não serve

O Fedora distribui `ffmpeg-free`, compilado sem os codecs sob patente — **não tem
`libx264`**, que é o encoder padrão do MoviePy e do passo de concatenação do MPT. Sem
tratar isso, o render morre no final, depois de gastar todo o TTS e a montagem.

O `setup_renderer.sh` detecta e resolve sozinho: o `imageio-ffmpeg`, que já vem como
dependência do MoviePy, traz um binário estático com `libx264`, e o
`utils.get_ffmpeg_binary()` do MPT honra `IMAGEIO_FFMPEG_EXE` antes do PATH. Nenhuma
linha do código dele é modificada.

## O radar

```bash
uv run agent radar
```

Quatro fontes gratuitas, rodando em ~19s. Cada uma falha isolada: a janela de um trend é
de horas, então nenhuma fonte fora do ar derruba a coleta.

| Fonte | Unidade | Velocidade | Papel |
|---|---|---|---|
| Hacker News (Algolia) | `points` | **nativa** — `points / idade` | primária do nicho |
| Google Trends RSS | `searches` | por diferença | cobertura Brasil + matérias já associadas |
| Wikipedia pageviews | `pageviews` | por diferença | confirma interesse real em pt |
| GDELT DOC 2.0 | `articles` | por diferença | cobertura global, com disjuntor |

O radar **não normaliza** as unidades numa nota única. Pontos do HN e pageviews da
Wikipedia não são comparáveis, e converter escalas diferentes num número só é julgamento —
julgamento é trabalho do curador (M2). O radar coleta e mede.

A única grandeza comparável em forma é a **velocidade**, porque é sempre a mesma derivada:
unidade por hora. Ela é `None` quando desconhecida, nunca zero — `None` significa "não
medi" e zero significaria "medi e não se moveu", que são afirmações diferentes e levam a
decisões diferentes.

O Hacker News é a fonte primária porque é a única gratuita que entrega velocidade **já na
primeira coleta** (`points` + `created_at_i`). As outras reportam nível, não taxa, e
precisam de duas coletas para dizer qualquer coisa sobre movimento — a série fica em
SQLite.

## Marcos

| | Marco | Estado |
|---|---|---|
| M0 | Porta Renderer + aceite medido do MP4 | **concluído** |
| M1 | Radar (HN, Trends, Wikipedia, GDELT) | **concluído** |
| M2 | Curador: score, filtro de política, dedup por memória | a fazer |
| M3 | Pesquisador + roteirista + juiz com rubrica | a fazer |
| M4 | Publicador (TikTok, inbox, rótulo AIGC) | a fazer |
| M5 | Eval: free tier vs. modelo pago na mesma rubrica | a fazer |

## Limites conhecidos

Publicados aqui de propósito, não escondidos.

- **Nenhuma API pública diz o que viraliza *no TikTok*.** O Creative Center não expõe API
  e a Research API é restrita a pesquisa acadêmica. Detectamos assunto em alta na internet
  e inferimos. São coisas diferentes, e o projeto não finge o contrário.
- **O Google Trends RSS não é API oficial** e pode mudar sem aviso. A API oficial seguia em
  alpha com acesso por inscrição em ago/2026; o `pytrends` foi arquivado em abr/2025.
- **Não há como anexar som em alta do TikTok por API** — só a Commercial Music Library ou
  o áudio do próprio arquivo. É um teto real de alcance.
- **O GDELT devolve 429 com frequência** sem chave (2 de 3 tentativas nos testes), por isso
  entra com backoff e circuit breaker, nunca como fonte única.
- **Reddit exige OAuth**: JSON e RSS devolvem 403. Ficou fora do M1.
- **O edge-tts usa o endpoint de leitura em voz alta do Edge.** Grátis, sem contrato, pode
  quebrar. O fallback planejado é o Kokoro-82M local (Apache 2.0, vozes pt-BR), que roda
  em CPU.
- **Viralidade não é previsível offline.** A rubrica mede qualidade de roteiro, não
  resultado. O único sinal real é retenção pós-publicação, e é isso que o M5 coleta.
- **Nenhuma estimativa de receita será publicada** até haver número medido do próprio canal.
- **O aceite verifica o artefato, não o código de saída.** A primeira execução real
  produziu um MP4 mudo que passava em dimensão e duração: o adaptador baixava
  `combined_videos` (o concat só de vídeo) em vez de `videos` (o corte com narração e
  legenda). `has_audio` é medido com `ffprobe` e é `False` por padrão, para que silêncio
  nunca seja o default aprovado.

## Licença e créditos

O renderizador é o [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)
de Harry, sob licença MIT. Não está incluído neste repositório: é clonado em tempo de
setup e consumido por HTTP.
