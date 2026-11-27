import glob
from pathlib import Path

import pandas as pd
from scipy.stats import mannwhitneyu

ORDER = ["hybrid", "rule", "rl", "keda", "hpa", "native"]
TESTS = {"mttr_s": "less", "scr": "greater", "rc_replica_s": "less"}   


def load(pattern: str = "results/*.csv") -> pd.DataFrame:
    frames = [pd.read_csv(f) for f in glob.glob(pattern) if "summary" not in f and "significance" not in f]
    df = pd.concat(frames, ignore_index=True)
    df["tag"] = df["tag"].fillna("")
    df["variant"] = df["method"] + df["tag"]
    return df


def summary(df: pd.DataFrame) -> pd.DataFrame:
    agg = {"MTTR_mean": ("mttr_s", "mean"), "MTTR_std": ("mttr_s", "std"), "SCR": ("scr", "mean"),
           "RC": ("rc_replica_s", "mean"), "RSR": ("recovered", "mean"), "AE": ("ae", "mean"),
           "SVR": ("svr", "mean"), "N": ("scenario", "size")}
    if "ttd_s" in df:
        agg["TTD"] = ("ttd_s", "mean")
    if "rca_correct" in df:
        agg["RCA"] = ("rca_correct", "mean")
    return df.groupby(["mode", "variant"]).agg(**agg).round(3)


def per_scenario(df: pd.DataFrame, metric: str = "mttr_s") -> pd.DataFrame:
    base = df[df.tag == ""]
    return base.pivot_table(index=["mode", "scenario"], columns="method", values=metric, aggfunc="mean").round(1)


def significance(df: pd.DataFrame, ours: str = "hybrid") -> pd.DataFrame:
    rows = []
    for mode, d in df[df.tag == ""].groupby("mode"):
        a = d[d.method == ours]
        for other in [m for m in ORDER if m != ours and m in set(d.method)]:
            b = d[d.method == other]
            for metric, alt in TESTS.items():
                stat, p = mannwhitneyu(a[metric], b[metric], alternative=alt)
                rows.append({"mode": mode, "baseline": other, "metric": metric, "U": round(stat, 1),
                             "p_value": p, "significant_0.05": p < 0.05})
    return pd.DataFrame(rows)


def main() -> None:
    df = load()
    out = Path("results")
    s, sc, sig = summary(df), per_scenario(df), significance(df)
    s.to_csv(out / "summary.csv")
    sc.to_csv(out / "per_scenario_mttr.csv")
    sig.to_csv(out / "significance.csv", index=False)
    (out / "summary.tex").write_text(s.to_latex(float_format="%.2f"), encoding="utf-8")
    print(s, "\n\n", sc, "\n\n", sig, sep="")


if __name__ == "__main__":
    main()