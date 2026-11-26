# Example report — synthetic data only

> This example is fictional and demonstrates the output format. It is not a real company or a real financial statement.

## Executive summary

The fictional report states revenue of 1,250 thousand RUB and expenses of 1,094 thousand RUB for FY2025. The arithmetic difference is 156 thousand RUB. The report's printed net profit is also 156 thousand RUB. This arithmetic check passes, but it does not independently establish whether the underlying figures are complete or correctly classified.

## 1. Scope and documents reviewed

| File | Entity / subject | Period / date | Pages reviewed | Review status |
|---|---|---|---:|---|
| fictional-report.pdf | Example Company | FY2025 | 1–8 | All pages assumed accessible for this fictional example |

## 2. Key findings

### F-01 — Revenue less expenses agrees with printed net profit

- **Priority:** Medium
- **Classification:** Calculated result
- **Finding:** 1,250 − 1,094 = 156 thousand RUB. This equals the printed net profit of 156 thousand RUB.
- **Evidence:** [fictional-report.pdf, PDF page 4, table "Income statement", rows "Revenue", "Expenses" and "Net profit"]
- **Why it matters:** The arithmetic relationship is internally consistent for these three displayed values.
- **Confidence:** High for the arithmetic; not an audit opinion on the source figures.

### F-02 — Completeness of expense categories is not established

- **Priority:** Medium
- **Classification:** Not established
- **Finding:** The example extract does not show the detailed expense schedule, so the completeness and classification of expenses cannot be verified.
- **Evidence:** [fictional-report.pdf, PDF page 4, table "Income statement"]; detailed schedule not present in the reviewed excerpt.
- **Why it matters:** A mathematically consistent total may still rely on incomplete or misclassified inputs.
- **Confidence:** High that the detail is not present in the described excerpt; no conclusion about the full underlying accounting records.

## 3. Numerical checks

| Metric | Printed value | Recalculated value | Unit / period | Result | Source |
|---|---:|---:|---|---|---|
| Net profit | 156 | 1,250 − 1,094 = 156 | thousand RUB / FY2025 | Arithmetic agrees | PDF page 4, income statement |

## 4. Contradictions and gaps

| ID | Issue | Source A | Source B / missing evidence | Classification | Priority |
|---|---|---|---|---|---|
| G-01 | Detailed expense breakdown not available in the excerpt | PDF page 4 | No supporting schedule in reviewed excerpt | Missing evidence | Medium |

## 5. Limitations and confidence

This is a fictional demonstration. No real PDF was inspected. In an actual review, the agent must replace every example locator with a verified locator from the supplied document and must not reuse these sample values.

## 6. Questions / next actions

Request the detailed expense schedule if the user needs to verify expense completeness or classification.
