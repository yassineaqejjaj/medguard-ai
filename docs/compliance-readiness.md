# Compliance readiness (not compliance)

MedGuard is **not** certified and is **not** presented as compliant with the GDPR, French HDS hosting requirements, or the EU AI Act.
This page lists technical measures that make a later assessment easier, and what remains for the operator.

| Topic | Technical measure present | What the operator still has to do |
|---|---|---|
| Data minimisation (GDPR art. 5) | Synthetic data by default; no patient fields in the data model; per-organisation retention with a purge of stored responses and reports | Decide a retention period; verify that connected applications receive no real personal data |
| Purpose limitation | Each application records its purpose and usage context | Keep these fields accurate |
| Security of processing (art. 32) | Encryption of stored credentials, tenant isolation (RLS), RBAC, TLS at the proxy, audit log, rate limiting, dependency and licence checks ([security.md](security.md)) | Production hardening checklist in [deployment.md](deployment.md); penetration test; key management |
| Accountability, audit | Hash-chained, insert-only audit log of who did what; reports embed the relevant entries and the chain head | Retain and review logs; export the chain head externally |
| Data subject rights | No personal data of patients is held by design. User identities (email, display name) come from the IdP | Procedure for access/erasure of staff accounts in Keycloak and `users` rows |
| Hosting (HDS) | Everything is self-hostable; no third-party SaaS in the data path | HDS applies to a hosting provider of health data: choose a certified host if real health data is ever processed |
| Human oversight (AI Act, art. 14 spirit) | Critical failures need an explicit human decision; release is signed by a named authorised person; gates cannot be overridden into a release on FAIL | Define who is authorised and their qualifications |
| Record-keeping and traceability (AI Act, art. 12 and 19 spirit) | Every report links run, scenario versions, settings, model and prompt versions, reviewer identities and decisions, with integrity hashes | Retain reports as long as your obligations require |
| Accuracy, robustness testing (art. 15 spirit) | Versioned scenarios, deterministic and judge evaluations, regression comparison, release gate | Build scenario suites that reflect your real intended use; validate them with medical experts |
| Transparency | Judge model, digest, prompt version and inference parameters are recorded per run; limits documented in [evaluation-limits.md](evaluation-limits.md) | Disclose to users how results are produced |

Whether a given AI application is high-risk under the AI Act, or a medical device under MDR, is a legal and clinical determination
outside this tool.
