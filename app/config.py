from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
