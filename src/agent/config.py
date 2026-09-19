"""Configuracao do agente, lida de variaveis de ambiente ou .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Fonte do MoneyPrinterTurbo que cobre acentos pt-BR. As outras que vem no repo
# dele sao chinesas (STHeiti, MicrosoftYaHei) ou vietnamitas, e renderizam
# tofu no lugar de "ç" e "ã". Verificado na cmap: 459 glifos, zero faltando.
FONT_PTBR = "BeVietnamPro-Bold.ttf"

# Vozes pt-BR gratuitas do edge-tts (sem chave, sem conta).
VOICES_PTBR = (
    "pt-BR-ThalitaMultilingualNeural",
    "pt-BR-FranciscaNeural",
    "pt-BR-AntonioNeural",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="AGENT_", extra="ignore"
    )

    # --- renderizador (MoneyPrinterTurbo rodando local) ---
    renderer_url: str = "http://127.0.0.1:8080"
    renderer_api_key: str = ""
    renderer_dir: Path = PROJECT_ROOT / ".renderer"
    # Render de 60-90s em CPU leva minutos; o timeout cobre o pior caso.
    renderer_timeout_s: float = 900.0
    renderer_poll_interval_s: float = 5.0

    # --- material visual ---
    # "pexels" em producao; "local" para provar a cadeia de producao (TTS,
    # legenda, montagem) sem depender de chave de API nem de rede.
    video_source: str = "pexels"
    local_materials: list[Path] = []

    # --- producao ---
    voice_name: str = VOICES_PTBR[0]
    font_name: str = FONT_PTBR
    font_size: int = 72
    subtitle_position: str = "two_thirds_bottom"

    # --- LLM (primeiro modelo do projeto, M3) ---
    # Sob a restricao de $0 o padrao nao e Claude: e free tier. O adaptador do
    # Claude existe para o braco pago do eval do M5 -- a comparacao medida e o
    # artefato, nao o modelo escolhido.
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    # Ids de modelo de free tier mudam e sao descontinuados sem aviso. Ficam
    # configuraveis, e `agent llm-health` confere contra o provedor em vez de
    # confiar que o padrao ainda existe.
    gemini_model: str = "gemini-2.5-flash"
    # O 2.5 Flash raciocina por padrao, e o raciocinio sai do MESMO orcamento de
    # saida e do mesmo relogio. Medido em 18/09/2026, com thinking ligado: uma
    # chamada do roteirista truncou o JSON no meio (o objeto abriu e nao fechou) e
    # outra estourou 60s de leitura. Zero desliga. Nao e economia de token: e o que
    # torna a resposta previsivel o bastante para ser validada por contrato.
    # Negativo deixa o provedor decidir (dinamico); se um dia houver evidencia de
    # que raciocinio melhora a rubrica, isso vira experimento do M5 e nao palpite.
    gemini_thinking_budget: int = 0
    groq_api_key: str = ""
    # Medido em 18/09/2026: o `llama-3.3-70b-versatile`, que era o padrao obvio,
    # saiu do catalogo do Groq (404 model_not_found) e nao ha mais nenhum Llama de
    # chat lá. Entre os que existem, este e o mais forte de uso geral -- o que
    # importa porque o Groq e o braco que o eval do M5 compara contra o pago.
    # Alternativa mais rapida e barata: "qwen/qwen3.8-27b" (0,5s contra 1,0s, e
    # menos da metade dos tokens). Os `groq/compound*` ficam FORA de proposito:
    # sao sistemas agenticos com busca web embutida, e aqui o texto da fonte quem
    # entrega e o pesquisador -- modelo que sai buscando sozinho quebra a
    # ancoragem.
    groq_model: str = "openai/gpt-oss-120b"
    # Vazio nao envia o parametro. Os `openai/gpt-oss-*` aceitam low/medium/high;
    # mandar isso para modelo que nao suporta devolve 400, e o caminho verificado
    # em 18/09/2026 foi sem o parametro.
    groq_reasoning_effort: str = ""
    # 60s nao bastavam: geracao de roteiro no free tier passa disso mesmo com o
    # raciocinio desligado, e o timeout caia no meio da chamada -- gastando a cota
    # sem receber a resposta.
    llm_timeout_s: float = 120.0

    # --- pesquisador ---
    # Cinco fontes cobrem um tema sem estourar a cota por minuto do free tier
    # (uma chamada de modelo por fonte).
    research_max_sources: int = 5
    research_max_facts_per_source: int = 4
    # Caracteres de cada pagina que vao no prompt. Pagina de noticia inteira e
    # cota gasta em menu e rodape.
    research_page_chars: int = 8000

    # --- publicador (TikTok Content Posting API, inbox, M4) ---
    # Inbox nao exige auditoria do app; o preco e que titulo, descricao e o
    # rotulo AIGC sao aplicados no app, nao pela API. Segredos so no .env.
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = ""
    tiktok_access_token: str = ""
    tiktok_refresh_token: str = ""
    # Chunk do PUT de bytes. < 5 MB sobe em 1 chunk; > 64 MB exige multiplos.
    tiktok_chunk_size: int = 10_000_000
    tiktok_timeout_s: float = 60.0

    # --- armazenamento ---
    data_dir: Path = PROJECT_ROOT / "data"
    output_dir: Path = PROJECT_ROOT / "output"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "agent.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
