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
