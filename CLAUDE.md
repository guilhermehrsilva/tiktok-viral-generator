# Contexto do tiktok-viral-generator

Agente que detecta assunto em alta em **tech, IA e ciência**, ancora cada afirmação numa
fonte verificável, roteiriza e produz vídeo curto em pt-BR. Meta dupla: portfólio de AI
Engineer **e** canal com receita. Restrição rígida: **custo $0/mês**.

O README cobre arquitetura e como rodar. Este arquivo guarda o que não se deduz lendo o
código: por que ele é assim, onde paramos, e o que vem a seguir.

---

## Onde paramos

**M6 — piloto automático ligado em 19/09/2026 (noite).** Desde 20/09/2026 são
**quatro posts por dia** — 09h, 12h, 16h e 19h de Brasília — sem comando manual.
A grade alterna **curto (~25s) e longo (60-90s)**: curto às 09h e 16h (alcance), longo
às 12h e 19h (monetização — o Rewards exige 60s). O **carrossel saiu da grade** e
continua alcançável por `slot-extra --format carrossel`. Instalado como serviços de
usuário do systemd (`./scripts/install_autopilot.sh`, linger ligado). Cada timer dispara
35 min antes e roda `uv run agent slot --slot <HHMM>`: radar (8 fontes) → curador → nota de interesse do
público (1 chamada) → tema e tipo de conteúdo para o horário → pesquisa → **formato
escolhido pela informação** (longo/curto/carrossel, com motivo) → roteiro + juiz de outra
família → render próprio em ffmpeg → espera a hora → inbox do TikTok (vídeo) ou pacote
para postar (carrossel) → aviso. 553 testes sem rede.

| Comando | O que faz |
|---|---|
| `uv run agent slot --slot 0900 [--no-publish] [--no-wait] [--force]` | um slot inteiro (o que o timer chama) |
| `uv run agent autopilot-status [--detail] [--day AAAA-MM-DD]` | o dia: estado de cada slot, motivos, cota e tokens por modelo |
| `journalctl --user -u 'seucanal-*' -f` | log ao vivo dos slots |
| `systemctl --user list-timers 'seucanal-*'` | próximos disparos |
| `./scripts/install_autopilot.sh --remove` | desliga tudo |

O que mudou em relação ao M5, e por quê (cada item veio de medida, não de palpite):

