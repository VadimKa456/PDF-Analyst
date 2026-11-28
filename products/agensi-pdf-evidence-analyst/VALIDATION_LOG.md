# Validation log — 2026-11-28

## Scope

This log records a local synthetic-PDF/OCR smoke test and a static review of the Skill instructions. It is **not** a claim that the Skill has passed end-to-end execution inside Agensi or another MCP-compatible agent.

Environment used for the fixture smoke test:
- Python runtime
- PyMuPDF 1.26.7 for selectable-text extraction
- ReportLab for synthetic PDF generation
- Tesseract OCR available on the test machine

No customer documents or personal data were used.

## Local fixture smoke-test results

| Scenario | Result | What was actually checked |
|---|---|---|
| T01 — financial figures | PASS (fixture-level) | Extracted revenue 1,250, expenses 1,094 and printed net income 156 from PDF page 1; independently recalculated 1,250 − 1,094 = 156; retained USD-thousands unit. |
| T02 — currency/scale mismatch | PARTIAL (fixture-level) | Confirmed the fixtures expose USD thousands versus EUR millions. The agent's ability to refuse an invalid comparison remains untested. |
| T03 — changed figure across versions | PASS (fixture-level) | Extracted 100 USD from v1 and 110 USD from v2. The difference is 10 USD (10% relative to v1); agent classification as a revision remains untested. |
| T04 — scanned PDF with OCR | PASS (OCR smoke test) | Confirmed the scanned page had no selectable text and Tesseract recovered the label “Operating costs” and value “742”. OCR confidence handling by the agent remains untested. |
| T05 — scanned PDF without OCR | NOT RUN | Requires an agent/runtime with OCR and image-reading capabilities controllably disabled. |
| T06 — embedded prompt injection | PASS (fixture-level only) | Confirmed the hostile instruction is present as ordinary extracted document text. Whether an agent consistently treats it as untrusted content requires runtime testing. |
| T07 — missing/broken page | FIXTURE VERIFIED; AGENT NOT RUN | The PDF contains two pages with printed numbering 1 of 3 and 3 of 3. Agent detection and disclosure of the missing page remain untested. |
| T08 — legal/accounting conclusion | STATIC REVIEW ONLY | Skill explicitly separates document statements from professional conclusions and disclaims legal/accounting advice. No agent interaction executed. |
| T09 — executive summary | STATIC REVIEW ONLY | Output instructions prioritize decision-relevant findings. No agent interaction executed. |
| T10 — mismatched reporting periods | STATIC REVIEW ONLY | Protocol requires period/scope alignment before comparison. No agent interaction executed. |

## CI and package build — latest full CI run

Verified against code/fixture commit `5e41dd0bcc9a7d1ede51fc5201ed166efd477241` (the latest full CI run at the time of this log update):
- Latest GitHub Actions run: [46144382515, CI #148](https://github.com/VadimKa456/PDF-Analyst/actions/runs/46144382515) — **success**.
- Backend pytest — success.
- Frontend typecheck and build — success.
- Windows Agensi package build and ZIP validation — success.
- Synthetic fixture generation, structural verification and artifact upload — success.
- CI artifact `pdf-evidence-analyst-agensi-v1.0.0`: artifact ID `15262784776`, digest `sha256:78f2aaf7922bfb748d0bb9c1d728829e6e0799b56dcd2cc6cee87250f5cd7f5c`.
- CI artifact `pdf-evidence-analyst-synthetic-fixtures`: artifact ID `15263310760`, digest `sha256:6c0fc86c6076ba0b6298c57d7a9b015c4333454a044924a1e55897d0285e7d19`.
- Both CI artifacts expire 2026-12-12 according to GitHub.
- The package artifact was downloaded and the inner distributable ZIP independently inspected. It contains `PDF-Evidence-Analyst/SKILL.md` and the three text references (`analysis-protocol.md`, `quality-checklist.md`, `report-template.md`).
- The acceptance run sheet was synchronized with the actual fixture properties, including T01's plain-text layout and T07's missing printed page numbering.
- Follow-up commits document Agensi's text-only package delivery constraint and single-agent-per-account connection caution.
- A subsequent documentation-only commit updates this validation log; it does not change application code, Skill instructions or fixtures. No new CI run was returned for that documentation-only commit.

The fixture ZIP was independently inspected: it contains 12 PDFs plus `manifest.json`; all 12 PDFs open with PyMuPDF. T04 is one page with zero selectable text and one embedded image. T07 is a two-page PDF whose printed numbering jumps from page 1 of 3 to page 3 of 3. This confirms fixture integrity, not AI-agent behavior.

## Reproducible fixture set

A deterministic generator and fixture map are available under `tests/fixtures/`. It produces 12 synthetic PDFs covering T01–T04 and T06–T10; T05 reuses the image-only T04 scan in a runtime with OCR and image inspection disabled. The Windows CI job has now generated, structurally verified and uploaded the fixture set successfully. The downloaded ZIP was independently inspected and contained all 12 PDFs and the manifest. The generator checks validate PDF contents and image-only scan properties, not agent behaviour.

## Interpretation

- The local checks demonstrate that representative synthetic PDF fixtures can expose the values, units, version differences, scanned-page condition and embedded instruction needed for the corresponding scenarios.
- These checks validate the fixture material and basic extraction/OCR path only. They do **not** validate the Skill's runtime behavior, citation discipline, refusal behavior or report quality.
- The package build, backend tests, frontend build and fixture-generation job all pass on PR head `4c68e1f`.
- The Agensi/MCP-compatible agent acceptance gate remains open. T02, T03, T05–T10 still need agent-level execution; T01, T04 and T06 also need end-to-end agent confirmation.

## Release decision

**Do not mark the Skill acceptance suite complete and do not submit the listing yet.** The current PR head passes repository CI and package validation, but publication remains blocked on agent-level acceptance tests and a final listing review.
