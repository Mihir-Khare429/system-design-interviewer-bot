from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")

    recall_api_key: str = "your_recall_key_here"
    openai_api_key: str = "your_openai_key_here"
    port: int = 8000
    webhook_base_url: str = "http://localhost:8000"
    bot_persona_name: str = "System Design Interviewer"

    # LLM backend (defaults to OpenAI; swap to Ollama for free local inference)
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    llm_vision_model: str = "gpt-4o"

    # TTS backend (defaults to OpenAI; swap to Kokoro for free local TTS)
    tts_base_url: str = "https://api.openai.com/v1"
    tts_voice: str = "onyx"

    # Streaming: deliver tokens sentence-by-sentence → TTS starts before generation ends
    llm_streaming: bool = True

    # Ollama / local-model settings (used when llm_base_url points to Ollama)
    llm_quantization: str = "q4_K_M"   # 4-bit quantization for Llama-3 LoRA adapter
    lora_adapter_path: str = ""         # path to LoRA adapter file relative to Ollama

    # ----- SaaS additions -----
    database_url: str = "sqlite+aiosqlite:///./sdi.db"
    jwt_secret: str = "dev-secret-change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 7  # 7 days

    # Plans / quota
    free_monthly_interviews: int = 3
    pro_monthly_interviews: int = 1000  # effectively unlimited

    # Stripe (test mode keys; empty string disables real billing)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_pro: str = ""
    stripe_success_url: str = "http://localhost:3000/dashboard?upgraded=1"
    stripe_cancel_url: str = "http://localhost:3000/pricing"

    # Pricing for cost tracking ($ per 1K tokens). Defaults match gpt-4o list price.
    price_input_per_1k: float = 0.0025
    price_output_per_1k: float = 0.01
    price_whisper_per_minute: float = 0.006
    price_tts_per_1k_chars: float = 0.015

    # Frontend origin allowed for CORS
    frontend_origin: str = "http://localhost:3000"


settings = Settings()
