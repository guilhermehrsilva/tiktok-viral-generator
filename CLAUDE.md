# Contexto do tiktok-viral-generator

Agente que detecta assunto em alta em **tech, IA e ciência**, ancora cada afirmação numa
fonte verificável, roteiriza e produz vídeo curto em pt-BR. Meta dupla: portfólio de AI
Engineer **e** canal com receita. Restrição rígida: **custo $0/mês**.

O README cobre arquitetura e como rodar. Este arquivo guarda o que não se deduz lendo o
código: por que ele é assim, onde paramos, e o que vem a seguir.

---

## Onde paramos

**M2 concluído.** Três commits em `main`, árvore limpa, 111 testes passando sem rede.

```
b93cc38  M2: curador com tres portoes, score por percentil e ledger de temas
96ba51c  M1: radar de tendencias com quatro fontes gratuitas
a326219  M0: porta Renderer sobre o MoneyPrinterTurbo, com aceite medido
```

O que já roda ponta a ponta, a custo zero:

| Comando | O que faz |
|---|---|
| `uv run agent radar` | coleta 4 fontes gratuitas (~19s) e grava a série |
| `uv run agent curate` | coleta, aplica 3 portões, escolhe 1 tema e grava o motivo de cada decisão |
| `uv run agent render --script <json>` | produz MP4 1080x1920 com narração pt-BR e legenda karaokê |
| `uv run agent health` | checa se o renderizador responde |

**A lacuna é o meio:** `curate` entrega um tema, `render` consome um roteiro pronto. Ainda
não existe nada que transforme um no outro. É isso o M3.

### Para retomar o ambiente

```bash
./scripts/setup_renderer.sh --serve      # deixe rodando; sem isso `render` falha
uv run pytest && uv run ruff check .
```

- `uv` está em `~/.local/bin` (instalado sem root; o Fedora tem `uv` no dnf se preferir).
- `.env` já tem `AGENT_RENDERER_API_KEY`, `PEXELS_API_KEY` e `IMAGEIO_FFMPEG_EXE`.
  **Segredo só vive aí** — `scripts/setup_renderer.sh` é versionado.
- `.renderer/` é o clone do MoneyPrinterTurbo; deve seguir sem modificações rastreadas.
- `data/agent.db` tem a série do radar e o ledger de decisões (não versionado).
- O plano completo original está em `~/.claude/plans/iterative-sniffing-waterfall.md`.

---

## Três restrições externas desenharam tudo

1. **O open source resolveu a metade errada.** O MoneyPrinterTurbo (124,5k ★, MIT) faz
   roteiro → TTS → legenda → ffmpeg → MP4 muito bem e **não tem nenhuma detecção de
   tendência**. Por isso ele entra como *gráfica* atrás da porta `Renderer`, e o agente
   constrói só a metade de cima: radar, curadoria, grounding, juiz, eval.

2. **O Creator Rewards exige vídeo ≥ 60s e exclui "AI slop".** Conteúdo assistido por IA
   só é elegível se for original, transformativo e rotulado. Isso promove o grounding com
   citação de refinamento técnico a **requisito de monetização** — e é por isso que "toda
   afirmação tem fonte" e "ponto de vista próprio" são critérios da rubrica do juiz, não
   sugestões.

3. **A publicação do MPT é um SaaS pago** (`upload_post.py` → upload-post.com, free tier
   de 10 posts/mês). Sob a restrição $0, o publicador é nosso: Content Posting API oficial
   do TikTok, que é gratuita. O custo dela é a auditoria, não dinheiro.

---

## Para onde vamos

### M3 — pesquisador + roteirista + juiz (próximo)

É onde entra **o primeiro LLM do projeto**, e a maior parte do valor de portfólio.

- **Porta `LLM`** com adaptadores. Sob a restrição $0 o caminho padrão **não é Claude**:
  free tier do Gemini Flash ou Groq. Manter um adaptador Claude para o braço pago do
  eval do M5 — a comparação medida é o artefato, não o modelo escolhido.
- **Pesquisador.** Parte dos `news_items` que o Google Trends RSS já entrega de graça
  (título, veículo, URL), busca 3–5 fontes e extrai `Fact(claim, source_url, source_name)`.
  Os contratos `Fact` e `Dossier` já existem em `src/agent/models.py` e já validam:
  não existe `Fact` sem URL, nem dossiê sem fato.
- **Roteirista.** Produz um `Script` (contrato já existe e já é validado pelos testes do
  M0): hook ≤1,5s, corpo, fechamento, 60–90s, `search_terms` **em inglês e em ordem
  cronológica**. Toda afirmação factual ancorada num `Fact` do dossiê.
- **Juiz.** Rubrica de 7 critérios, 0–2 cada, corte em 11/14, com até 2 rodadas de revisão:
  1. hook abre lacuna de informação nos primeiros 1,5s
  2. toda afirmação factual tem fonte no dossiê
  3. duração falada entre 60 e 90s *(requisito de monetização)*
  4. ponto de vista próprio — não é resumo de notícia *(requisito de monetização)*
  5. nenhum termo da lista de política
  6. pt-BR falado, frases curtas
  7. fechamento com CTA que não seja "siga para mais"

  O `fixtures/roteiro_manual.json` é o **modelo do que o roteirista deve gerar** — inclusive
  o fechamento, que explora uma lacuna real da fonte (ela afirma "9x menor" e nunca informa
  o tamanho original). É isso que o critério 4 chama de ponto de vista próprio.

