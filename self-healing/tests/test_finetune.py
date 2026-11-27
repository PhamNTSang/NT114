import json

import pytest

from selfheal.agent import finetune, registry


class FakeModel:
    def save(self, path):                       
        open(f"{path}.zip", "wb").write(b"model")


@pytest.fixture
def tmp_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ROOT", tmp_path)
    monkeypatch.setattr(registry, "REGISTRY", tmp_path / "registry.json")
    (tmp_path / "current.zip").write_bytes(b"bc_s1")
    return tmp_path


def test_empty_registry_scores_current_model_first(tmp_registry):
    calls = []
    base = {"mttr": 8.0, "rsr": 1.0}
    score = finetune.ensure_baseline(FakeModel(), evaluate=lambda p: calls.append(p) or base,
                                     path=str(tmp_registry / "current.zip"))
    reg = json.loads((tmp_registry / "registry.json").read_text())
    assert score == base and len(calls) == 1
    assert reg["current"] == "policy_v001" and reg["versions"][0]["score"] == base


def test_worse_candidate_is_not_promoted_after_baseline(tmp_registry):
   
    finetune.ensure_baseline(FakeModel(), evaluate=lambda p: {"mttr": 8.0, "rsr": 1.0})
    worse = {"mttr": 20.0, "rsr": 0.9}
    assert not registry.not_worse(worse, registry.current_score())


def test_existing_registry_is_not_rescored(tmp_registry):
    finetune.ensure_baseline(FakeModel(), evaluate=lambda p: {"mttr": 8.0, "rsr": 1.0})
    called = []
    finetune.ensure_baseline(FakeModel(), evaluate=lambda p: called.append(p) or {})
    assert not called
