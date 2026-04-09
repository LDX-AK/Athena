from __future__ import annotations

import copy
from collections import OrderedDict
from typing import Dict, List, Tuple


class AblationMatrix:
    """Generate and apply feature-group ablation scenarios for Athena experiments."""

    DEFAULT_GROUPS = [
        "price",
        "indicators",
        "orderbook",
        "orderflow",
        "multihorizon",
        "regime",
        "rolling",
        "volatility",
        "volume",
        "time",
        "sentiment",
    ]

    def __init__(self, base_config: Dict, groups: List[str] | None = None):
        self.base_config = copy.deepcopy(base_config)
        self.groups = list(groups or self.DEFAULT_GROUPS)

    def generate_scenarios(self) -> Dict[str, List[str]]:
        scenarios: Dict[str, List[str]] = {"baseline": []}
        for group in self.groups:
            scenarios[f"no_{group}"] = [group]
        scenarios["no_rolling"] = ["rolling"]
        scenarios["no_sentiment"] = ["sentiment"]
        scenarios["no_rolling_sentiment"] = ["rolling", "sentiment"]
        scenarios["no_regime"] = ["regime"]
        scenarios["minimal"] = ["regime", "rolling", "volatility", "volume", "sentiment"]
        scenarios["core_compact"] = ["orderbook", "rolling", "time", "sentiment"]
        scenarios["price_action_core"] = ["orderbook", "orderflow", "rolling", "time", "sentiment"]
        return scenarios

    def apply_scenario(self, scenario_name: str) -> Dict:
        scenarios = self.generate_scenarios()
        if scenario_name not in scenarios:
            raise KeyError(f"Unknown ablation scenario: {scenario_name}")

        cfg = copy.deepcopy(self.base_config)
        feature_groups = cfg.setdefault("feature_groups", {})
        for group in self.groups:
            feature_groups.setdefault(group, True)
        for group in scenarios[scenario_name]:
            feature_groups[group] = False
        return cfg

    def effective_signature(self, cfg: Dict) -> Tuple[str, ...]:
        feature_groups = cfg.get("feature_groups", {})
        flags = cfg.get("flags", {})

        disabled = [group for group in self.groups if not feature_groups.get(group, True)]
        sentiment_off = not flags.get("SENTIMENT_ENABLED", True) or not flags.get("SENTIMENT_BACKTEST", True)
        if "sentiment" in self.groups and sentiment_off and "sentiment" not in disabled:
            disabled.append("sentiment")

        return tuple(disabled)

    def unique_scenarios(self, scenario_names: List[str] | None = None) -> Dict[str, List[str]]:
        scenarios = self.generate_scenarios()
        ordered_names = scenario_names or list(scenarios.keys())
        unique: Dict[str, List[str]] = OrderedDict()
        seen_signatures = set()

        for scenario_name in ordered_names:
            cfg = self.apply_scenario(scenario_name)
            signature = self.effective_signature(cfg)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            unique[scenario_name] = scenarios[scenario_name]

        return unique