- **Aceite:** roteiro aprovado com 100% das afirmações rastreáveis a uma URL; fixture
  adversarial com afirmação sem fonte é reprovado pelo juiz.

### M4 — publicador
OAuth do TikTok + Content Posting API via `video.upload` (inbox — **não** exige auditoria).
Rótulo AIGC sempre ligado, sem flag para desligar. Respeitar 6 req/min por token.
Primeiro post real conferido no app antes de qualquer automação.

### M5 — eval e feedback loop
Conjunto fixo de temas → roteiro por configuração de modelo → juiz cego, com custo medido.
Compara free tier contra Claude na mesma rubrica. Coleta métricas do post publicado
(views, watch time, completion) e liga ao roteiro que as gerou — o único sinal real de
viralidade. Também é onde a troca do deduplicador lexical por embedding vira experimento
medido, e não upgrade assumido.

---

## Regras ao mexer aqui

- **Não fazer fork do MPT nem vendorizar o código dele.** A fronteira é HTTP e existe de
  propósito: mantém o repo leve, permite `git pull` das melhorias deles, e faz o portfólio
  mostrar o agente em vez de um fork. Se algo precisar mudar lá, resolver por configuração
  ou variável de ambiente.
- **Não sugerir provedor pago** sem dizer explicitamente que quebra a restrição de $0.
- **Não afirmar que o sistema detecta o que viraliza *no TikTok*.** Não existe API pública
  para isso: o Creative Center não expõe API e a Research API é restrita a pesquisa
  acadêmica. Detectamos assunto em alta na internet e inferimos.
- **Nenhuma estimativa de receita** até haver número medido do próprio canal.
- **Commits sem trailer `Co-Authored-By`** (regra global do autor: repo de portfólio,
  autoria é o que está sendo avaliado).
- **Toda decisão é gravada com motivo, inclusive as rejeitadas.** Sem isso só se sabe o que
  foi escolhido, nunca o que foi perdido, e calibrar vira chute.
- **Verificar o artefato, não o código de saída.** Foi assim que o MP4 mudo apareceu.

---

## Armadilhas já pagas — não repetir

- **`combined_videos` não é o corte final.** No MPT, `combined-N.mp4` é o concat só de
  vídeo e `videos` → `final-N.mp4` é o que tem narração e legenda. A primeira execução real
  baixou o errado e produziu um MP4 mudo que passou em dimensão e duração. Por isso
  `has_audio` é medido com `ffprobe` e é `False` por padrão.
- **O ffmpeg do Fedora não tem `libx264`.** É `ffmpeg-free`, sem os codecs sob patente —
  e libx264 é o encoder padrão do MoviePy e do passo de concatenação do MPT. O
  `setup_renderer.sh` detecta e aponta `IMAGEIO_FFMPEG_EXE` para o binário estático que o
  `imageio-ffmpeg` já traz. `h264_qsv` e `h264_vaapi` falham nesta máquina por falta de
  runtime, apesar de a Iris Xe aparecer em `/dev/dri`.
- **`grep -q` com `set -o pipefail` mente.** O grep sai cedo, o comando anterior morre de
  SIGPIPE e o pipeline reporta falha mesmo tendo encontrado. Capturar a saída numa
  variável antes de testar.
- **`content_tokens` tinha piso de 3 caracteres e matava "ai" e "ia".** Os dois termos mais
  centrais do léxico do nicho sumiam antes da comparação, e o recall do portão era 2/20 —
  rejeitava até o "Bonsai 2 27B", que é o tema do fixture de roteiro. O nicho tokeniza com
  piso 2; a deduplicação mantém 3.
- **Calibração do nicho é travada por teste** contra os 20 títulos reais em
  `tests/fixtures/radar/hacker_news.json`. Mexer no léxico sem rodar esse teste regride o
  recall em silêncio.
- **O plano previa embeddings para dedup; não use.** `sentence-transformers` arrasta >1,5 GB
  de CUDA (cudnn 527 MB, nccl 206 MB, cufft 204 MB, cusolver 191 MB) numa máquina sem GPU
  NVIDIA, e a variante CPU-only não instalou em 7 minutos. A implementação é lexical atrás
  da porta `Deduplicator`; trocar é experimento do M5, não upgrade óbvio.
- **Termos de busca vão direto para o Pexels**, sem tradução: precisam ser **em inglês** e
  em ordem cronológica casando com a narração. O modelo `Script` valida ASCII por isso.
- **Só `BeVietnamPro-Bold.ttf` cobre os acentos do pt-BR** entre as fontes do MPT; as
  outras são chinesas ou vietnamitas e renderizam tofu no lugar de "ç" e "ã".
- **A Wikipedia tem artigos de um caractere ("Q").** Título legítimo lá, inútil como tema,
  e estourava o `min_length` do `Signal` derrubando a fonte inteira.
- **Em português "lula" também é o molusco.** O filtro de política bloqueia um tema legítimo
  de biologia marinha por engano. O erro é assimétrico de propósito e está documentado em
  teste: deixar passar política partidária custa muito mais caro que perder um vídeo sobre
  cefalópodes.
- **Segredos só no `.env`** (git-ignored).
