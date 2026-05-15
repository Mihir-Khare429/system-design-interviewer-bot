#!/usr/bin/env python3
"""
DPO fine-tuning of Llama-3 on system-design interview data.

Uses TRL's DPOTrainer with PEFT LoRA adapters so the full model weights stay
frozen and only a small set of low-rank matrices are trained.  4-bit
quantization (bitsandbytes NF4) lets an 8B model fit on a single 24 GB card.

All hyperparameters, per-step training metrics, and the final adapter are
logged to MLflow so runs are reproducible and comparable.

Usage
-----
    python scripts/train_dpo.py
    python scripts/train_dpo.py --model meta-llama/Meta-Llama-3.2-3B-Instruct
    python scripts/train_dpo.py --beta 0.05 --epochs 5 --lora-rank 32
    python scripts/train_dpo.py --mlflow-tracking-uri http://mlflow-server:5000

DPO loss (Rafailov et al. 2023)
---------------------------------
L_DPO = -E[ log σ( β · (log π_θ(y_w|x) - log π_ref(y_w|x))
                   - β · (log π_θ(y_l|x) - log π_ref(y_l|x)) ) ]

β controls the KL penalty against the reference model.  Lower β lets the
policy deviate more from the reference; higher β keeps it closer.

Dependencies (not in requirements.txt — install in a separate training env)
---------------------------------------------------------------------------
    pip install "trl>=0.9" "peft>=0.10" "transformers>=4.44" \\
                "bitsandbytes>=0.43" "mlflow>=2.12" "datasets>=2.18" \\
                accelerate
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths & defaults ──────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT  = _SCRIPT_DIR.parent
DATA_PATH   = _REPO_ROOT / "data" / "dpo_dataset.jsonl"
ADAPTER_DIR = _REPO_ROOT / "lora_adapter"

DEFAULT_MODEL     = "meta-llama/Meta-Llama-3.2-3B-Instruct"
DEFAULT_EPOCHS    = 3
DEFAULT_BETA      = 0.1      # KL penalty — lower = more deviation from reference
DEFAULT_LR        = 5e-5
DEFAULT_LORA_R    = 16
DEFAULT_LORA_A    = 32       # alpha = 2 * rank is a reliable default
DEFAULT_BATCH     = 2
DEFAULT_GRAD_ACC  = 4        # effective batch = 2 * 4 = 8
EVAL_SPLIT        = 0.15
MLFLOW_EXPERIMENT = "sdi-dpo"


# ── Dataset ───────────────────────────────────────────────────────────────────

def load_dataset(path: Path):
    """Load a JSONL file where each line is a DPO example.

    Expected schema (TRL conversational format):
      {
        "prompt":   [{"role": "system", ...}, {"role": "user", ...}],
        "chosen":   [{"role": "assistant", "content": "..."}],
        "rejected": [{"role": "assistant", "content": "..."}]
      }
    """
    from datasets import Dataset

    records = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    logger.info("Loaded %d DPO examples from %s", len(records), path)
    return Dataset.from_list(records)


# ── MLflow callback ───────────────────────────────────────────────────────────

def _make_mlflow_callback():
    import mlflow
    from transformers import TrainerCallback

    class _MlflowCallback(TrainerCallback):
        """Forward every logged metric to the active MLflow run."""
        def on_log(self, args, state, control, logs=None, **_):
            if not logs or not state.is_local_process_zero:
                return
            numeric = {k: v for k, v in logs.items() if isinstance(v, (int, float))}
            if numeric:
                mlflow.log_metrics(numeric, step=state.global_step)

    return _MlflowCallback()


# ── Training ──────────────────────────────────────────────────────────────────

def train(args: argparse.Namespace) -> None:
    # Lazy imports — avoids slow torch startup when just running --help
    import mlflow
    import torch
    from peft import LoraConfig, TaskType
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import DPOConfig, DPOTrainer

    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    with mlflow.start_run(run_name=f"dpo-{Path(args.model).name}"):
        # ── Hyperparameter logging ─────────────────────────────────────────
        mlflow.log_params({
            "model":         args.model,
            "epochs":        args.epochs,
            "beta":          args.beta,
            "lr":            args.lr,
            "lora_rank":     args.lora_rank,
            "lora_alpha":    args.lora_alpha,
            "batch_size":    args.batch_size,
            "grad_acc":      args.grad_acc,
            "dataset":       str(args.dataset),
            "loss_type":     "sigmoid",
            "quant":         "nf4_4bit",
        })

        # ── Dataset ────────────────────────────────────────────────────────
        dataset = load_dataset(args.dataset)
        split   = dataset.train_test_split(test_size=EVAL_SPLIT, seed=42)
        mlflow.log_params({"train_size": len(split["train"]), "eval_size": len(split["test"])})

        # ── Tokenizer ──────────────────────────────────────────────────────
        logger.info("Loading tokenizer: %s", args.model)
        tokenizer = AutoTokenizer.from_pretrained(args.model)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # ── Model (4-bit NF4 for memory efficiency) ────────────────────────
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,  # nested quantization saves ~0.4 GB
        )
        logger.info("Loading model %s with NF4 4-bit quantization", args.model)
        model = AutoModelForCausalLM.from_pretrained(
            args.model,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        )
        model.config.use_cache = False
        model.enable_input_require_grads()

        # ── LoRA ───────────────────────────────────────────────────────────
        # Target all linear projection matrices — covers attention and MLP.
        peft_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=args.lora_rank,
            lora_alpha=args.lora_alpha,
            lora_dropout=0.05,
            bias="none",
            target_modules=[
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
        )
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total     = sum(p.numel() for p in model.parameters())
        logger.info("LoRA: %d / %d trainable params (%.2f%%)", trainable, total, 100 * trainable / total)
        mlflow.log_params({"trainable_params": trainable, "total_params": total})

        # ── DPO training config ────────────────────────────────────────────
        output_dir = Path(args.output) if args.output else ADAPTER_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        dpo_config = DPOConfig(
            output_dir=str(output_dir),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            per_device_eval_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_acc,
            learning_rate=args.lr,
            beta=args.beta,
            loss_type="sigmoid",           # standard DPO sigmoid loss
            optim="adamw_8bit",            # 8-bit optimizer from bitsandbytes
            bf16=True,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            logging_steps=5,
            eval_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            report_to="none",              # we handle logging via callback
            remove_unused_columns=False,
            max_prompt_length=512,
            max_length=768,
        )

        trainer = DPOTrainer(
            model=model,
            ref_model=None,   # implicit reference: pre-LoRA weights (memory-efficient)
            args=dpo_config,
            train_dataset=split["train"],
            eval_dataset=split["test"],
            tokenizer=tokenizer,
            peft_config=peft_config,
            callbacks=[_make_mlflow_callback()],
        )

        logger.info("Starting DPO training (%d epochs).", args.epochs)
        train_result = trainer.train()

        # ── Save adapter ───────────────────────────────────────────────────
        trainer.save_model(str(output_dir))
        tokenizer.save_pretrained(str(output_dir))
        logger.info("Adapter saved to %s", output_dir)

        # ── Log summary metrics and artifacts ─────────────────────────────
        mlflow.log_metrics({
            "train_runtime_s":    train_result.metrics.get("train_runtime", 0),
            "train_loss_final":   train_result.metrics.get("train_loss", 0),
            "samples_per_second": train_result.metrics.get("train_samples_per_second", 0),
        })
        mlflow.log_artifacts(str(output_dir), artifact_path="adapter")
        mlflow.log_param("adapter_output_path", str(output_dir))

        run_id = mlflow.active_run().info.run_id
        logger.info(
            "Training complete. Run ID: %s\n"
            "  View: mlflow ui --backend-store-uri %s\n"
            "  Next: python scripts/eval_judge.py --run-id %s",
            run_id, args.mlflow_uri, run_id,
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="DPO fine-tune Llama-3 on system-design interview data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--model",    default=DEFAULT_MODEL,
                   help="HuggingFace model ID or local path")
    p.add_argument("--dataset",  type=Path, default=DATA_PATH,
                   help="Path to dpo_dataset.jsonl")
    p.add_argument("--output",   type=Path, default=None,
                   help="Adapter output directory (default: lora_adapter/)")
    p.add_argument("--epochs",   type=int,   default=DEFAULT_EPOCHS)
    p.add_argument("--beta",     type=float, default=DEFAULT_BETA,
                   help="DPO KL penalty β — lower values allow more deviation from reference")
    p.add_argument("--lr",       type=float, default=DEFAULT_LR,
                   help="AdamW learning rate")
    p.add_argument("--lora-rank",  type=int, default=DEFAULT_LORA_R, dest="lora_rank",
                   help="LoRA rank r")
    p.add_argument("--lora-alpha", type=int, default=DEFAULT_LORA_A, dest="lora_alpha",
                   help="LoRA scaling α (recommend 2 × rank)")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,  dest="batch_size",
                   help="Per-device train batch size")
    p.add_argument("--grad-acc",   type=int, default=DEFAULT_GRAD_ACC, dest="grad_acc",
                   help="Gradient accumulation steps")
    p.add_argument("--mlflow-tracking-uri", default="./mlruns", dest="mlflow_uri",
                   help="MLflow tracking server URI")
    return p


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )
    _args = _build_parser().parse_args()

    import mlflow
    mlflow.set_tracking_uri(_args.mlflow_uri)

    train(_args)
