# PDF Evidence Analyst — Agensi package

A standalone agent skill for evidence-backed analysis of PDF documents. It does not require the PDF-Analyst Windows application, a local database, a hosted backend, API keys or Agensi tools.

## Package contents

- `SKILL.md` — primary skill instructions and marketplace metadata.
- `references/analysis-protocol.md` — repeatable document review and verification method.
- `references/report-template.md` — structured report format.
- `references/quality-checklist.md` — final validation checklist.

## Intended listing

- **Name:** PDF Evidence Analyst
- **Version:** 1.0.0
- **Proposed price:** US$5 one-time (subject to creator dashboard and payout setup)
- **Positioning:** evidence-backed PDF review, numerical verification, document comparison and contradiction detection.
- **Dependencies:** an AI agent that supports the SKILL.md standard and can access/read the user's PDF files.

## Important product boundary

This package provides an analysis workflow, not a PDF parser or standalone application. Actual extraction, OCR, calculations and page-image inspection depend on the connected agent's available file-reading and computation capabilities. The skill must disclose unavailable capabilities rather than imply they were used.

The PDF-Analyst application remains a separate product. Buyers do not need it to use this skill.

## Local package validation

1. Check that the archive has `SKILL.md` at its root.
2. Check frontmatter and required `name` / `description`.
3. Check every referenced file path exists.
4. Check that the package contains text files only and no secrets, PDFs, binaries, virtual environments or caches.
5. Test with representative text PDFs, scanned PDFs, multi-document comparisons, conflicting figures and missing-page cases.
6. Upload to Agensi only after the creator profile and payout method are configured and the listing preview has been reviewed.

Agensi packaging guidance: https://www.agensi.io/docs/packaging
