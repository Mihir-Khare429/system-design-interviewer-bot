"""
Tests for scripts/train_dpo.py — dataset loader and CLI configuration.

The training function itself (which requires torch / trl / peft) is not
exercised here — only the pure-Python helpers that are safe to run without a
GPU.  Heavy deps that train_dpo.py imports lazily (inside function bodies)
are stubbed via patch.dict(sys.modules) for the one test class that calls
load_dataset().
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Import the module under test ───────────────────────────────────────────────
# train_dpo.py lives in scripts/, which is not a package.  Add it to sys.path
# so pytest can import it.

_SCRIPTS = str(Path(__file__).parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import train_dpo  # noqa: E402


# ── load_dataset ───────────────────────────────────────────────────────────────

_SAMPLE_RECORD = {
    "prompt":   [{"role": "system", "content": "You are Alex."},
                 {"role": "user",   "content": "I'd use Redis for caching."}],
    "chosen":   [{"role": "assistant", "content": "At what QPS does Redis become your bottleneck?"}],
    "rejected": [{"role": "assistant", "content": "Redis is great! Have you considered Memcached? "
                                                   "What's your eviction policy? Also, how large is your dataset?"}],
}


def _write_jsonl(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "dataset.jsonl"
    with open(path, "w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return path


class TestLoadDataset:
    def _call(self, path: Path):
        mock_ds = MagicMock()
        with patch.dict(sys.modules, {"datasets": mock_ds}):
            train_dpo.load_dataset(path)
        return mock_ds

    def test_calls_dataset_from_list(self, tmp_path):
        path = _write_jsonl(tmp_path, [_SAMPLE_RECORD] * 3)
        mock_ds = self._call(path)
        mock_ds.Dataset.from_list.assert_called_once()

    def test_passes_correct_record_count(self, tmp_path):
        path = _write_jsonl(tmp_path, [_SAMPLE_RECORD] * 7)
        mock_ds = self._call(path)
        records_passed = mock_ds.Dataset.from_list.call_args[0][0]
        assert len(records_passed) == 7

    def test_skips_blank_lines(self, tmp_path):
        path = tmp_path / "data.jsonl"
        with open(path, "w") as fh:
            fh.write(json.dumps(_SAMPLE_RECORD) + "\n")
            fh.write("\n")
            fh.write("   \n")
            fh.write(json.dumps(_SAMPLE_RECORD) + "\n")
        mock_ds = self._call(path)
        records_passed = mock_ds.Dataset.from_list.call_args[0][0]
        assert len(records_passed) == 2

    def test_preserves_record_structure(self, tmp_path):
        path = _write_jsonl(tmp_path, [_SAMPLE_RECORD])
        mock_ds = self._call(path)
        records_passed = mock_ds.Dataset.from_list.call_args[0][0]
        assert records_passed[0] == _SAMPLE_RECORD

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text("not valid json\n")
        with pytest.raises(json.JSONDecodeError):
            with patch.dict(sys.modules, {"datasets": MagicMock()}):
                train_dpo.load_dataset(path)

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            with patch.dict(sys.modules, {"datasets": MagicMock()}):
                train_dpo.load_dataset(tmp_path / "nonexistent.jsonl")

    def test_handles_large_dataset(self, tmp_path):
        records = [_SAMPLE_RECORD] * 500
        path = _write_jsonl(tmp_path, records)
        mock_ds = self._call(path)
        records_passed = mock_ds.Dataset.from_list.call_args[0][0]
        assert len(records_passed) == 500

    def test_real_dataset_file_loads_successfully(self):
        real_path = Path(__file__).parent.parent / "data" / "dpo_dataset.jsonl"
        mock_ds = MagicMock()
        with patch.dict(sys.modules, {"datasets": mock_ds}):
            train_dpo.load_dataset(real_path)
        records_passed = mock_ds.Dataset.from_list.call_args[0][0]
        assert len(records_passed) == 25


# ── _build_parser ──────────────────────────────────────────────────────────────

class TestBuildParser:
    def _parse(self, *argv):
        return train_dpo._build_parser().parse_args(list(argv))

    def test_default_model_contains_llama(self):
        args = self._parse()
        assert "llama" in args.model.lower() or "meta" in args.model.lower()

    def test_default_epochs(self):
        assert self._parse().epochs == train_dpo.DEFAULT_EPOCHS

    def test_default_beta(self):
        assert self._parse().beta == pytest.approx(train_dpo.DEFAULT_BETA)

    def test_default_lr(self):
        assert self._parse().lr == pytest.approx(train_dpo.DEFAULT_LR)

    def test_default_lora_rank(self):
        assert self._parse().lora_rank == train_dpo.DEFAULT_LORA_R

    def test_default_lora_alpha(self):
        assert self._parse().lora_alpha == train_dpo.DEFAULT_LORA_A

    def test_default_batch_size(self):
        assert self._parse().batch_size == train_dpo.DEFAULT_BATCH

    def test_default_grad_acc(self):
        assert self._parse().grad_acc == train_dpo.DEFAULT_GRAD_ACC

    def test_default_output_is_none(self):
        assert self._parse().output is None

    def test_default_mlflow_uri(self):
        assert self._parse().mlflow_uri == "./mlruns"

    def test_default_dataset_path_ends_with_jsonl(self):
        assert str(self._parse().dataset).endswith("dpo_dataset.jsonl")

    def test_override_epochs(self):
        assert self._parse("--epochs", "5").epochs == 5

    def test_override_beta(self):
        assert self._parse("--beta", "0.05").beta == pytest.approx(0.05)

    def test_override_lr(self):
        assert self._parse("--lr", "1e-4").lr == pytest.approx(1e-4)

    def test_override_lora_rank(self):
        assert self._parse("--lora-rank", "32").lora_rank == 32

    def test_override_lora_alpha(self):
        assert self._parse("--lora-alpha", "64").lora_alpha == 64

    def test_override_batch_size(self):
        assert self._parse("--batch-size", "4").batch_size == 4

    def test_override_model(self):
        assert self._parse("--model", "mistralai/Mistral-7B").model == "mistralai/Mistral-7B"

    def test_override_mlflow_uri(self):
        assert self._parse("--mlflow-tracking-uri", "http://server:5000").mlflow_uri == "http://server:5000"

    def test_override_output(self):
        args = self._parse("--output", "/tmp/adapter")
        assert str(args.output) == "/tmp/adapter"

    def test_parser_rejects_unknown_flag(self):
        with pytest.raises(SystemExit):
            self._parse("--nonexistent-flag", "value")


# ── Constants ──────────────────────────────────────────────────────────────────

class TestConstants:
    def test_data_path_filename(self):
        assert train_dpo.DATA_PATH.name == "dpo_dataset.jsonl"

    def test_data_path_exists(self):
        assert train_dpo.DATA_PATH.exists(), "dpo_dataset.jsonl must exist on disk"

    def test_adapter_dir_name(self):
        assert train_dpo.ADAPTER_DIR.name == "lora_adapter"

    def test_eval_split_is_valid_fraction(self):
        assert 0.0 < train_dpo.EVAL_SPLIT < 1.0

    def test_mlflow_experiment_name_non_empty(self):
        assert isinstance(train_dpo.MLFLOW_EXPERIMENT, str)
        assert len(train_dpo.MLFLOW_EXPERIMENT) > 0

    def test_default_lr_is_small(self):
        # Learning rate should be at most 1e-4 to avoid destabilising pretrained weights
        assert train_dpo.DEFAULT_LR <= 1e-4

    def test_lora_alpha_is_twice_rank(self):
        # Alpha = 2 × rank is the standard default from the LoRA paper
        assert train_dpo.DEFAULT_LORA_A == 2 * train_dpo.DEFAULT_LORA_R

    def test_default_beta_is_positive(self):
        assert train_dpo.DEFAULT_BETA > 0

    def test_default_epochs_is_at_least_one(self):
        assert train_dpo.DEFAULT_EPOCHS >= 1
