# Analysis protocol

## 1. Establish the scope

Write down:
- The question the user wants answered.
- The documents actually accessible.
- The entity, reporting period, document version and scope for each file.
- Any requested output format or level of detail.

If two files are different versions, establish whether they are revisions, appendices, translations or separate reporting periods. Do not assume they are comparable.

## 2. Inspect document structure

For each PDF:
1. Determine whether selectable text is available.
2. Identify page count and any obvious gaps, rotated pages, appendices or scanned sections when the tools permit.
3. Locate the sections, tables and pages relevant to the question.
4. Record whether the document contains mixed text and scanned-image pages.

If OCR is unavailable, do not pretend that scanned pages were analyzed. If OCR output is uncertain, mark the affected values and verify against the page image when possible.

## 3. Build an evidence ledger

For each relevant item, record:

| Field | What to capture |
|---|---|
| ID | Short stable label, e.g. F-01 |
| Type | Fact, claim, obligation, figure, date, assumption |
| Exact content | Faithful short quote or normalized value |
| Source | Filename and precise page/section/table/row |
| Context | Entity, period, unit, currency, scope |
| Status | Verified, partially verified, ambiguous, not verified |
| Notes | OCR issue, ambiguity, missing context |

Do not merge facts from different files into one row without preserving both sources.

## 4. Verify numbers

For each important figure:
- Preserve sign, decimal separator, thousands separator and parentheses.
- Record the unit and scale exactly (for example, RUB, thousand RUB, million EUR, percent).
- Check whether the figure is a point-in-time balance or a period flow.
- Recalculate totals only when all necessary components are available.
- Recalculate percentage change as `(new - old) / old × 100%`; state the base period and do not calculate when the base is zero or undefined.
- For ratios, state numerator, denominator and whether the inputs share the same scope and period.
- Keep printed and recalculated values separate.
- Flag rounding differences rather than silently forcing equality.

Example:
- Printed revenue: 1,250 thousand RUB.
- Printed expenses: 1,094 thousand RUB.
- Calculated difference: 156 thousand RUB.
- Formula: 1,250 − 1,094 = 156 thousand RUB.
- Source: [Report.pdf, PDF page 8, table "Income statement", rows "Revenue" and "Expenses"].

## 5. Compare documents

Before comparing, align:
- Entity and consolidation perimeter.
- Period start/end dates.
- Currency and scale.
- Accounting or measurement basis.
- Gross/net presentation.
- Version/date of issue.
- Whether the number is audited, provisional, forecast or actual.

Classify discrepancies:
- Direct contradiction: same scope and period, incompatible statements.
- Scope mismatch: values refer to different entities or perimeters.
- Period mismatch: different dates or reporting periods.
- Unit/currency mismatch: values cannot be compared as shown.
- Revision: a later version changes an earlier value.
- Unresolved: available evidence does not explain the difference.

Never label a difference a contradiction until scope and basis have been checked.

## 6. Assess claims and conclusions

For each material conclusion in the PDF, ask:
1. What evidence is cited?
2. Does that evidence support the exact wording?
3. Are material assumptions disclosed?
4. Is there contrary evidence elsewhere in the same or another file?
5. Is the conclusion a fact, calculation, opinion, forecast or recommendation?

Use cautious language. "The report states that..." is not the same as "The documents establish that...".

## 7. Prioritize findings

Use:
- High: material discrepancy, missing evidence or ambiguity that could change the user's decision.
- Medium: relevant inconsistency or limitation that needs clarification.
- Low: editorial, formatting or non-material issue.

Explain the reason for each priority. Do not imply a formal legal or regulatory risk rating.

## 8. Handle incomplete evidence

If a file cannot be opened, pages are unreadable, extraction is incomplete or a key table is missing:
- Identify the exact limitation.
- State which conclusions are affected.
- Do not fill gaps by guessing.
- Ask for a clearer scan, missing page or source file only when needed to answer the user's question.
