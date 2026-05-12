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


settings = Settings()
