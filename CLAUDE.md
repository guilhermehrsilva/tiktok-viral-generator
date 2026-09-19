# Contexto do tiktok-viral-generator

Agente que detecta assunto em alta em **tech, IA e ciência**, ancora cada afirmação numa
fonte verificável, roteiriza e produz vídeo curto em pt-BR. Meta dupla: portfólio de AI
Engineer **e** canal com receita. Restrição rígida: **custo $0/mês**.

O README cobre arquitetura e como rodar. Este arquivo guarda o que não se deduz lendo o
código: por que ele é assim, onde paramos, e o que vem a seguir.

---

## Onde paramos

**M3 concluído.** Porta `LLM` com os dois adaptadores de free tier, pesquisador, roteirista
e juiz. 322 testes passando sem rede e sem chave. O agente vai do tema em alta ao MP4
sozinho, com motivo gravado em cada decisão do caminho.

O que já roda ponta a ponta, a custo zero:

| Comando | O que faz |
|---|---|
| `uv run agent radar` | coleta 4 fontes gratuitas (~19s) e grava a série |
| `uv run agent curate` | coleta, aplica 3 portões, escolhe 1 tema e grava o motivo de cada decisão |
| `uv run agent research` | monta o dossiê do tema: 3–5 fontes, cada fato com URL e trecho conferidos |
| `uv run agent write --out <json>` | escreve o roteiro do último dossiê, corrigindo sozinho o que é mecânico |
| `uv run agent judge --script <json>` | aplica a rubrica de 7 critérios; reprova na medida sem gastar token |
| `uv run agent produce --out <json>` | escreve, julga e revisa até passar (máx. 2 revisões) |
| `uv run agent llm-health` | confere qual id de modelo ainda responde, e a que custo |
| `uv run agent render --script <json>` | produz MP4 1080x1920 com narração pt-BR e legenda karaokê |
| `uv run agent health` | checa se o renderizador responde |

| `uv run agent publish --video <mp4>` | sobe o MP4 para a inbox do TikTok e grava o publish_id |
| `uv run agent publish-status --publish-id <id>` | consulta o estado e atualiza `posts` |
| `uv run agent tiktok-auth-url` | imprime a URL de autorização OAuth (escopo video.upload) |

**M4 commitado (b81b928 + fix 6b53033). Primeiro post real em 19/09/2026:**
`publish_id v_inbox_file~v2.7687247660403689473` (MP4 40,8 MB, 69s) subiu em
4 chunks para a inbox e chegou a `SEND_TO_USER_INBOX`, concluído no app pela
pessoa criadora. Falta para fechar o M4: app em produção aprovado no portal
(ícone + vídeo demo anexados, review submetida) — o piloto rodou em sandbox.

**M5 em andamento (fatia 1, 19/09/2026).** Chaves de LLM configuradas e
`llm-health` OK nos dois free tiers. Primeira rodada real no tema Bonsai 2:
pesquisador OK nos dois (4 fatos, 0 descartes), roteirista gemini OK (180
palavras, 1 tentativa), roteirista groq (`gpt-oss-120b`) falha 2x em
`json_validate_failed`, juiz gemini 12/14 x juiz groq 14/14 no mesmo roteiro.
`agent eval` (offline, sem cota) e `agent metrics-record` prontos, 376 testes.
Braço Claude **fora de escopo** (decisão do autor: sem API paga).

O aceite do M3 é conferível agora, sem chave nenhuma:

```bash
uv run agent judge --script fixtures/roteiro_sem_fonte.json   # reprova, 0 tokens, exit 1
```

### Verificado com chave em 19/09/2026

