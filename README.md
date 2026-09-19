# tiktok-viral-generator

Agente que detecta assunto em alta em **tech, IA e ciência**, ancora cada afirmação numa
fonte verificável, roteiriza e produz vídeo curto em pt-BR.

O recorte é deliberado. Já existe open source maduro que transforma um tema em MP4 —
o [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) (MIT) faz isso muito
bem. O que não existe é a metade de cima: **descobrir o que vale a pena falar, e provar
que o que se fala é verdade.** É essa metade que este repositório constrói.

> Estado atual: **M4 (código pronto, sem post real)** — o agente vai do tema em alta
> ao MP4 sozinho e sobe para a inbox do TikTok via Content Posting API:
> curador escolhe, pesquisador ancora cada fato numa URL, roteirista escreve na
> faixa de monetização, juiz aplica a rubrica de 7 critérios e devolve para
> revisão, renderizador produz, publicador entrega na inbox. Falta o primeiro
> post real no app (exige app registrado + OAuth). Veja [Marcos](#marcos).

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
                  memória (SQLite: sinais, temas, dossiês)
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
uv run pytest          # 322 testes, sem rede e sem chave de LLM
uv run ruff check .
```

### O ciclo inteiro

```bash
uv run agent curate                            # escolhe o tema do dia
uv run agent research                          # 3-5 fontes, cada fato com URL
uv run agent produce --out output/roteiro.json # escreve, julga, revisa
uv run agent render --script output/roteiro.json
```

Do `research` em diante é preciso uma chave de LLM gratuita no `.env`
(`AGENT_GEMINI_API_KEY` ou `AGENT_GROQ_API_KEY`); `uv run agent llm-health`
confirma que ela responde.

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

## O curador

```bash
uv run agent curate
```

Três portões em ordem, do mais barato para o mais caro, e só depois o score:

1. **Política** — bloqueia antes de qualquer cálculo. Tema vetado não pode ganhar no
   ranking por estar subindo rápido. Guarda saúde/medicamento, política partidária,
   tragédia com vítima e menores.
2. **Nicho** — portão, não tempero. Termo fora de tech/IA/ciência é descartado mesmo com
   velocidade altíssima.
3. **Duplicata** — só entre os que sobraram, porque comparar com o ledger custa.

O score só é calculado entre os sobreviventes. Velocidade e volume entram como
**percentil dentro da própria fonte**: ponto do Hacker News e pageview da Wikipedia não
compartilham escala, e somar os números crus faria a Wikipedia vencer sempre por ter
unidade maior — não por ter assunto melhor.

**Toda decisão é gravada com motivo, inclusive as rejeitadas.** Sem isso só se sabe o que
foi escolhido, nunca o que foi perdido, e calibrar o score vira chute.

### Deduplicação: lexical, atrás de uma porta

O plano previa embeddings locais via `sentence-transformers`. Medido em 18/09/2026: aquele
pacote arrasta o torch com a stack CUDA inteira — cudnn 527 MB, nccl 206 MB, cufft 204 MB,
cusolver 191 MB — mais de 1,5 GB de bibliotecas NVIDIA numa máquina **sem GPU NVIDIA**. A
variante CPU-only não terminou de instalar em 7 minutos.

O que a deduplicação precisa pegar aqui é majoritariamente lexical: a mesma matéria por
fontes diferentes, ou o mesmo lançamento reformulado. Jaccard sobre tokens de conteúdo
resolve, de forma determinística e testável, sem download e sem modelo.

O que ele **não** pega é paráfrase sem palavra em comum. Essa é a lacuna que justificaria
embeddings — e, por estar atrás da porta `Deduplicator`, trocar a técnica e medir contra a
mesma base de temas é barato. É o tipo de evidência que o M5 produz.

## O pesquisador

```bash
uv run agent research                 # tema vem do curador
uv run agent research --topic "..." --url https://fonte/materia
```

É onde entra o primeiro LLM do projeto. O estágio recebe um tema e devolve um
dossiê: de 3 a 5 fontes lidas, e cada `Fact` com afirmação, URL, nome do veículo
e o **trecho literal** que a sustenta.

A decisão que sustenta o resto: **uma chamada de modelo por fonte, e a URL é
estampada por nós.** O modelo recebe o texto de uma página e devolve afirmações
sobre aquela página; de onde veio o texto é informação que já temos. Pedir
`source_url` ao modelo convidaria o erro mais caro possível aqui — fato real com
fonte trocada, que parece ancorado, passa no juiz e só aparece quando alguém
clica no link. Com isso, "não existe `Fact` sem URL verificável" deixa de
depender da honestidade do modelo e passa a ser estrutural.

### Descoberta de fontes sem buscador pago

Não existe API de busca web gratuita que sirva: Google e Bing cobram, e raspar
SERP quebra em uma semana. O que existe de graça, e já está na stack:

| Estratégia | O que dá | Custo |
|---|---|---|
| `news_item` do Google Trends RSS | título, veículo e URL, já associados ao tema | $0, vem na coleta do radar |
| API do Algolia (`/items/{id}`) | o artigo por trás da discussão do Hacker News | $0, sem chave |
| GDELT DOC 2.0 em `artlist` | quem mais escreveu sobre o tema | $0, sem chave, instável |

Nenhuma cobre todo tema — item do HN não tem matéria associada, tema do Trends
não passa pelo Algolia, GDELT devolve 429 com frequência — então as três rodam e
o relatório diz quais falharam. Há teto de 2 páginas por domínio: cinco páginas
do mesmo site não são cinco fontes, e o juiz não tem como saber a diferença
olhando só o dossiê.

### Dois portões antes de um fato entrar

Os dois são determinísticos e não gastam token. Existem porque o modelo pode
parecer certo estando errado, e porque pedir a ele que se audite não é
verificação.

1. **O trecho citado tem que existir na página.** O modelo devolve, junto de cada
   afirmação, a passagem literal que a sustenta. Conferir passagem é `in` numa
   string — barato e impossível de enganar. Paráfrase onde devia haver cópia
   reprova: não dá para saber se a afirmação é verdadeira, e "não dá para saber"
   reprova.
2. **Todo número da afirmação tem que estar na fonte.** Número é o que o roteiro
   usa para convencer, e é o que um modelo inventa com mais confiança.

O portão numérico compara **dígitos**, não valores: pt-BR escreve `5,9` e inglês
escreve `5.9` para a mesma coisa, e `1.500` é mil e quinhentos em português e um
e meio em inglês. Casar só os dígitos resolve os dois sentidos sem criar falso
negativo por vírgula.

O caminho óbvio — medir sobreposição de vocabulário entre a afirmação e a página
— está errado aqui, e por um motivo que só aparece quando se olha as fontes
reais: elas são quase todas em inglês e a afirmação sai em pt-BR. "Retém 98,2% do
desempenho" e *"retains 98.2% of performance"* não compartilham uma palavra. O
portão reprovaria justamente os fatos bem traduzidos. **Número sobrevive à
tradução; palavra não.**

**Todo fato derrubado é gravado com o motivo**, junto do dossiê, e a CLI imprime
os descartes antes do resultado. É o que diz se o portão está calibrado ou
estrangulando — sem isso, um portão apertado demais só apareceria como "o
modelo está ruim hoje".

### Custo medido, não estimado

`Completion` carrega tokens de entrada, de saída e latência, e a tabela
`dossiers` guarda isso em coluna própria. O eval do M5 compara free tier contra
modelo pago na mesma rubrica, e essa comparação só vale se o custo for medido na
hora — provedor não devolve consumo retroativo. No Gemini Flash, os tokens de
raciocínio interno entram na conta: saem do mesmo orçamento, e ignorá-los
subestimaria o consumo.

### Os dois provedores desde já

| Provedor | Formato estruturado | Papel |
|---|---|---|
| Gemini Flash (AI Studio) | `responseSchema` nativo | padrão; pt-BR melhor |
| Groq (endpoint compatível com OpenAI) | `json_object` + schema no prompt | segundo braço, muito mais rápido |

Porta com um único adaptador não é porta, é indireção — por isso os dois entram
juntos, com teste de conformidade. As chaves são gratuitas e ficam só no `.env`:

```bash
AGENT_GEMINI_API_KEY=...   # aistudio.google.com/apikey
AGENT_GROQ_API_KEY=...     # console.groq.com/keys

uv run agent llm-health    # confere qual id de modelo ainda responde, e a que custo
```

`llm-health` existe porque id de modelo de free tier é descontinuado sem aviso, e
o erro apareceria no meio de uma pesquisa, depois de gastar tempo lendo páginas.
Ele gasta uma chamada mínima e reporta quem respondeu, em quanto tempo e por
quantos tokens — verifica o artefato, não a configuração.

## O roteirista

```bash
uv run agent write --out output/roteiro.json
uv run agent render --script output/roteiro.json     # fecha o ciclo
```

O estágio lê o último dossiê gravado e devolve um `Script` — o mesmo contrato que
o M0 já renderiza, sem adaptação no meio.

A separação que organiza o estágio: **o roteirista corrige o que é mecânico, o
juiz julga o que é julgamento.** Contar palavra, conferir se o termo de busca
está em ASCII, conferir se o índice de fato existe no dossiê, conferir se um
número em dígito da narração está em algum fato — nada disso precisa de rubrica,
e gastar uma rodada de revisão do juiz com erro de contagem é queimar cota de
free tier. Então o roteirista tem seu próprio laço: até três tentativas, com o
**defeito medido devolvido ao modelo em texto** ("a narração tem 90 palavras e
precisa ter entre 150 e 225").

Só chega ao juiz um roteiro que já passa em tudo que é verificável.

### O modelo aponta o fato, não o reescreve

O roteiro não recebe os fatos como texto para reaproveitar: recebe o dossiê
**indexado**, e devolve `used_facts: [0, 2]`. Os `Fact` que vão para o `Script`
são os objetos do dossiê, com a URL que o pesquisador estampou. Se o modelo
pudesse redigir o fato, a afirmação do roteiro deixaria de ser rastreável ao que
a fonte diz — que é todo o motivo de o dossiê existir.

### A faixa de duração é requisito, não gosto

Vídeo abaixo de 60s não é elegível ao Creator Rewards. A faixa é estimada aqui
pelo ritmo de fala (2,5 palavras/s → 150 a 225 palavras) e **medida de verdade**
só depois do TTS, pelo `ffprobe`, no aceite do renderizador. A estimativa serve
para não gastar um render inteiro para descobrir que o texto era curto; a medida
é a que manda.

Um limite conhecido e assumido: o portão de números só vê o que está escrito em
**dígito**. A narração boa escreve número por extenso para o TTS ("cinco vírgula
nove gigabytes"), e conferir isso exigiria converter numeral em português de
volta para dígito. Quem cobre esse caso é o critério 2 da rubrica do juiz, com o
dossiê em mãos.

### Todas as tentativas ficam gravadas

Inclusive quando a primeira já passa. Se toda execução gasta duas rodadas no
mesmo defeito, o problema está na instrução e não no modelo — e isso só aparece
se o intervalo for registrado em vez de descartado no sucesso. A tabela
`scripts` guarda o número de tentativas, as violações de cada uma, o custo em
tokens e o `dossier_id` de origem.

Esse vínculo com o dossiê é o que vai permitir, no M5, ligar retenção ao material
que gerou o roteiro. Sem ele, "este vídeo foi melhor" nunca vira "esta fonte
rende melhor".

## O juiz

```bash
uv run agent judge --script fixtures/roteiro_sem_fonte.json   # reprova sem gastar nada
uv run agent produce --out output/roteiro.json                # escreve, julga, revisa
```

Rubrica de 7 critérios, 0–2 cada, corte em 11/14:

| # | Critério | De onde sai a nota |
|---|---|---|
| 1 | hook abre lacuna nos primeiros segundos | julgada |
| 2 | toda afirmação tem fonte no dossiê | **medida** (dígitos) + julgada |
| 3 | duração falada entre 60 e 90s | **medida** |
| 4 | ponto de vista próprio, não resumo de notícia | julgada |
| 5 | nenhum termo da lista de política | **medida** |
| 6 | pt-BR falado, frases curtas | julgada |
| 7 | fechamento com CTA que não seja "siga para mais" | julgada |

### O que não se pergunta ao modelo

Duração é contagem de palavra. Perguntar a um LLM quantos segundos o texto leva
falado é trocar uma medida por um chute. Política já tem filtro escrito contra o
radar real, e o juiz **reusa o mesmo filtro** que barrou o tema — duas listas
divergiriam com o tempo, e o roteiro passaria a ser julgado por uma regra
diferente da que decidiu o assunto.

Fonte tem as duas metades: a conta de dígitos é nossa, a leitura é do modelo.
Número inventado é pego sem custo; afirmação que vai além do dossiê precisa de
um leitor.

### Medir é barato, julgar custa cota

A ordem é a mesma do curador: quando a medida já reprova num critério de
requisito, **o modelo não é chamado**. Os critérios de leitura ficam marcados
como *não avaliados* — zero ali significa "não sei", não "ruim", e por isso não
voltam ao roteirista como correção.

Isso tem um efeito prático bom: a fixture adversarial do M3 é reprovada **sem
nenhuma chave de API e sem gastar um token**, o que dá para conferir agora:

```
$ uv run agent judge --script fixtures/roteiro_sem_fonte.json
modelo    : nao consultado (reprovou na medida)
  [2/2] medido   duracao        210 palavras, ~84s estimados
  [2/2] medido   politica       nenhum termo da lista de politica
  [0/2] medido   fonte          numero citado sem respaldo no dossie: 12, 40
  [0/2] pulado   hook           nao avaliado: o roteiro reprovou antes em fonte
  ...
REPROVADO: 4/14 (corte 11)
  veto em fonte: e requisito, nao qualidade — nota nos outros criterios nao compensa
custo     : 0 tokens
```

A fixture é o roteiro de referência do M0 com **uma única** afirmação enxertada
("12 mil GPUs e 40 milhões de dólares", números que não existem em nenhum fato).
Todo o resto é idêntico, de propósito: assim não há como ela ser reprovada por
escrita ruim, duração ou política. O teste disso ainda dá ao juiz um parecer de
nota máxima nos cinco critérios julgados — o cenário mais favorável possível ao
roteiro — e ele reprova mesmo assim.

### A soma não decide sozinha

Aprovar exige três coisas: **11/14**, **nenhum critério zerado** e **nenhum veto**.

A soma sozinha permite compensação errada. Um roteiro que é puro resumo de
notícia (0 em ponto de vista) chegaria a 12 de 14 com o resto perfeito e
passaria — sendo exatamente o "AI slop" que o Creator Rewards exclui. E fonte,
duração e política são **veto**: falham em requisito, não em qualidade, e nota
alta nos outros critérios não compra aprovação.

### Revisão: no máximo duas

O laço `roteirista → juiz → roteirista` mora fora dos dois estágios
(`agent/pipeline.py`). Se o roteirista soubesse do juiz, passaria a escrever para
a rubrica e o parecer deixaria de ser independente; se o juiz soubesse do
roteirista, julgaria a tentativa e não o texto.

O teto de duas revisões não é arbitrário: a partir da terceira, o que costuma
acontecer não é o roteiro melhorar — é o modelo começar a trocar de assunto para
agradar a rubrica. Melhor reprovar com o motivo gravado e escolher outro tema.

As notas de revisão vão ordenadas por custo: **veto primeiro**. Não adianta
melhorar o hook de um roteiro que cita número sem fonte.

## Marcos

| | Marco | Estado |
|---|---|---|
| M0 | Porta Renderer + aceite medido do MP4 | **concluído** |
| M1 | Radar (HN, Trends, Wikipedia, GDELT) | **concluído** |
| M2 | Curador: score, filtro de política, dedup por memória | **concluído** |
| M3 | Pesquisador + roteirista + juiz com rubrica | **concluído** |
| M4 | Publicador (TikTok, inbox, rótulo AIGC) | **código pronto, sem rede real** — falta app registrado + 1º post no app |
| M5 | Eval: free tier x free tier na mesma rubrica + métricas do post | **em andamento** — `agent eval` (offline) e `agent metrics-record` prontos; 1ª rodada real abaixo |

## Eval (M5) — primeiros números

Primeira rodada real em 19/09/2026, tema único (Bonsai 2 27B), `uv run agent eval`.
O braço pago (Claude) está fora de escopo — sem API paga, não há número a
publicar. A comparação é free tier x free tier:

| | gemini (`gemini-2.5-flash`) | groq (`openai/gpt-oss-120b`) |
|---|---|---|
| pesquisador | 4 fatos, 0 descartes, 2525 in / 489 out | 4 fatos, 0 descartes, 2537 in / 684 out |
| roteirista | OK, 180 palavras (~72s), 1 tentativa | **falha 2x**: `400 json_validate_failed` (não gerou JSON válido antes do teto de tokens) |
| juiz (mesmo roteiro) | 12/14 APROVADO | **14/14 APROVADO** — 2 pontos mais generoso (hook 2x1, ponto de vista 2x1) |

`produce` gemini ponta a ponta: APROVADO 12/14, 186 palavras, 2038 in / 648 out.
Métricas do post (`agent metrics-record`) são lidas no app à mão: a inbox não
expõe endpoint de métricas e a Research API é restrita a pesquisa acadêmica.

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
- **Os adaptadores de LLM foram exercitados contra a API real em 19/09/2026.**
  `llm-health` responde nos dois free tiers; pesquisador, roteirista (gemini) e
  juiz (gemini e groq) rodaram de verdade no tema Bonsai 2. O roteirista groq
  (`gpt-oss-120b`) falha em `json_validate_failed` — registrado no Eval acima,
  não aqui.
- **O portão de trecho reprova paráfrase.** Quando o modelo reescreve onde devia
  copiar, o fato cai mesmo que seja verdadeiro. O erro é assimétrico de propósito:
  dossiê curto com motivo gravado é calibrável, dossiê cheio de fato frouxo não.
  Os descartes ficam no banco justamente para essa calibração ter dado.
- **O portão numérico não confere unidade nem contexto.** "5,9 GB" casa com uma
  página que diz "5,9 milhões de downloads". A alternativa seria pedir ao próprio
  modelo que se auditasse, o que não é verificação.
- **O portão de números do roteirista só vê dígito.** Número inventado escrito
  por extenso ("nove vezes menor") escapa dele; é o critério 2 da rubrica do juiz
  que cobre esse caso.
- **Não há busca web gratuita.** A descoberta de fontes depende do que o Trends
  RSS já associou, do link por trás do item do HN e do GDELT — que devolve 429 com
  frequência. Tema fora dessas três trilhas pode não render dossiê nenhum.
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
