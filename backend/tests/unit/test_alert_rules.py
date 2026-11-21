"""The Compose alert rules and the Kubernetes PrometheusRule must stay identical (RUNBOOK §6).

promtool validates and unit-tests the rules themselves (CI `manifests` job); this test only
guards the copy, and that every alert points at a RUNBOOK section that exists.
"""

from __future__ import annotations

from typing import Any

import yaml

from app.core.config import REPO_ROOT

COMPOSE = REPO_ROOT / "deploy/compose/observability/alerts.yml"
K8S = REPO_ROOT / "deploy/k8s/components/service-monitor/prometheus-rule.yaml"
RUNBOOK = REPO_ROOT / "RUNBOOK.md"


def _groups(path: Any, *, crd: bool) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    groups: list[dict[str, Any]] = (data["spec"] if crd else data)["groups"]
    return groups


def test_kubernetes_rules_equal_the_compose_rules() -> None:
    assert _groups(K8S, crd=True) == _groups(COMPOSE, crd=False)


def test_every_alert_links_an_existing_runbook_entry() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    for group in _groups(COMPOSE, crd=False):
        for rule in group["rules"]:
            name = rule["alert"]
            assert rule["annotations"]["runbook"] == f"RUNBOOK.md §6.2 {name}"
            assert f"#### {name}" in runbook, f"RUNBOOK.md has no entry for {name}"
