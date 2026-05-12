"""
Ollama model setup for Llama-3 with LoRA adapter and 4-bit quantization.

The project defaults to GPT-4o (OpenAI API), but the llm_base_url setting makes
the LLM backend fully swappable. This module generates the Ollama Modelfile needed
to serve a LoRA-fine-tuned Llama-3 model locally with the same OpenAI-compatible
chat completions endpoint.

Usage
-----
    python -m app.llm_setup          # print Modelfile + setup instructions
    python -m app.llm_setup --create  # generate Modelfile and register with Ollama

LoRA adapter training
---------------------
Fine-tune Llama-3 on system-design corpora using HuggingFace PEFT:

    pip install peft trl datasets
    python scripts/train_lora.py          # trains and saves adapter to lora_adapter/

Then point LORA_ADAPTER_PATH at the saved adapter directory in .env.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from app.config import settings

# Llama-3 chat template (Meta's official format)
_LLAMA3_TEMPLATE = textwrap.dedent("""\
    {{ if .System }}<|start_header_id|>system<|end_header_id|>

    {{ .System }}<|eot_id|>{{ end }}{{ if .Prompt }}<|start_header_id|>user<|end_header_id|>

    {{ .Prompt }}<|eot_id|>{{ end }}<|start_header_id|>assistant<|end_header_id|>

    {{ .Response }}<|eot_id|>""")

MODEL_NAME = "sdi-interviewer"


def generate_modelfile(
    base_model: str = "llama3:8b-instruct",
    adapter_path: str = "",
    quantization: str = "q4_K_M",
) -> str:
    """
    Render an Ollama Modelfile for Llama-3 with optional LoRA adapter.

    Parameters
    ----------
    base_model:   Ollama base model tag (e.g. "llama3:8b-instruct").
    adapter_path: Path to the LoRA adapter directory (GGUF or safetensors).
                  If empty, the base model is used without adaptation.
    quantization: Ollama quantization level applied at model creation time.
                  "q4_K_M" gives the best quality/speed trade-off for 8B models.
    """
    lines: list[str] = [f"FROM {base_model}"]

    if adapter_path:
        lines.append(f"ADAPTER {adapter_path}")

    lines += [
        "",
        f"PARAMETER quantize {quantization}",
        "PARAMETER temperature 0.85",
        "PARAMETER num_predict 80",       # mirrors max_tokens=80 in the app
        'PARAMETER stop "<|eot_id|>"',
        'PARAMETER stop "<|end_of_text|>"',
        "",
        f'TEMPLATE """{_LLAMA3_TEMPLATE}"""',
    ]

    return "\n".join(lines)


def print_setup_instructions() -> None:
    adapter = settings.lora_adapter_path or "./lora_adapter"
    modelfile = generate_modelfile(
        base_model="llama3:8b-instruct",
        adapter_path=settings.lora_adapter_path,
        quantization=settings.llm_quantization,
    )

    print("=" * 62)
    print("  System Design Interviewer — Llama-3 LoRA setup")
    print("=" * 62)
    print()
    print("Step 1 — pull the base model")
    print("  ollama pull llama3:8b-instruct")
    print()
    print("Step 2 — train the LoRA adapter (skip if you already have one)")
    print("  pip install peft trl datasets")
    print("  python scripts/train_lora.py --output lora_adapter/")
    print()
    print("Step 3 — save this Modelfile and create the Ollama model")
    print(f"  # Modelfile contents (also written to Modelfile.sdi):")
    print()
    for line in modelfile.splitlines():
        print(f"  {line}")
    print()
    print("  ollama create sdi-interviewer -f Modelfile.sdi")
    print()
    print("Step 4 — update .env to point at the local model")
    print("  LLM_BASE_URL=http://localhost:11434/v1")
    print("  LLM_MODEL=sdi-interviewer")
    print(f"  LLM_QUANTIZATION={settings.llm_quantization}")
    if settings.lora_adapter_path:
        print(f"  LORA_ADAPTER_PATH={settings.lora_adapter_path}")
    print()
    print("The app will call http://localhost:11434/v1/chat/completions —")
    print("the same OpenAI-compatible endpoint, no code changes required.")


def create_model(output_dir: Path = Path(".")) -> None:
    """Write Modelfile.sdi and register it with Ollama."""
    adapter = settings.lora_adapter_path
    modelfile_text = generate_modelfile(
        base_model="llama3:8b-instruct",
        adapter_path=adapter,
        quantization=settings.llm_quantization,
    )

    modelfile_path = output_dir / "Modelfile.sdi"
    modelfile_path.write_text(modelfile_text)
    print(f"Wrote {modelfile_path}")

    print(f"Registering '{MODEL_NAME}' with Ollama …")
    result = subprocess.run(
        ["ollama", "create", MODEL_NAME, "-f", str(modelfile_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("ollama create failed:")
        print(result.stderr)
        sys.exit(1)
    print(f"Model '{MODEL_NAME}' is ready.")
    print(f"Set LLM_BASE_URL=http://localhost:11434/v1 and LLM_MODEL={MODEL_NAME} in .env")


if __name__ == "__main__":
    if "--create" in sys.argv:
        create_model()
    else:
        print_setup_instructions()
