from __future__ import annotations

import json
import pickle
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd


class ExperimentRegistry:
    """Persist experiment results, copied models, and metadata for strategy R&D."""

    def __init__(self, storage_path: str | Path = "data/experiments"):
        self.storage = Path(storage_path)
        self.models_dir = self.storage / "models"
        self.results_dir = self.storage / "results"
        self.logs_dir = self.results_dir / "logs"
        self.metadata_path = self.storage / "metadata.json"

        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        if not self.metadata_path.exists():
            self._save_metadata({"experiments": {}, "models": {}})

    def _load_metadata(self) -> Dict[str, Any]:
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    def _save_metadata(self, payload: Dict[str, Any]) -> None:
        self.metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def save_experiment(
        self,
        name: str,
        results: Dict[str, Any],
        config_snapshot: Dict[str, Any] | None = None,
        model: Any | None = None,
        model_path: str | Path | None = None,
    ) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name).strip("_")
        exp_id = f"{timestamp}_{safe_name}" if safe_name else timestamp

        result_payload = {
            "exp_id": exp_id,
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "config_snapshot": config_snapshot or {},
            "results": results,
        }
        result_path = self.results_dir / f"{exp_id}.json"
        result_path.write_text(json.dumps(result_payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

        stored_model_path = None
        if model_path is not None:
            src = Path(model_path)
            if src.exists():
                stored_model_path = self.models_dir / f"{exp_id}{src.suffix or '.pkl'}"
                shutil.copy2(src, stored_model_path)
        elif model is not None:
            stored_model_path = self.models_dir / f"{exp_id}.pkl"
            with stored_model_path.open("wb") as fh:
                pickle.dump(model, fh)

        metadata = self._load_metadata()
        metadata.setdefault("experiments", {})[exp_id] = {
            "name": name,
            "created_at": result_payload["created_at"],
            "result_path": str(result_path),
            "model_path": str(stored_model_path) if stored_model_path else None,
            "summary": self._extract_summary(results),
        }
        if stored_model_path:
            metadata.setdefault("models", {})[exp_id] = {
                "path": str(stored_model_path),
                "name": name,
                "created_at": result_payload["created_at"],
            }
        self._save_metadata(metadata)
        return exp_id

    def _extract_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        candidate = results
        if isinstance(results.get("holdout"), dict):
            candidate = results["holdout"].get("conservative") or next(iter(results["holdout"].values()), {})
        elif isinstance(results.get("results"), dict):
            candidate = results["results"]
        if not isinstance(candidate, dict):
            candidate = {}
        keys = ["sharpe_ratio", "profit_factor", "total_return_pct", "win_rate", "max_drawdown_pct"]
        return {key: candidate.get(key) for key in keys if key in candidate}

    def load_model(self, exp_id: str):
        metadata = self._load_metadata()
        model_entry = metadata.get("models", {}).get(exp_id) or metadata.get("experiments", {}).get(exp_id, {})
        model_path = model_entry.get("path") or model_entry.get("model_path")
        if not model_path:
            raise FileNotFoundError(f"No stored model for experiment: {exp_id}")
        with Path(model_path).open("rb") as fh:
            return pickle.load(fh)

    def list_experiments(self) -> List[Dict[str, Any]]:
        metadata = self._load_metadata()
        items = []
        for exp_id, payload in metadata.get("experiments", {}).items():
            items.append({"exp_id": exp_id, **payload})
        return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)

    def list_models(self) -> List[Dict[str, Any]]:
        metadata = self._load_metadata()
        items = []
        for exp_id, payload in metadata.get("models", {}).items():
            items.append({"exp_id": exp_id, **payload})
        return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)

    def compare_experiments(self, exp_ids: Iterable[str]) -> pd.DataFrame:
        rows = []
        metadata = self._load_metadata().get("experiments", {})
        for exp_id in exp_ids:
            entry = metadata.get(exp_id)
            if not entry:
                continue
            result_path = Path(entry["result_path"])
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            results = payload.get("results", {})
            summary = self._extract_summary(results)
            rows.append(
                {
                    "exp_id": exp_id,
                    "name": entry.get("name", ""),
                    "sharpe": summary.get("sharpe_ratio", 0.0),
                    "profit_factor": summary.get("profit_factor", 0.0),
                    "return_pct": summary.get("total_return_pct", 0.0),
                    "win_rate": summary.get("win_rate", 0.0),
                    "max_dd": summary.get("max_drawdown_pct", 0.0),
                }
            )
        return pd.DataFrame(rows)
