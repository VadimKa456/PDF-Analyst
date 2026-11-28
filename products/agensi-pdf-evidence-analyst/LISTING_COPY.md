# Agensi listing copy — submission draft

## Listing name

PDF Evidence Analyst

## Summary

Turn PDFs into evidence-backed analysis: extract key facts, verify calculations, compare documents, and flag contradictions with page-level source references.

## Description

PDF Evidence Analyst helps your AI agent review one or more PDF documents systematically instead of producing an untraceable summary.

It follows an evidence-first workflow:
- Extracts the facts, figures, dates, units, obligations and claims relevant to your question.
- Links material findings to the source filename, PDF page and table or section when the connected agent can access those details.
- Separates facts printed in the document from calculations and interpretations.
- Rechecks totals, percentages and period changes, showing the formulas and inputs.
- Compares versions and reporting periods while checking scope, currency, units and measurement basis.
- Flags contradictions, missing evidence, ambiguous wording and OCR uncertainty.
- Produces a structured report with an executive summary, findings, numerical checks, limitations and next actions.

## See it in action

The following is a fictional illustration of the report style, not a result from a real customer document.

**User request:** “Review this quarterly report. Check whether the revenue and expense figures reconcile, and tell me whether the year-over-year growth claim is supported.”

**Evidence captured from the PDF**
- Revenue — 1,250 thousand RUB — source: `Quarterly-Report.pdf`, PDF page 8, “Income statement” table, “Revenue” row.
- Operating expenses — 1,094 thousand RUB — source: same file and table, “Operating expenses” row.
- Revenue in the comparable prior-year period — 1,100 thousand RUB — source: PDF page 8, prior-year column.

**Numerical checks**
- Calculated difference: 1,250 − 1,094 = 156 thousand RUB. This is a calculated result, not a printed subtotal.
- Calculated revenue growth: (1,250 − 1,100) / 1,100 × 100 = 13.64%.
- If the report claims 14% growth, the claim is consistent with rounding to a whole percentage point, subject to confirming that both periods use the same scope and accounting basis.

**Finding**
The figures shown in the example reconcile arithmetically. The growth claim is supported by the stated inputs to the precision shown. This does not independently verify the underlying accounting records.

**Limitation**
A real review would identify any unreadable pages, OCR uncertainty, missing context or unavailable calculation tools. It would not invent citations or claim that inaccessible pages were reviewed.

## Best for

- Reviewing financial statements and business reports.
- Comparing multiple PDF versions or reporting periods.
- Checking totals, percentages and numerical consistency.
- Reviewing contracts, policies and technical reports for key claims.
- Preparing concise, traceable document-review reports.

## Compatibility

Requires an AI agent that supports the SKILL.md skill format and can access the PDF files supplied by the user. The agent must be able to read PDF text for text-based analysis. OCR, page-image inspection and calculations depend on the tools available in that agent session. This skill does not install a PDF reader, OCR engine or desktop application.

## Limitations and FAQ

**Does it read every scanned PDF?** Not necessarily. OCR and page-image inspection depend on the connected agent's capabilities. If those capabilities are unavailable or results are uncertain, the skill instructs the agent to disclose the limitation.

**Does it replace an auditor, lawyer or accountant?** No. It supports document review and evidence organization; it does not provide an audit, legal opinion, accounting opinion or regulated professional advice.

**Does it require the PDF-Analyst desktop application?** No. It is a standalone agent workflow and does not require the PDF-Analyst application, backend, API keys or a hosted service.

**Does it send documents to an external service?** The skill itself does not add an upload service. The agent should not send document contents elsewhere unless the user explicitly requests and approves that destination.

## Categories (suggested)

- Productivity
- Research
- Business

## Tags (suggested)

PDF, document analysis, financial review, due diligence, evidence, calculations, document comparison

## Proposed price

US$5 one-time. Confirm the final price and payout configuration in Creator Studio before submission.

## Internal release note — not listing copy

This is proposed marketplace copy. The fictional example above is illustrative and must not be represented as a real benchmark, customer case or completed acceptance test. Run the acceptance scenarios with representative, permission-cleared PDFs before removing the Draft status.
