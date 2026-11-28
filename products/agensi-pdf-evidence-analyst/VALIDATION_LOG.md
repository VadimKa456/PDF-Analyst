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

## CI and package build — current PR head

Verified against PR #3 head commit `4c68e1f1e04c55cb481dd7820bbe1b25ceeacd17`:
- GitHub Actions run: [46139553488](https://github.com/VadimKa456/PDF-Analyst/actions/runs/46139553488) — **success**.
- Backend pytest — success.
- Frontend typecheck and build — success.
- Windows Agensi package build and ZIP validation — success.
- Synthetic fixture generation, structural verification and artifact upload — success.
- Agensi package artifact: `pdf-evidence-analyst-agensi-v1.0.0`, 6,179 bytes; SHA-256 `82a87a70136efe41755a00665b7b22a2963ca73103f4df60db635eb282007d49`.
- Synthetic fixture artifact: `pdf-evidence-analyst-synthetic-fixtures`, 20,407 bytes; SHA-256 `cce28212562c1c83f671c3bedb9340439f34f340d76f617e94684284309da05b`.
- Both artifacts expire 2026-12-12 according to GitHub.

The fixture ZIP was downloaded and independently inspected: it contains 12 PDFs plus `manifest.json`; all 12 PDFs open with PyMuPDF. T04 is one page with zero selectable text and one embedded image. T07 is a two-page PDF whose printed numbering jumps from page 1 of 3 to page 3 of 3. This confirms fixture integrity, not AI-agent behavior.

## Reproducible fixture set

A deterministic generator and fixture map are available under `tests/fixtures/`. It produces 12 synthetic PDFs covering T01–T04 and T06–T10; T05 reuses the image-only T04 scan in a runtime with OCR and image inspection disabled. The Windows CI job has now generated, structurally verified and uploaded the fixture set successfully. The downloaded ZIP was independently inspected and contained all 12 PDFs and the manifest. The generator checks validate PDF contents and image-only scan properties, not agent behaviour.

## Interpretation

- The local checks demonstrate that representative synthetic PDF fixtures can expose the values, units, version differences, scanned-page condition and embedded instruction needed for the corresponding scenarios.
- These checks validate the fixture material and basic extraction/OCR path only. They do **not** validate the Skill's runtime behavior, citation discipline, refusal behavior or report quality.
- The package build, backend tests, frontend build and fixture-generation job all pass on PR head `4c68e1f`.
- The Agensi/MCP-compatible agent acceptance gate remains open. T02, T03, T05–T10 still need agent-level execution; T01, T04 and T06 also need end-to-end agent confirmation.

## Release decision

**Do not mark the Skill acceptance suite complete and do not submit the listing yet.** The current PR head passes repository CI and package validation, but publication remains blocked on agent-level acceptance tests and a final listing review.
