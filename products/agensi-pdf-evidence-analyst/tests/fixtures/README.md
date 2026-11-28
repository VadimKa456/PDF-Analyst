# Synthetic PDF fixtures for agent acceptance tests

These documents are fictional test inputs. They contain no customer, personal, or confidential data.

## Generate and verify

From the repository root:

\`\`\`powershell
python products/agensi-pdf-evidence-analyst/tests/fixtures/generate_fixtures.py
\`\`\`

The generator writes PDFs and \`manifest.json\` into a local \`generated/\` directory. The PDFs are generated at test time and are not committed as opaque binaries.

To verify an existing generated set:

\`\`\`powershell
python products/agensi-pdf-evidence-analyst/tests/fixtures/generate_fixtures.py --verify-only
\`\`\`

Dependencies are already in the repository's root \`requirements.txt\`: ReportLab, Pillow and PyMuPDF.

## Fixture map

| Scenario | Files | Fixture fact |
|---|---|---|
| T01 | \`T01_financial_statement.pdf\` | USD thousands; revenue 1,250; expenses 1,094; printed net income 156 |
| T02 | \`T02_report_A_USD_thousands.pdf\`, \`T02_report_B_EUR_millions.pdf\` | Same metric, incompatible currencies and scales; no FX rate |
| T03 | \`T03_version_v1.pdf\`, \`T03_version_v2.pdf\` | Marketing expense revised from USD 100 to USD 110 |
| T04 | \`T04_scanned_ocr.pdf\` | Image-only scan; OCR target “Operating costs” / “742” |
| T05 | \`T04_scanned_ocr.pdf\` | Reuse T04 with OCR and image inspection unavailable in the agent runtime |
| T06 | \`T06_embedded_instruction.pdf\` | Ordinary report text includes a hostile instruction as untrusted document content |
| T07 | \`T07_missing_page_sequence.pdf\` | Printed page sequence jumps from 1 of 3 to 3 of 3 |
| T08 | \`T08_accounting_note.pdf\` | Fictional provisional accrual; no framework or legal finding |
| T09 | \`T09_executive_summary_source.pdf\` | Three decision-relevant findings plus one minor formatting issue |
| T10 | \`T10_entity_A_calendar_year.pdf\`, \`T10_entity_B_nine_months.pdf\` | 12-month vs 9-month reporting periods |

## Important limitations

- These fixtures validate test inputs and basic PDF properties, not the behaviour of an AI agent.
- T05 is only meaningful when the target runtime's OCR and page-image tools are actually unavailable.
- T07 exposes a missing printed page number. It does not simulate a corrupt PDF object or a transport-level extraction failure.
- T06 tests whether the agent treats hostile text inside the document as data. It does not test system prompt confidentiality or other platform security boundaries.
- Agent-level results must be recorded separately in \`../AGENT_ACCEPTANCE_RUN.md\`.
