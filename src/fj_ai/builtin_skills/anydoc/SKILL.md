---
name: anydoc
description: "Use this skill whenever the user wants to read or extract the contents of an office document, spreadsheet, presentation, ebook, or PDF that cannot be read directly. Converts Word (.doc, .docx), PowerPoint (.ppt, .pptx), Excel (.xls, .xlsx), OpenDocument (.odt, .ods, .odp), RTF, EPUB, CSV, and PDF files to GitHub-Flavored Markdown. Triggers include: any mention of 'convert to markdown', 'read this document', 'extract text from docx/pdf/pptx/xlsx', or requests to get the contents of an office document, spreadsheet, presentation, ebook, or PDF. Do NOT use for authoring new documents (use the docx/pptx/xlsx skills) or for scanned/image-only PDFs needing OCR."
license: MIT
---

# Convert documents to Markdown (anydoc)

Run the `@firecrawl/anydoc` CLI. It needs Node 20+ and no install:

```bash
npx -y @firecrawl/anydoc <file>              # Markdown to stdout
npx -y @firecrawl/anydoc <file> -o out.md    # write to a file
npx -y @firecrawl/anydoc - --format csv < f  # read stdin
```

> This skill is read-only extraction. To **author or edit** documents, use the
> `docx`, `pptx`, `xlsx`, or `pdf` skills instead.

## Supported inputs

`.doc`, `.docx`, `.docm`, `.odt`, `.rtf`, `.epub`, `.pdf`, `.ppt`, `.pps`, `.pot`,
`.pptx`, `.pptm`, `.ppsx`, `.ppsm`, `.odp`, `.xls`, `.xlsx`, `.xlsm`, `.xlsb`,
`.ods`, `.csv`.

## Rules

1. The format is detected from the file content. Pass `--format <name>` only when detection cannot work: CSV from stdin, or a missing or wrong extension.
2. Exit codes: `0` success, `1` the document could not be converted, `2` usage error. Failures print one `anydoc: <message>` line to stderr. The CLI never prompts.
3. For a large document, write to a file with `-o` and read the parts you need instead of streaming everything into context.
4. Scanned and image-only PDFs need OCR, which anydoc does not do; they fail as unsupported. The hosted [Firecrawl Parse](https://firecrawl.dev/parse) API handles those — or fall back to the `pdf` skill's OCR tooling.
5. Inside a Node, Python, or Rust codebase, prefer the library over shelling out: `@firecrawl/anydoc` on npm, `firecrawl-anydoc` on PyPI, `anydoc` on crates.io. Each exposes the same `to_markdown` / `toMarkdown` API.

## Dependencies

Node 20+ (for `npx -y @firecrawl/anydoc`). No install step — the CLI is fetched on first run.