- **Roteador de LLM por cota** (`adapters/router.py`, `memory/llm_ledger.py`). O
  gemini-2.5-flash tem **20 pedidos/dia** no free tier (medido no 429:
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier = 20`). Cada estágio tem uma rota
  ordenada de modelos (Gemini 3.8/3.5 flash, flash-lite, Groq gpt-oss-120b/20b, qwen);
  cota do dia esgotada vai para o livro até o reset (meia-noite do Pacífico = 4h/5h de
  Brasília), cota do minuto (TPM do Groq) espera o `retry-after`, 503 tira o modelo por
  10 min. Groq agora usa **saída estruturada estrita** (`json_schema`): acabou o
  `json_validate_failed` e o schema saiu do prompt.
- **Editorial** (`editorial/`): 7 tipos de conteúdo = pilares da marca + **história**
  (novo, pedido do autor). A fórmula de gancho/batidas/CTA de cada pilar existia no
  `brand.json` e **não chegava a prompt nenhum** — agora chega ao roteirista e ao juiz.
  Formato = horário (prior declarado) + tipo (afinidade) + o que o dossiê aguenta
  (medido) − repetição no dia + desempenho medido (quando houver amostra ≥3 por formato).
- **Radar**: RSS pt-BR e global agrupados por história (veículos cobrindo = sinal de
  engajamento com velocidade nativa), Hugging Face em alta, Wikipedia "neste dia" e um
  arquivo atemporal de história/curiosidade como reserva.
- **Renderizador próprio** (`adapters/ffmpeg_renderer.py`, padrão; MPT virou reserva):
  narração edge-tts com **dicionário de pronúncia** (voz lê "Djémini", legenda mostra
  "Gemini"), vozes monolíngues pt-BR (Francisca; Antonio em tutorial/VS), legenda karaokê
  de 3 palavras na fonte da marca, clipes escolhidos por relevância + escuridão, **trilha
  gerada localmente** (sem direito autoral) com ducking, loudness −14 LUFS, cartão do
  gancho nos 3 primeiros segundos. ~20s de render contra ~5,5 min no MPT. O Whisper do
  Groq transcreve cada narração e acusa nome próprio que o ouvinte não reconheceu
  (`data/pronuncia_suspeita.txt` = candidatos ao léxico).

**O que ainda exige a mão do autor** (limite de plataforma, não de código):

1. **Vídeo**: chega à inbox do TikTok; concluir no app (legenda do `caption.txt`, rótulo
   AIGC ligado). Postar direto exige o escopo `video.publish` **e** auditoria do app.
   Inbox acumula: com mais de ~5 envios pendentes o TikTok devolve
   `spam_risk_too_many_pending_share` — concluir ou apagar os rascunhos todo dia.
2. **Carrossel**: a API de foto só aceita `PULL_FROM_URL` de domínio/prefixo verificado no
   portal do TikTok. Até verificar um (ex.: GitHub Pages), o slot fica `ready_manual`: os 5
   slides + legenda no pacote e aviso.
3. **Máquina ligada** nos horários (timer com `Persistent=true` roda ao ligar; atraso >2h
   pula o slot para não colar em outro post).
4. **Aviso no celular** é opcional: `AGENT_NTFY_TOPIC=<nome-longo-aleatorio>` no `.env` e o
   app ntfy inscrito nesse tópico.

**M7 — em andamento (20/09/2026, manhã).** Quatro frentes pedidas pelo autor:

- **OpenRouter principal** (`adapters/openrouter.py`, posterior ao Groq como molde).
  A cota do Gemini no AI Studio disputa requisição com outras automações dele, e o
  endpoint pago do OpenRouter não consome aquela cota — então toda rota abre com
  OpenRouter barato (`deepseek-v4-flash` na pesquisa/ranker/juiz,
  `gemini-2.5-flash-lite` no escritor/humanize) e o Gemini direto fica por último.
  402 (sem crédito) vira cota do dia e segue para groq/gemini. Estimativa: ~$0,01 por
  vídeo → $100 duram anos. Falta: `AGENT_OPENROUTER_API_KEY` no `.env` (segredo só
  aí) + `llm-health` ao vivo + medir se algum modelo sustenta `json_schema` estrito
  (allowlist começa vazia de propósito).
  **Medido em 20/09/2026 (manhã):** chave no `.env`, `llm-health` OK nos 3 provedores
  (`deepseek-v4-flash` 0,89s). `json_schema` estrito funciona nos 2 modelos da rota
  (deepseek-v4-flash e gemini-2.5-flash-lite, 200 + JSON aderente) → allowlist
  preenchida, schema saiu do prompt (economia de entrada em toda chamada). 589 testes.
- **Degrau pago por tarefa (20/09/2026, manhã).** Teto do autor $0,10–0,15/
  vídeo: escritor/humanize abrem no `gemini-2.5-flash`, juiz no `deepseek-v4-pro`
  (cruza família), pesquisa/ranker ficam no flash barato. Medido: ~$0,01/vídeo
  (10x de folga). Mesma manhã: o 2.5-flash repetiu o traço da família e estourou
  o teto do curto 2x (65 e 53 palavras) → rota `writer_short` nova, curto abre
  no groq (medido bom em 19/09), premium só no longo/carrossel/humanize.
- **Carrossel sempre às 20h** (`FORMATO_FORCADO`, ordem aplicada no runner, short de
  emergência se o dossiê não sustenta 5 slides). Troca assumida: a noite deixa de
  ser o vídeo longo monetizável — o slot das 20h vira pacote manual.
- **Fio no carrossel (20/09/2026, tarde).** Reclamação do autor com razão:
  slides-fragmento ("Lançado em 2026 com a mesma ideia" — a mesma ideia do QUÊ?).
  Causa: o prompt pedia frase curta por slide sem instrução de ligação, e o juiz
  (hook/fonte/cta) não media fluxo. Correção: regra de fio no roteirista (cada
  slide se entende sozinho) + 4º critério `fluxo` no juiz (corte 8/10, zero
  bloqueia e volta como nota de revisão). Limite honesto medido no artefato de
  hoje: o juiz ao vivo ainda deu 2/2 no fluxo mesmo com teste de isolamento e
  extração-antes-da-nota — generosidade de coerência é ponto mole de juiz LLM
  (mesma família do groq-generoso). Aposta: a correção morre no roteirista
  (fio), não no juiz; o slot das 20h de hoje é o experimento natural.
- **Cobertura de agentes**: radar/curador/planejador → escritor → voz → vídeo/
  carrossel → juiz (+preflight) → publicador/inbox + aviso. "Edição" é o humanizer
  + a montagem determinística do render (clipes, legenda, música, loudness); não há
  agente-editor separado.
- **THÉO filmado, boca nossa (20/09/2026, noite) — terceira reescrita.**
  O autor gerou no Hailuo um clipe fotorrealista do THÉO com a
  identidade travada do `brand.json`, e isso vira o desenho
  anterior de cabeça para baixo: **a piscada, o balanço de cabeça e a respiração
  deixam de ser sintetizados e passam a vir do clipe**, porque lá eles são
  humanos de verdade. Sobra para nós só a boca — a única coisa que depende
  da narração daquele vídeo e que, portanto, não pode vir pronta. Ele
  escuta de lábios fechados do primeiro ao último quadro (conferido nos
  141 e depois nos 362), que é o neutro ideal: não há movimento de lábio
  do modelo brigando com o nosso.
  - `scripts/make_presenter_video.py` (efêmero no `uv`, rembg +
    mediapipe, mesma decisão do recorte parado) assa o clipe em
    `theo_base.mp4` (cor pré-multiplicada + máscara, duas trilhas) +
    `theo_base.json` com **os pontos do rosto em cada quadro**. Sem isso a
    boca desenhada em coordenada fixa descola do rosto no primeiro balanço.
    Matting com `u2net_human_seg` e mediana temporal de 3 quadros contra a
    fervura da borda do cabelo.
  - `render/visemes.py`: grafema→fonema→visema de pt-BR sobre o tempo de
    palavra do TTS. Era o "fora de escopo declarado" da manhã, e num rosto
    fotorrealista virou requisito: boca aberta no /m/ é gatilho forte de
    vale da estranheza. A **forma** vem da letra, o **tamanho** vem da
    envoltória RMS (`modular`), e o fecho bilabial é reimposto depois da
    suavização — interpolado entre duas vogais ele sobrevivia como um
    respiro de 0,3 de abertura, que é exatamente o defeito a matar.
  - `render/presenter_video.py`: clipe em **vai-e-vem** (medido: o melhor
    corte entre quadros não vizinhos custa 6,74/255 contra 1,13 entre
    vizinhos — seis vezes o movimento normal, visível a cada volta). Preço
    declarado: a piscada toca ao contrário uma vez por ciclo. Com o clipe
    de 15s a volta só acontece em vídeo longo.
  - **THÉO apresenta todos os pilares** e a **voz segue quem aparece**
    (Antonio em todo vídeo com apresentador): rosto masculino com narração
    feminina seria incoerência maior que qualquer defeito de boca. A Íris
    não foi removida — ficou com `formats: []` e volta sozinha quando
    `iris_base.json` existir.

  Três defeitos medidos e corrigidos no caminho, todos do tipo que passa em
  teste de código de saída:
  1. **`"" in "mn"` é `True` em Python.** A regra "vogal seguida de m ou n"
     também casava com o fim da palavra: *toda* palavra terminada em vogal
     ganhava boca de vogal nasal (`bonito` → `P o T i T o~`). A mesma
     armadilha estava em mais três comparações (`prox in "ei"` não pega
     "ê" nem "í", e "você" saía com [k] duro).
  2. **A mandíbula girava errado.** A primeira versão descia em bloco tudo
     abaixo da linha dos lábios. No centro o vão pintado escondia a emenda;
     dos cantos da boca para fora sobrava um **degrau nu de 61 px
     atravessando a bochecha** — um risco horizontal de um lado ao outro do
     rosto. O osso gira em torno da articulação perto da orelha: a amplitude
     cai com a distância ao centro e a rampa começa mais alto e fica mais
     longa. `campo_maxilar` saiu como função própria justamente para o teste
     medir o campo em pixel em vez de olhar a imagem e achar que está bom.
  3. **A boca descansava tarde.** O repouso só entrava um pouco antes da
     palavra seguinte, então numa pausa de 2,4s entre frases a boca ficava
     escancarada no /a/ final o tempo todo. Agora o descanso entra também
     no **fim** da palavra.

  **O portão do quadro passou a mentir, e foi trocado.** `conferir_apresentador`
  comparava final x bruto dentro da máscara contra um anel em volta — ou
  seja, media "alguma coisa mudou aqui". Com o apresentador fotorrealista e
  o cartão do gancho logo acima dele, o anel passou a mudar tanto quanto a
  máscara e o veredito saiu **NAO CHEGOU AO QUADRO num vídeo que tinha o
  apresentador no quadro** (conferido a olho no artefato das 18h55). Alarme
  que dispara sempre é alarme que ninguém lê. A medida nova compara o final
  com a **própria camada** (correlação dentro da máscara, onde o alfa é
  cheio): eq e vinheta mudam o nível do pixel e não desmancham a estrutura
  do rosto; b-roll no lugar do avatar não correlaciona com rosto nenhum.

  **A boca não convenceu, e a reclamação estava certa (20/09/2026, noite).**
  O resto do vídeo passou; a boca não. Medi antes de mexer, e o diagnóstico
  se partiu em duas metades independentes:

  *Dinâmica.* Sincronia estava boa (lag de 1 quadro, −33 ms). O defeito era
  o interpolador: ele **segurava o visema parado e saltava** em 70 ms.
  Medido na narração de 16,5s: salto médio de **0,109** entre quadros,
  **0,381** no p95 — 38% do curso em 33 ms. Isso lê como estalo. Trocado
  por massa-mola criticamente amortecida (`_inercia`), alvo constante pela
  **duração** de cada fonema e filtro rodando a 4x a taxa de quadro (a
  constante de 35 ms é menor que o quadro de 33 ms — a mesma armadilha já
  paga na envoltória). Depois: salto médio **0,069**, p95 **0,213**. E de
  brinde vem o **undershoot**: na fala corrida ninguém articula cada fonema
  por inteiro, e a escada articulava tudo com perfeição igual, que é o jeito
  mais rápido de soar robô. Taxa conferida contra o áudio (referência
  honesta, não gosto): **3,7 picos/s** contra 3,9 da energia da narração.

  *Forma.* Na ampliação 2x apareceram quatro coisas, todas do mesmo erro de
  fundo — eu desenhava uma **elipse inventada** onde o mediapipe já media o
  contorno do lábio e eu simplesmente não o tinha gravado:
  1. a elipse tem tangente vertical no canto, boca tem canto em bico: ela
     avançava por cima da borda do lábio de cima;
  2. onde ela não alcançava sobrava o lábio **duplicado** pela deformação;
  3. o lábio de baixo deslizava como **laje rígida**, sem afinar;
  4. o esticar horizontal usava uma caixa de 121 px (do nariz ao queixo) e
     **ondulava a barba** a cada sílaba.

  Agora o vão é o polígono entre a **linha de costura dos lábios** e ela
  deslocada pela queda do maxilar — área zero em repouso por construção (os
  dois arcos da malha ficam 1–3 px separados mesmo de boca fechada, e usar o
  arco cru pintava um risco escuro permanente). Três tentativas erradas no
  caminho, todas visíveis: polígono com os arcos no mesmo sentido → um **X**
  dentro da boca; sem perfil de comissura → uma **barra retangular**, porque
  canto de boca não abre; `sin(π·1)` dá −8,7e−17 e base negativa com expoente
  fracionário vira **NaN**, que desceu até o índice da reamostragem. O dente
  ganhou **aresta de corte** (sem ela lia como barra de metal polido) e
  entrou língua, porque vão preto lê como buraco recortado no rosto.

  **Marca d'água do Hailuo, achada por acaso.** Ampliando um quadro para
  olhar a boca apareceu "MINIMAX | Hailuo AI" queimada no peito do THÉO —
  ela atravessou o primeiro assado inteira. Marca de outra ferramenta num
  canal que precisa passar por originalidade para monetizar. Ninguém tinha
  olhado o peito dele ainda; todo mundo olhava o rosto. `linha_da_marca`
  acha pela interseção de "variância temporal ~zero" com "bem mais claro que
  a camiseta preta" (medido: y 1290-1305, x 459-741 em 1344 linhas) e o
  assado corta acima dela — 1272 → 1210 linhas, dentro da faixa que já saía
  em degradê. Conferido depois: nenhuma marca remanescente.

  Moral repetida, terceira vez no mesmo arquivo: **o defeito aparece na
  ampliação, não no teste que roda.** E o corolário novo: ampliar por um
  motivo acha defeito de outro.

- **Grade de 4 posts (20/09/2026, noite).** Pedido do autor: 09h curto,
  12h longo, 16h curto, 19h longo, tudo em Brasília, tudo vídeo. O carrossel
  saiu dos horários fixos (segue em `slot-extra --format carrossel`). O
  `short` subiu de ~15s para **~25s** e o `long` ficou como estava — os 60s
  do pedido são o piso do Creator Rewards, não um alvo, e a faixa 60-90s dá
  espaço para o arco.

  **"Ordem forçada" nunca foi ordem.** `FORMATO_FORCADO` sempre foi descrito
  como preferência ("o segundo elemento é emergência, não alternativa") e
  `choose_format` tratava a tupla como *lista de permitidos*, escolhendo pela
  nota. Passou despercebido enquanto o único slot forçado era o carrossel das
  20h, que pontuava alto sozinho. Com `("long", "short")` no almoço e à noite,
  o curto ganha do longo em pilar de notícia (afinidade 0,50 × 0,35) e os dois
  slots longos do dia sairiam **curtos** — o contrário do que a grade pede.
  Agora existe `em_ordem=True`, usado só quando há grade forçada. Achado
  conferindo a grade montada, não por teste; travado em teste depois.

  Duas armadilhas de constante duplicada, as duas pagas na mesma tarde:
  1. **`SLOT_PRIOR["1500"]` era o padrão escrito dentro de `choose_format`.**
     Com a grade nova aquele id deixou de existir: um `KeyError` esperando o
     primeiro `slot-extra`. Virou `PRIOR_PADRAO`, nomeado.
  2. **A faixa do curto morava em dois lugares** — palavras no `writer`
     (30-50) e segundos no `judge` (`(10, 20)`, cravado). Subi só a primeira
     e o juiz passou a reprovar *todo* curto que o roteirista aprovava, com a
     mensagem genérica "nenhum formato aprovado pelo juiz", que não aponta
     para lugar nenhum. Agora as duas saem de `SHORT_MIN/MAX_DURATION_S` em
     `models.py`, ao lado da faixa do longo. Duas constantes para o mesmo
     fato sempre divergem.

  O `install_autopilot.sh` agora **apaga os timers da grade antiga** antes de
  instalar: unidade órfã em `~/.config/systemd/user` continua disparando, e
  reinstalar deixaria o 15h e o 20h produzindo em paralelo com a grade nova.
  Conferido depois de instalar: 4 timers ativos, nenhum 1500/2000 em disco.

  **`agent rerender` (20/09/2026, noite).** Nasceu de uma falha: tentar ver a
  boca nova numa peça de produção custou uma rodada inteira que terminou em
  `FAILED` — 4 temas tentados, nenhum aprovado, porque as rodadas do dia já
  tinham consumido as pautas boas. A parte cara de testar uma mudança de
  render é justamente a que não mudou (radar, pesquisa, roteirista, juiz):
  gasta cota, disputa pauta com os slots e pode não aprovar nada. Um roteiro
  que **já passou pelo juiz** é material legítimo, então `rerender` refaz só
  o vídeo, chamando `SlotRunner.render_video` — o mesmo caminho da produção,
  não uma segunda implementação que diverge com o tempo.

      uv run agent rerender --script <roteiro.json> [--out-dir <pasta>]

  Foi por aí que o portão corrigido se confirmou ao vivo: `apresentador no
  quadro: OK (correlacao com a camada 1,00, 289103 px)`.

  Armadilha de grade, paga: o slot das **20h é carrossel** (`FORMATO_FORCADO`)
  e carrossel **não tem apresentador**. Esperar o slot da noite para conferir
  uma mudança de boca não testa nada — e o timer dispara 35 min antes, então
  às 19h43 o pacote das 20h já estava pronto desde as 19h31.

  Rodada real de 20/09/2026 18h55, `slot-extra --format short --no-publish`:
  short de 17,4s com THÉO. 684 testes.
  Inspeção sem gastar slot: `uv run agent presenter-preview --script <json>`
  (usa o clipe base; `--still` força a reserva sintetizada).

- ~~**Apresentador animado (20/09/2026, tarde) — reescrita.**~~ **substituído pelo clipe filmado**
  (acima). Segue aqui porque é a reserva quando não há clipe base. As três
  tentativas da manhã (cutout na chamada, arte recortada, movimento
  procedural) estão descritas abaixo porque o erro é o que ensina:
  `render/presenter.py` sintetiza a silhueta **inteira** falando, quadro a
  quadro, sem modelo e sem API. Boca pela envoltória RMS da narração (ataque
  25 ms / relaxamento 55 ms), piscada com semente fixa, cabeça e tronco em duas
  camadas de máscara complementar girando em torno de um pivô no peito, e
  **encenação pelo roteiro**: grande na chamada → canto durante o corpo → volta
  no fechamento, com as batidas vindas do tempo de palavra do TTS. O cartão do
  gancho e a legenda karaoke passaram a obedecer a encenação (`Encenacao`
  decide `legenda_y`, `legenda_inicio` e `cartao_s`): enquanto ele está grande
  quem escreve o gancho é o cartão, e a legenda entra quando ele encolhe.
  Reclamação do autor que originou tudo, e ela estava certa: "praticamente
  manteve a imagem retangular e apenas colocou um movimento nela". Referência
  que ele mandou: Lu do Magalu (#PayDayMagalu).
  Medido no i5 sem GPU: 2012 quadros (67s) em 56s, 28 ms/quadro, camada 8,7 MB.
  Inspeção sem gastar slot: `uv run agent presenter-preview --script <json>`.
- **Boca e pálpebra: serrilhado e mecânica (20/09/2026, noite).** Reclamação do
  autor: lip sync e piscada "artificiais, mecânicos", bordas "serrilhadas
  durante a interpolação". O vocabulário da queixa era de engine 3D (MSAA/TAA,
  blendshape, viseme) e aqui não há nenhum dos três — é numpy + Pillow quadro a
  quadro. Antes de mexer, medi; e a **primeira hipótese caiu**: a silhueta está
  boa (matte com rampa de 3 px, e o afim bilinear a 1,75x de redução difere de
  uma referência super-amostrada 4x em 0,09/255, zero pixel acima de 32). AA
  global seria gasto no lugar errado. Os defeitos reais, todos medidos:
  1. `ImageDraw.ellipse` do Pillow **não tem anti-aliasing** — zero pixel de
     borda parcial em 12, 26 e 44 px. O borrão gaussiano depois não resolve: o
     degrau já está assado. Agora a máscara sai em 4x e desce por média de área
     (`Image.BOX`). Só a máscara, nunca a cor — reduzir RGBA sobre fundo
     transparente devolveria a franja escura que o `encode_command` evita.
  2. **Canto da boca truncado em inteiro**: entre abertura 0,36 e 0,39 ela
     saltava 1 px de lado enquanto crescia 1 px. A parte fracionária agora entra
     nas coordenadas do desenho grande; a boca anda em passos de 0,125 px.
  3. **Sombra do cílio presa a linha inteira** (`int(round(linha))`, faixa dura
     de 2 px): saltava 31 px entre dois quadros. Virou peso contínuo centrado na
     posição fracionária.
  4. **Extrapolação abaixo do cílio**: com o olho quase fechado o divisor ia a
     zero, a inclinação explodia e 5 px da pálpebra inferior grudavam na mesma
     linha de origem. Teto de compressão (3x) + volta à identidade em 0,6 altura
     de olho. Primeira tentativa de correção **piorou** (47 linhas) — a medida
     pegou, o olho não pegaria.
  5. **Ataque de 25 ms menor que o quadro de 33,3 ms**: o filtro não filtrava
     nada. O RMS também vinha de janelas retangulares sem sobreposição — o sinal
     de controle chegava serrilhado *antes* de virar geometria. Agora Hann com
     50% de sobreposição a 4x a taxa de quadro, filtro nessa taxa, média para o
     quadro no fim. Salto médio entre quadros −26%, quadros com salto >0,25 de
     92 para 40, correlação 0,940 com a curva antiga.
  6. **Piscada simétrica** (2 quadros fechando, 2 abrindo, e o 1º já saltava
     0,00→0,82). Agora 1,5 quadro fechando / 3,5 abrindo (2,09x), ease cúbico
     nas duas pontas, e **ancorada nas fronteiras de frase** do
     `batidas.sentencas` que já existia: 53% das piscadas são puxadas, distância
     mediana até a pontuação 0,78s → 0,40s, ritmo preservado (3,92s → 3,89s).
  7. **Costura vertical na caixa do olho** — achado só na ampliação 5x, depois
     de todo o resto: a deformação valia cheia até a última coluna e zero na
     seguinte (salto de 9,4/255 contra 2,8 típico = 3,4x). O maxilar já tinha
     pena de 46 px; o olho não tinha nenhuma. Agora tem, e ela cabe exatamente
     na folga lateral da caixa. Voltou a 1,00x.

  Custo: +0,44 ms/quadro (+0,9 s num render de ~50 s). Recalibração assumida da
  envoltória p20/p95 → p30/p92, porque a janela de Hann preenche os silêncios
  curtos e levanta o piso: p30/p92 devolve os picos na mosca (16% de boca aberta
  de par em par, idêntico) ao custo de +0,04 na mediana — 1,4 px numa abertura
  máxima de 34. Pico é o que lê como expressivo. 648 testes.

  **Fora de escopo, declarado:** a boca continua por amplitude, não por viseme.
  Na ampliação 5x ela é uma elipse preta com uma tira cinza de dente — o degrau
  sumiu, mas a *forma* não existe: ela fica aberta no "m" e no "b", que é um
  gatilho forte de vale da estranheza. Viseme por regra de grafema→fonema pt-BR
  sobre os tempos de palavra do TTS é determinístico e $0 (~200 linhas); ficou
  para depois por decisão do autor, que escolheu polir a amplitude primeiro.
- **Recorte e pontos do rosto, uma vez só (20/09/2026, tarde).**
  `scripts/make_presenter_cutouts.py` roda em ambiente efêmero do `uv` (`rembg`
  + `mediapipe`, >400 MB com onnxruntime e opencv — não entram no repo, mesma
  decisão do `sentence-transformers`) e grava `<id>.png` + `<id>.json` com
  olhos, subnasal, boca, queixo, pescoço e pivô. As fontes viraram
  `brand/assets/presenters/source/{iris,theo}.jpg`. **Sem o JSON não há
  apresentador** — o runner avisa no log e o vídeo sai sem ele.
- **Carrossel: distribuição de conteúdo (20/09/2026, tarde).** Referência que o
  autor mandou (kit de post de IA no Envato) virou cinco camadas de
  hierarquia: chip da marca + contador no topo, banho de acento na diagonal
  **só quando há foto**, título com a última linha (ou a última palavra) no
  acento, apoio marcado por um quadrado, rodapé com régua + arroba + ação
  (deslizar / salvar). O layout anterior era honesto e vazio.
- **Bug pago: id do pilar x objeto do pilar (20/09/2026, tarde).** O runner
  fazia `pilar = marca.pillars.get(pillar)` e depois chamava
  `presenter_for(pilar)` e `accent_for(pilar)`. As duas esperam o **id**, então
  caíam no padrão em silêncio: **nunca entrou apresentador em vídeo nenhum** e
  todo vídeo saiu no verde, mesmo nos pilares de acento ciano. Só apareceu na
  rodada real de produção, porque os dois caminhos degradam sem erro. Travado
  em `TestApresentadorNoSlot`. Moral repetida: caminho que degrada em silêncio
  precisa de teste que mede o resultado, não o código de saída.
- ~~**Apresentador na chamada** (20/09/2026, manhã)~~ **substituído.** Cutout
  Íris/Théo só nos primeiros 3,2s, à direita do cartão. Descoberto na época: o
  overlay ainda mais antigo mostrava o vídeo inteiro no canto inferior-direito
  (em cima dos botões do TikTok). `news`→Íris (papel dela já era "notícia e
  análise"). Gap que segue de pé: Íris sem voz aberta (visual dela + narração
  Francisca do edge-tts).
- ~~**Arte dos apresentadores** (20/09/2026, manhã)~~ **refeita.** O recorte de
  570px cortava o assunto nas bordas da origem: virava uma caixa de rosto com o
  peito cortado a faca. Agora o busto é cortado *acima* de onde o ombro encosta
  na borda e a última faixa some em degradê.
- ~~**Movimento procedural** (20/09/2026, manhã)~~ **substituído.** A janela
  340x640 passeando sobre o PNG media "a região difere entre frames" e passava
  — medindo movimento da janela, não da pessoa. É o mesmo erro do MP4 mudo com
  outra roupa: o teste media o sintoma errado.
- **Dicionário/mídias**: o laço Whisper→léxico está em dia (nada novo verificado
  hoje para adicionar); banco de B-roll e prefetch de cache por pilar ficam como
  próximo passo.

**M3 concluído.** Porta `LLM` com os dois adaptadores de free tier, pesquisador, roteirista
e juiz. O agente vai do tema em alta ao MP4 sozinho, com motivo gravado em cada decisão do
caminho.

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
uv run pytest && uv run ruff check .
uv run agent autopilot-status --detail   # o que o piloto fez hoje e por quê
./scripts/setup_renderer.sh --serve      # só para o `render` manual e a reserva MPT
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
juiz (8/10, com `fluxo`), slides PNG 1080x1920 (`render/carousel.py`, Pillow) e eval/métricas
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

Fatia 8 — anti-repetição + preflight (19/09/2026): curador re-checa dups
contra o ledger corrido (top-3 do dia sai distinto); `curate --top 3` +
`--cooldown-days`; `research --topic` documentado como atualização
intencional; `agent status` (resumo da memória); `agent preflight`
(parecer ligado via script_id + MP4 medido + checklist humano); outputs em
`output/YYYY-MM-DD/HHMM-tema-formato/`. Calibrações da rodada: pool
case-insensitive (UI maiúsculo quebrava); sujeito por nome próprio, mínimo 1;
`AGENT_GROQ_REASONING_EFFORT=low` destrava o writer groq (reasoning comia o
orçamento do JSON); intervalo "25 a 300" conta como um número. Pendente de
cota: long do dia (gemini 429 diário + groq só escreve curto com low).

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
- **gemini-2.5-flash tem 20 pedidos/dia no free tier.** Medido no corpo do 429
  (`quotaValue: 20`). Era o padrão do projeto e esgotava com um vídeo e meio. Cada modelo
  é um balde próprio: a rota por estágio é o que multiplica a capacidade diária.
- **Gemini 3.x no free tier devolve 503 "high demand"**, e cada 503 leva 10–20s para
  voltar. Repetir no mesmo modelo repetia o 503; o roteador tira o modelo por 10 min.
- **O arquivo `SpaceGrotesk-Bold.ttf` da marca é a fonte variável com Light como
  padrão** (tabela `fvar`, wght 300–700). Pillow e libass carregavam o Light: títulos
  finos. `render/typography.py` gera a instância estática 700 em `data/fonts/`.
- **Sem fontTools, `_cobre()` devolvia False e o slide caía na fonte bitmap de 10px.** O
  carrossel das 13h56 de 19/09 saiu ilegível e passou no aceite (que só media
  1080x1920). "Não sei se cobre" agora vira "usa a fonte da marca", e o aceite mede
  tinta no PNG (`render/carousel.py:ink_height`).
- **As músicas do MPT (`resource/songs`) vieram de vídeos do YouTube** — o README deles
  pede para apagar se houver problema de direito autoral. Canal monetizado não usa; a
  trilha é sintetizada (`render/music.py`). O Lyria do Gemini tem cota 0 no free tier.
- **"Gemini" saía "Zemini"** (regra do português: G antes de E). Sem SSML no endpoint
  gratuito do edge-tts; a correção é grafia fonética só no texto da voz
  (`voice/pronounce.py`), legenda com a grafia original. Confirmado pelo Whisper nas três
  vozes: "Zemini" antes, "Gemini" depois.
- **A voz Multilingual troca o sotaque no meio da frase** ("Discorda?" com sotaque de
  outra língua). Padrão agora é voz monolíngue pt-BR.
- **Francisca a +4% fala 2,78 palavras/s** — um roteiro longo de 150 palavras daria 54s,
  fora do Rewards. Vozes igualadas em ~2,57 (Francisca −4%, Antonio +4%) e o piso do longo
  subiu para 159 palavras (62s).
- **O MPT não aceita áudio pronto pela API** (`custom_audio_file` só vale para arquivo que
  a WebUI dele subiu para a pasta da task). Por isso pronúncia exigiu renderizador próprio.
- **Juiz que responde motivo "ok" derrubava o slot:** `CriterionScore.reason` tem
  `min_length=3`, e o `ValidationError` escapava do tratamento de `LLMError`.
- **O curto recusava dossiê de 2 fatos** com a mensagem do longo ("a faixa de 60-90s
  pede pelo menos 3"): o piso de fatos agora é por formato (curto = 1).
- **O "selected" do curador não é a escolha do slot.** Gravá-lo no ledger tirava do dia
  um tema que nunca virou vídeo; o piloto grava como `not_selected` e marca `selected`
  só o tema que virou pacote.

