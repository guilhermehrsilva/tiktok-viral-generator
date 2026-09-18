# Contexto do tiktok-viral-generator

Agente que detecta assunto em alta em **tech, IA e ciência**, ancora cada afirmação numa
fonte verificável, roteiriza e produz vídeo curto em pt-BR. Meta dupla: portfólio de AI
Engineer **e** canal com receita. Restrição rígida: **custo $0/mês**.

O README cobre arquitetura e como rodar. Este arquivo guarda só o que não se deduz lendo
o código — as decisões e os fatos externos que explicam por que ele é assim.

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

## Regras ao mexer aqui

- **Não fazer fork do MPT nem vendorizar o código dele.** A fronteira é HTTP e existe de
  propósito: mantém o repo leve, permite `git pull` das melhorias deles, e faz o portfólio
  mostrar o agente em vez de um fork. O clone em `.renderer/` deve permanecer com zero
  modificações rastreadas — se algo precisar mudar lá, resolver por configuração ou
  variável de ambiente.
- **Não sugerir provedor pago** sem dizer explicitamente que quebra a restrição de $0.
- **Não afirmar que o sistema detecta o que viraliza *no TikTok*.** Não existe API pública
  para isso: o Creative Center não expõe API e a Research API é restrita a pesquisa
  acadêmica. Detectamos assunto em alta na internet e inferimos. O README diz isso; o
  código não deve fingir o contrário.
- **Nenhuma estimativa de receita** até haver número medido do próprio canal.
- **Commits sem trailer `Co-Authored-By`** (regra global do autor: repo de portfólio,
  autoria é o que está sendo avaliado).

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
- **Termos de busca vão direto para o Pexels**, sem tradução: precisam ser **em inglês** e
  em ordem cronológica casando com a narração. O modelo `Script` valida ASCII por isso.
- **Só `BeVietnamPro-Bold.ttf` cobre os acentos do pt-BR** entre as fontes do MPT; as
  outras são chinesas ou vietnamitas e renderizam tofu no lugar de "ç" e "ã".
- **Segredos só no `.env`** (git-ignored). O `setup_renderer.sh` é versionado.
- **`content_tokens` tinha piso de 3 caracteres e matava "ai" e "ia".** Os dois termos mais
  centrais do léxico do nicho sumiam antes da comparação, e o recall do portão era 2/20.
  O nicho tokeniza com piso 2; a deduplicação mantém 3.
- **O plano previa embeddings para dedup; não use.** `sentence-transformers` arrasta >1,5 GB
  de CUDA numa máquina sem GPU NVIDIA. A implementação é lexical atrás da porta
  `Deduplicator`, e trocar é um experimento mensurável, não um upgrade óbvio.
- **Calibração do nicho é travada por teste** contra os 20 títulos reais em
  `tests/fixtures/radar/hacker_news.json`. Mexer no léxico sem rodar esse teste regride o
  recall em silêncio.

## Estado

M2 concluído. O agente coleta de quatro fontes gratuitas, escolhe um tema do dia com
justificativa gravada, e produz o MP4 vertical a custo zero. Falta o miolo: pesquisa com
citação, roteiro, juiz (M3), publicação (M4) e eval (M5).
