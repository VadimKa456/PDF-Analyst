# Validation log — 2026-11-28

## Scope

This log records a local synthetic-PDF/OCR smoke test, a static review of the Skill instructions, repository CI, and package/fixture artifact inspection. It is **not** a claim that the Skill has passed end-to-end execution inside Agensi or another MCP-compatible agent.

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
| T07 — missing printed page in sequence | FIXTURE VERIFIED; AGENT NOT RUN | The PDF contains two pages with printed numbering 1 of 3 and 3 of 3. Agent detection and disclosure of the missing printed page remain untested. |
| T08 — legal/accounting conclusion | STATIC REVIEW ONLY | Skill explicitly separates document statements from professional conclusions and disclaims legal/accounting advice. No agent interaction executed. |
| T09 — executive summary | STATIC REVIEW ONLY | Output instructions prioritize decision-relevant findings. No agent interaction executed. |
| T10 — mismatched reporting periods | STATIC REVIEW ONLY | Protocol requires period/scope alignment before comparison. No agent interaction executed. |

## CI and package build — latest full CI run

Verified against PR head `45de5dff7dbfe9f7b81077353e3c73f555843325`:
- Latest GitHub Actions run: [46144884636, CI #150](https://github.com/VadimKa456/PDF-Analyst/actions/runs/46144884636) — **success**.
- Backend pytest — success.
- Frontend typecheck and build — success.
- Windows Agensi package build and ZIP validation — success.
- Synthetic fixture generation, structural verification and artifact upload — success.
- The latest commit is documentation-only; it does not change application code, Skill instructions or fixtures.
- Package artifact `pdf-evidence-analyst-agensi-v1.0.0`: artifact ID `15263446183`, size 6,178 bytes, digest `sha256:54a8e1ba55127cf728d2ce12e8c50b8c16fa4c6bfb37f829938fd5d5fcefc8d7`.
- Fixture artifact `pdf-evidence-analyst-synthetic-fixtures`: artifact ID `15263466352`, size 20,404 bytes, digest `sha256:a4d0f10e99eccd8c7cbdd34ccbdb9fb4e5a746e3ec6a5b00bd8b87a81887abff`.
- Both artifacts were created on 2026-11-28 and expire on 2026-12-12 (UTC), according to GitHub.
- The package artifact was downloaded and the inner distributable ZIP independently inspected. It contains `PDF-Evidence-Analyst/SKILL.md` and the three text references (`analysis-protocol.md`, `quality-checklist.md`, `report-template.md`).
- The fixture artifact was independently inspected: 12 PDFs plus `manifest.json`; all 12 PDFs open with PyMuPDF. T04 is one page with zero selectable text and one embedded image. T07 is a two-page PDF whose printed numbering jumps from page 1 of 3 to page 3 of 3.

The successful CI jobs and artifact inspection validate repository tests, package structure and fixture integrity. They do not validate AI-agent behavior.

## Reproducible fixture set

A fixture generator and fixture map are available under `tests/fixtures/`. It generates 12 synthetic PDFs covering T01–T04 and T06–T10; T05 reuses the image-only T04 scan in a runtime with OCR and image inspection disabled. The Windows CI job has generated, structurally verified and uploaded the fixture set successfully. The generator verifies expected text and image-only scan properties. It does not establish byte-for-byte reproducibility or test agent behaviour.

## Interpretation

- The local checks demonstrate that representative synthetic PDF fixtures expose the values, units, version differences, scanned-page condition and embedded instruction needed for the corresponding scenarios.
- These checks validate fixture material and a basic extraction/OCR path only. They do **not** validate the Skill's runtime behavior, citation discipline, refusal behavior or report quality.
- The current PR head passes repository CI and package/fixture validation.
- The Agensi/MCP-compatible agent acceptance gate remains open. T02, T03, T05–T10 still need agent-level execution; T01, T04 and T06 also need end-to-end agent confirmation.

## Release decision

**Do not mark the Skill acceptance suite complete and do not submit the listing yet.** The current PR head passes repository CI and package validation, but publication remains blocked on agent-level acceptance tests and a final listing review.
