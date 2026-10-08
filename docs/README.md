# Supporting documentation

Updated: 8 October 2026.

Start with the [current delivery ledger and live backlog](product/BUILD_STATUS.md) for completed work and pending steps. The root [vision](../Unloop_Vision.md), [architecture](../Architecture.md) and [README](../README.md) describe the current application. [BUILD_PLAN](../BUILD_PLAN.md) is preserved as the original plan; explicit later decisions in the ledger and iteration log supersede its framework, policy and provider settings.

| Folder | Active content |
|---|---|
| [agents](agents/Receipt_Extraction_Agent.md) | A1 receipt extraction contract, evidence gates and human precedence |
| [policy](policy/Synthetic_T&E_Policy.md) | Owner-reviewed synthetic policy v0.3, effective 1 October 2026; active locally, including Ground Transport and per-line rounding |
| [integrations](integrations/GMAIL.md) | Gmail connection/scan design, existing setup and future production gates |
| [product](product/PRODUCT_ITERATION_LOG.md) | Engineering hypotheses, iterations, results, decisions and [delivery workflow](product/DELIVERY_WORKFLOW.md) |
| [local development](product/LOCAL_DEVELOPMENT.md) | Cloud handoff, active local branch, service commands and remaining validation gates |
| [Arize](integrations/ARIZE.md) | Current telemetry and scored synthetic evaluations; real account ingestion pending |
| [validation](validation/ARIZE_LOCAL.md) | Latest 382-backend/20-browser CI, transport/privacy and Linux runtime evidence; dated phase records retained |

Historical evidence is labelled with its original date. It is not fresh proof of the revised application. Correction learning is out of scope; the iteration log and synthetic engineering evals do not introduce it. Superseded source versions and old diagrams live in [archive](../archive/README.md), outside the current requirement set.
