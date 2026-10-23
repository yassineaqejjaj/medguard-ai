"""How far do automatic (LLM-judge) verdicts agree with qualified human reviewers?

This is the guard against trusting the judge by default: until agreement is measured on enough human-reviewed cases,
judge scores are indicative only. Cohen's kappa corrects raw agreement for chance."""
from dataclasses import dataclass


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    if len(a) != len(b) or not a:
        return None
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in labels)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return (po - pe) / (1 - pe)


@dataclass
class Agreement:
    n: int
    observed: float | None
    kappa: float | None
    confusion: dict[str, int]  # "judge:human" -> count
    judge_false_pass: int  # judge said pass, human said not acceptable: the dangerous disagreement
    judge_false_fail: int
    sufficient: bool


MIN_SAMPLES = 30


def agreement(pairs: list[tuple[str, str]]) -> Agreement:
    """pairs: (judge, human) with each in {'pass', 'fail'}."""
    judge = [p[0] for p in pairs]
    human = [p[1] for p in pairs]
    conf: dict[str, int] = {}
    for j, h in pairs:
        conf[f"{j}:{h}"] = conf.get(f"{j}:{h}", 0) + 1
    n = len(pairs)
    return Agreement(n=n, observed=(sum(j == h for j, h in pairs) / n if n else None), kappa=cohen_kappa(judge, human),
                     confusion=conf, judge_false_pass=conf.get("pass:fail", 0), judge_false_fail=conf.get("fail:pass", 0),
                     sufficient=n >= MIN_SAMPLES)
