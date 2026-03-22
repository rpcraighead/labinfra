# md2docx: Because Not Everyone Reads Markdown

**Date:** March 2026
**Project:** Developer Tools
**Category:** Build Log
**Skills Demonstrated:** Python, python-docx, document formatting, open-source publishing

---

## The Problem

Markdown is the lingua franca of technical writing. Developers, sysadmins, and engineers live in it — READMEs, wikis, documentation, notes. It's clean, portable, and version-control friendly.

But send a `.md` file to someone outside your team and you get a blank stare. They open it in Word or Notepad and see pipes, hashes, triple backticks, and asterisks. The content is all there — it's just buried under formatting characters that make perfect sense to us and zero sense to everyone else.

We hit this problem in our own lab. We write everything in Markdown — infrastructure docs, build logs, project proposals. When we needed to share a proposal with someone who doesn't live in a terminal, we had to manually reformat it into a Word document. Every time.

## The Approach

Build a Python script that reads any Markdown file and outputs a professionally formatted `.docx` — something you'd be comfortable attaching to an email or printing for a meeting. No Pandoc, no LaTeX, no templates to manage. Just one script and one dependency.

### Design Goals

- **Zero configuration.** Point it at a `.md` file, get a `.docx`.
- **Looks good by default.** Styled headings, formatted tables, shaded code blocks — not the plain-text-in-a-Word-doc look that Pandoc produces without a custom template.
- **Handles real Markdown.** Not just paragraphs — tables with header rows, nested bullet lists, fenced code blocks, inline formatting.
- **Single file.** No package to install, no config files, no build step. Copy the script and go.

## How It Works

The script parses Markdown line by line and maps each element to its Word equivalent using `python-docx`:

| Markdown | Word Output |
|----------|-------------|
| `# Heading` | Styled H1 (22pt, dark blue) |
| `## Heading` | Styled H2 (16pt) |
| `**bold**` | Bold run |
| `*italic*` | Italic run |
| `` `code` `` | Consolas 9pt, dark color |
| ` ``` code block ``` ` | Consolas on gray background |
| `\| table \|` | Formatted table with dark header row and alternating shading |
| `- bullet` | Bulleted list with nested indent support |
| `1. item` | Numbered list |
| `---` | Subtle horizontal divider |

### Example

```bash
# Convert a file
python md2docx.py README.md

# Specify output path
python md2docx.py project-proposal.md -o proposal.docx
```

The output is a clean Word document with consistent typography (Calibri), professional table formatting, and readable code blocks — the kind of document you can hand to anyone.

### Use as a Library

```python
from md2docx import parse_markdown, build_docx

md_text = parse_markdown("notes.md")
build_docx(md_text, "notes.docx")
```

This makes it easy to integrate into automation pipelines. We use it in our lab to auto-generate Word versions of documentation alongside the Markdown originals.

## Why Not Pandoc?

Pandoc is the Swiss Army knife of document conversion. It handles dozens of formats and is incredibly powerful. But for Markdown-to-Word specifically, the default output is plain — no styled tables, no code formatting, no visual hierarchy. Getting good-looking output requires building a custom reference `.docx` template and potentially writing Lua filters.

md2docx takes the opposite approach: one format, one direction, zero configuration. The styling is built into the script. You get dark header rows in tables, alternating row shading, monospace code with background shading, and proper heading hierarchy out of the box.

If you need to convert between 40 formats, use Pandoc. If you need to make one Markdown file look good in Word, use md2docx.

## The Result

A single Python file that turns any Markdown document into a readable Word file in under a second. We use it for:

- **Project proposals** — write in Markdown, deliver in Word
- **Lab documentation** — Markdown for the website, Word for sharing
- **Build logs** — the post you're reading right now has a `.docx` version

The tool is open source and available on GitHub: [github.com/rpcraighead/md2docx](https://github.com/rpcraighead/md2docx)

## What I Learned

- **python-docx is surprisingly capable.** You can control paragraph shading, table cell colors, font properties, and even XML-level formatting without much pain.
- **Markdown parsing doesn't need a library** for the common cases. A line-by-line state machine handles headings, tables, code blocks, and lists cleanly.
- **Good defaults beat configuration.** Nobody wants to pick fonts and colors when they just need a readable document. Opinionated styling that looks professional out of the box is more useful than a dozen options.

## Try It Yourself

**Requirements:** Python 3, `python-docx` (`pip install python-docx`)
**Install:** Clone the repo or copy `md2docx.py`
**Time:** 30 seconds

```bash
pip install python-docx
python md2docx.py your-document.md
```

---

*Built with Claude Code. Lab documented at rpc-cyberflight.com.*
