import json
import shutil
import time
from pathlib import Path

ROOT = Path("models")
REGISTRY = ROOT / "registry.json"


def _load() -> dict:
    return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {"current": None, "versions": []}


def register(model, score: dict, note: str = "") -> str:
    reg = _load()
    version = f"policy_v{len(reg['versions']) + 1:03d}"
    model.save(ROOT / version)
    reg["versions"].append({"version": version, "time": time.strftime("%Y-%m-%d %H:%M"),
                            "score": score, "note": note})
    REGISTRY.write_text(json.dumps(reg, indent=2))
    return version


def promote(version: str) -> None:
    reg = _load()
    shutil.copy(ROOT / f"{version}.zip", ROOT / "current.zip")
    reg["current"] = version
    REGISTRY.write_text(json.dumps(reg, indent=2))


def current_score() -> dict | None:
    reg = _load()
    for v in reg["versions"]:
        if v["version"] == reg["current"]:
            return v["score"]
    return None


def not_worse(new: dict, old: dict | None, tol: float = 0.05) -> bool:
    """Chap nhan neu MTTR khong tang qua 5% va RSR khong giam qua 5 diem phan tram."""
    if old is None:
        return True
    return new["mttr"] <= old["mttr"] * (1 + tol) and new["rsr"] >= old["rsr"] - tol