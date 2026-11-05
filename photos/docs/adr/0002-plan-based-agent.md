# ADR 2: LLM produces a plan, code executes it
Context: weighted score ensembles caused false positives. Decision: LLM output is a validated boolean plan executed by deterministic set algebra; LLM failure is an explicit error. Consequence: explainable, testable, no silent guessing.