`llm-health` OK nos dois free tiers (gemini `gemini-2.5-flash`, groq
`openai/gpt-oss-120b`). Primeira rodada real no tema Bonsai 2 gravada no banco
(dossiês #2 e #3, roteiros #1 e #2, pareceres #3 a #5) e tabulada no README,
seção Eval. Achados: roteirista groq falha em `json_validate_failed`, juiz
groq 2 pontos mais generoso que o gemini no mesmo texto. Portão de trecho com
0 descartes nesta fonte -- sem sinal de aperto excessivo por enquanto.

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

### M3 — pesquisador + roteirista + juiz (concluído)

É onde entra **o primeiro LLM do projeto**, e a maior parte do valor de portfólio.

- ~~**Porta `LLM`** com adaptadores~~ **feito.** `gemini_free.py` e `groq.py` desde já,
  porque porta com um adaptador só é indireção. O adaptador Claude entra no braço pago do
  eval do M5 — a comparação medida é o artefato, não o modelo escolhido.
- ~~**Pesquisador**~~ **feito.** Descoberta por três trilhas grátis (`news_items` do
  Trends, artigo por trás do item do HN via Algolia, GDELT `artlist`), **uma chamada de
  modelo por fonte** e URL estampada por nós — o modelo nunca informa a fonte. Dois
  portões determinísticos antes de o fato entrar: o trecho citado tem de existir
  literalmente na página, e todo número da afirmação tem de estar na fonte.
- ~~**Roteirista**~~ **feito.** Produz um `Script` e corrige sozinho, em até três
  tentativas, tudo que é mecânico: faixa de 150–225 palavras (= 60–90s), `search_terms` em
  ASCII e em ordem cronológica, índice de fato existente no dossiê, número em dígito
  ancorado. O modelo **aponta** o fato por índice e nunca o reescreve, então a afirmação
  do roteiro continua rastreável à URL que o pesquisador estampou. Toda tentativa
  reprovada fica gravada — é o que revela prompt fraco.
- ~~**Juiz**~~ **feito.** Rubrica de 7 critérios, 0–2 cada, corte em 11/14 — e aprovar
  exige também **nenhum critério zerado** e **nenhum veto** (fonte, duração e política
  falham em requisito, não em qualidade). Três critérios saem de medida nossa, não do
  modelo; quando a medida já reprova, o modelo não é chamado. Até 2 revisões, com as
  notas ordenadas por custo (veto primeiro). Os sete critérios:
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

- **Aceite: atingido.** `tests/test_m3_aceite.py` e `fixtures/roteiro_sem_fonte.json` —
  a fixture adversarial é o roteiro de referência com **uma** afirmação inventada, e é
  reprovada por fonte mesmo recebendo parecer de nota máxima nos cinco critérios julgados.

### M4 — publicador
OAuth do TikTok + Content Posting API via `video.upload` (inbox — **não** exige auditoria).
Rótulo AIGC sempre ligado, sem flag para desligar. Respeitar 6 req/min por token.
Primeiro post real conferido no app antes de qualquer automação.

### M5 — eval e feedback loop (fatia 1 pronta; Claude fora de escopo)
Conjunto fixo de temas → roteiro por configuração de modelo → juiz cego, com custo medido.
~~Compara free tier contra Claude na mesma rubrica.~~ Braço pago fora de escopo (sem API
paga): a comparação é **free tier x free tier** (gemini x groq). Coleta métricas do post publicado
(views, watch time, completion) e liga ao roteiro que as gerou — o único sinal real de
viralidade. Também é onde a troca do deduplicador lexical por embedding vira experimento
medido, e não upgrade assumido.

Fatia 1 (19/09/2026): `agent eval` agrega offline roteiros e pareceres gravados
(escritor x juiz + matriz pareada no mesmo roteiro, parecer interrompido fora da
média); `agent metrics-record` grava a série por `publish_id` com `script_id`
opcional fechando o loop. Fatia 2 (19/09/2026): vocabulário visual do canal dark
(`writer/visuals.py`, 4 pilares A–D, tags fixas em inglês) com portão mecânico
no roteirista — validado com o gemini real (5 termos, pilar C, 1ª tentativa).
Fatia 3 (19/09/2026): humanizer como estágio (`writer/humanize.py`, adaptado
do `blader/humanizer` MIT: scan determinístico pt-BR + 1 reescrita travada por
grounding) e 3 formatos — `long` (contrato atual), `short` (~40 palavras, loop,
faixa 30–50), `carousel` (5 slides, teto 15/slide, save no 5, número no 1) com
juiz (6/8), slides PNG 1080x1920 (`render/carousel.py`, Pillow) e eval/métricas
por formato (saves/comments/shares). Roteamento medido: gemini escreve longo
mas estoura o curto (60–80 palavras, 3 rodadas); groq escreve curto (42) e
carrossel (8/8) de 1ª — e escreveu longo OK uma vez (176, 12/14), então o
`json_validate_failed` anterior pode ser prompt/transiente, não veredito.
Cota gemini 429 no fim do dia após uso intenso; groq segurou a rodada.
Calibrações: mirar 12 para caber no teto 15; exemplo de 40 palavras no prompt
short; número ≤5 isento do portão numérico do carrossel (é a contagem dos
slides). Falta: conjunto fixo com 2–3 temas (hoje só Bonsai 2)
e as primeiras métricas reais do app.

Fatia 4 (19/09/2026): estúdio de vozes local (`agent/voice/`, Piper/VITS em
CPU, RTF ~0,05–0,1 no i5). 3 vozes MIT/CC0 (razo/faber/jeff) + 10 estilos
(documental..calmo) como interpretação sobre os timbres; `voice-narrate` do
roteiro ao wav com `[PAUSA]` e `*enfase*`. Rejeitados com motivo: edresson-low
(nasal corrompida), F5/XTTS (NC/não-comercial), Bark (lento em CPU), Kokoro
(sem voz pt-BR). Lacunas: voz feminina aberta não existe; sotaque regional
ninguém reproduz (variedade = locutor). Amostras em `output/vozes/`.

Fatia 5 (19/09/2026): branding Seu Canal (`brand/brand.json` transcrito do
guia, `agent/brand/` como fonte única). Portões em todas as camadas: gancho
≤12 palavras, 1 número/frase, sem emoji/bordão (roteirista e carrossel);
promessa-que-não-paga zera no juiz (era o furo do slide "5 IAs"); slides na
paleta com 1 acento por pilar de conteúdo, Space Grotesk/Plex Mono,
`caption.txt` com as 5 hashtags; símbolo + avatar gerados de
`scripts/make_brand_assets.py`. Teto do slide 15→12 (marca manda).
Divergência assumida: guia mira 20–45s, monetização exige ≥60s — long mantém
voz/regras da marca na duração do Rewards.

Fatia 6 (19/09/2026): RAG de sujeito (`research/subject.py` — roteiro que não
nomeia reprova citando o que falta; pesquisador prefere fato com criador) e
fotos nos slides (`render/photos.py`: Pexels pela tag do pilar, cache,
overlay escuro; categoria auto pelo pilar de conteúdo). Armadilhas pagas:
Pexels barra UA do urllib (403) na busca E no download; `fetch` sem mkdir
engole o erro; chave no CLI vem de `AGENT_PEXELS_API_KEY` (Settings), não de
`os.environ`. Groq-long `json_validate_failed` recorrente + 429 geral no fim
do dia: rodada2 saiu com short novo, long/slides reaproveitados da rodada1.

Fatia 7 (19/09/2026): apresentadores do guia (Íris + Théo) no ecossistema.
`brand.json` ganhou `presenters` (prompts de identidade, seeds, negativo);
`presenter_for` trava por formato (só analise/tutorial/fato/vs, resto sem
avatar); `brand-avatar` imprime prompt travado + travas (geração é externa:
sem image-gen local $0). Voz: Théo usa `jeff` (estilo `theo`, amostra em
`output/vozes/amostra_theo.wav`); Íris segue sem voz aberta (gap declarado,
não gambiarra com timbre masculino).

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
- **`total_chunk_count` é piso, não teto.** A API exige `video_size // chunk_size`
  arredondado para baixo, com o último chunk absorvendo o resto (até 128 MB); cada
  chunk de 5 a 64 MB, abaixo de 5 MB sobe inteiro. O adaptador mandava teto e o init
  real devolvia 400 `invalid_params` -- e os testes mockavam o teto e passavam. Só o
  primeiro post real acusou. Mesma moral do MP4 mudo.
- **Teste que lê `.env` não é hermético.** `Settings()` vazio puxa o `.env`, então um
  teste de "sem credencial" passa sem chave na máquina e quebra com chave gravada.
  Credencial de teste vai explícita no construtor.

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
- **`MockTransport` entrega o corpo num único chunk.** Um teto de bytes implementado só
  como `break` no laço de `iter_bytes()` passa no teste e não vale nada contra um servidor
  real, que manda pedaços de 64 KB. O teto precisa cortar o acumulado também.
- **"5,9 GB" tokeniza em "5" e "9".** Dígito solto não é termo distintivo: a consulta do
  GDELT saía como `"27b 2 5"` e deixava o nome do produto de fora. Piso de 2 caracteres
  para token com dígito, 3 para o resto.
- **Sobreposição de vocabulário não serve para conferir fato.** As fontes de tech são em
  inglês e a afirmação sai em pt-BR: "retém 98,2% do desempenho" e *"retains 98.2% of
  performance"* não compartilham uma palavra. Só o número sobrevive à tradução — é por isso
  que o portão de ancoragem compara dígitos, e não texto.
- **Nota zerada em critério não avaliado não é crítica ao texto.** Quando o juiz reprova na
  medida e nem chama o modelo, os critérios de leitura ficam com zero e `evaluated=False`.
  Tratar isso como nota real mandaria o roteirista "melhorar o hook" por causa de algo que
  nunca foi julgado, e desperdiçaria a revisão no lugar errado.
- **`vetoed` só vale para critério de requisito.** Usar mínimo 1 como padrão fazia qualquer
  critério zerado aparecer como veto, e a CLI passava a dizer que *hook* é requisito de
  monetização — o que é falso. Critério de qualidade zerado reprova por outra regra.
- **Defeito mecânico não é trabalho do juiz.** Contagem de palavra, termo com acento e
  índice de fato inexistente são conferíveis sem rubrica. Mandar isso para o juiz gastaria
  uma rodada de revisão (e cota) para descobrir o que um `len()` já sabia.
- **Não pedir `source_url` ao modelo.** Fato real com fonte trocada parece ancorado, passa
  no juiz e só aparece quando alguém clica. Uma chamada por fonte, URL estampada por nós.
- **Lista no topo do JSON não deve virar o primeiro elemento.** Se o modelo devolve
  `[{...}, {...}]` onde se pediu um objeto, aproveitar o primeiro item devolveria um dossiê
  com um fato e nenhum aviso de que os outros foram jogados fora.
- **Segredos só no `.env`** (git-ignored).
