# First Mac release checks (architect snapshot at 95f67f4)

Copied verbatim from PR #8 comment 7226311601 for provenance; the register (core/docs/acceptance_register.json) maps each row to MAC-01 to MAC-20.

| Release check | Implementation | Review | Evidence or remaining work |
| --- | ---: | ---: | --- |
| Requirements and documentation | 0.5 | 0.5 | Release criteria exist. Complete the requirement-to-design-to-test mapping and reconcile open scope. |
| Design and security standards | 0.5 | 0.5 | Architecture findings are recorded. Close or explicitly dispose of the remaining privacy, recovery, and usability decisions. |
| Release stages and acceptance criteria | 0.5 | 0.5 | The first Mac release gates are known. Reconcile the stage checklist and required evidence against the product scope. |
| Build, lint, types, and supported platforms | 1 | 1 | Exact-head hosted builds and static checks passed on the covered platforms. |
| Line-by-line and function-by-function coverage | 0.5 | 0.5 | The six-file latest batch was reviewed. Release-wide file, line and function coverage is unmeasured. Record reviewed ranges and coverage of changed functions and their tests. |
| Hosted CI release checks | 0.5 | 1 | All 16 job outcomes accounted for. Fifteen passed, and Mac UI failed. |
| CI failure and artifact safety | 0.5 | 0.5 | Pass paths verified. Hosted failed-test reporting and rejected-artifact coverage remain due. |
| Mac onboarding accessibility | 0.5 | 1 | The exact-head contrast failure is confirmed. Fix it and recheck the rendered flow. |
| First-run consent and usability | 0.5 | 0.5 | Consent UI exists. Confirm owner-facing onboarding and permission behavior end to end. |
| Paired-phone revocation and tested cache wipe | 1 | 1 | Real-Core phone test verified unpairing and clearing the tested cache on reconnection. |
| Library final grant check | 1 | 1 | Late grant withdrawal is covered for the Library response. Coverage wording is tracked with the first Mac workflow. |
| Citation text permission at delivery | 1 | 1 | Regression covers withdrawal during the citation read and withholding its text. |
| Live-stream device and shutdown checks | 0.5 | 0.5 | Iterator checks are reviewed. Signed socket evidence remains due for idle revocation, scope changes and in-flight delivery. |
| Search coverage privacy and accuracy | 0.5 | 1 | Two concrete findings remain. A queued response can retain withdrawn counts, and a rebuild can substitute newer index counts for historical coverage. |
| Finance and Health final permission checks | 0.5 | 0.5 | Summaries exist. Verify permission at delivery and cover withdrawal during preparation. |
| Startup ownership and lock release | 1 | 1 | Stable lock and refusal cleanup close the startup race. A deterministic contention test would strengthen evidence. |
| Keychain provisioning and staged restore | 0.5 | 0.5 | Lock-before-provisioning reviewed. Native add-only behavior and interrupted restore still need evidence. |
| Shutdown and restart | 0.5 | 0.5 | In-process drain and lock retention are covered. Verify forced process exit and restart. |
| First Mac Documents and Mail workflow | 0.5 | 0.5 | Core and Mac components exist. Run the owner workflow with sample sources and exact citations across two document versions. |
| Result UX, cancellation, and withdrawal | 0.5 | 0.5 | Verify truthful incomplete search wording, durable Cancelled state and clearing displayed results after withdrawal. |

