# Evaluation: what a result does and does not mean

MedGuard does not certify anything. A **PASS** means a version met the criteria configured for its campaign, nothing more. It is not
a guarantee of clinical safety, not a regulatory or medical-device certification, and it does not replace medical experts.

## Two kinds of evidence

1. **Deterministic checks** (reproducible, no model): JSON format, required fields, citations present, cited sections exist in the
   reference, must-contain / must-not-contain rules, length, latency, API errors, fictional sensitive identifiers.
2. **LLM-as-a-judge** (Qwen3-8B, local): faithfulness, relevance, citation accuracy, unjustified claims, uncertainty, boundaries,
   sensitive requests. Output is validated JSON (criterion, score, status, justification, evidence, confidence, review flag).
   Inference parameters are fixed (temperature 0, seed 42, max 700 tokens), the prompt is versioned (`judge-v1`), and the model name and
   digest are stored on the run.

## Rules that keep a judge from deciding alone

- A deterministic failure fails the result whatever the judge says.
- A judge can fail a result but a judge **pass never overrides** a deterministic failure.
- Critical or high-severity results that pass on a judge verdict alone are sent to a human.
- Low judge confidence (< 0.7), judge errors (unreachable, invalid JSON after one retry), and judge-versus-deterministic
  disagreement are sent to a human.
- A critical failure is never closed automatically: it needs an explicit human decision.
- The result score is its weakest criterion, not an average. The release gate evaluates critical failures independently of the
  overall pass rate: 99 passes and one critical failure is a FAIL.

## Known limits of judges

- Judges are noisy, can be wrong with high confidence, and may share blind spots with the model under test. A local 8B model is a
  weaker judge than a large one.
- Scores depend on the prompt and on the quantisation of the model; results are reproducible with the recorded settings but not
  guaranteed bit-for-bit across hardware.
- The judge sees only the question, the reference text in the scenario, the expected behaviour and the answer. It cannot verify facts
  outside the supplied reference.
- Consistency across rephrasings is declared as a criterion but is **not yet implemented** as a multi-prompt check.
- Prompt injection inside an application's answer is mitigated (fenced data, instruction to treat it as evidence against the
  answer) but not eliminated.
- The judge has **not yet been exercised against the real Qwen3-8B model in this repository's test environment**; it is tested against a
  stub server that speaks the same protocol. Run a real campaign and review the agreement report before relying on it.

## Measuring the judge against humans

`GET /api/v1/judge/agreement` (also shown on the Human Reviews page) compares the judge's verdict on each reviewed result with the
final human decision: observed agreement, Cohen's kappa, a confusion count, and the number of **false passes** (judge pass, human
rejected), the dangerous error. Below 30 reviewed cases it says so: the numbers are then indicative only. A sensible practice is to
keep human review on a sample of every campaign even once agreement looks good, and to re-measure after any model or prompt change.

## Synthetic data

The demonstration uses a fictional assistant, a fictional corpus and invented identifiers. Do not point MedGuard at a system that
holds real patient data unless a data-protection assessment covers it.
