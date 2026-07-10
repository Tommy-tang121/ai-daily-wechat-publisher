---
name: baoyu-format-markdown
description: Formats plain text or markdown files with frontmatter, titles, summaries, headings, bold, lists, and code blocks. Use when user asks to "format markdown", "beautify article", "add formatting", or improve article layout. Outputs to {filename}-formatted.md.
version: 1.57.0
metadata:
  openclaw:
    homepage: https://github.com/JimLiu/baoyu-skills#baoyu-format-markdown
    requires:
      anyBins:
        - bun
        - npx
---

# Markdown Formatter

Transforms plain text or markdown into well-structured, reader-friendly markdown. The goal is to help readers quickly grasp key points, highlights, and structure — without changing any original content.

**Core principle**: Only adjust formatting and fix obvious typos. Never add, delete, or rewrite content.

## Usage

The workflow has two phases: **Analyze** (understand the content) then **Format** (apply formatting).

## Workflow

### Step 1: Read & Detect Content Type

Read the user-specified file, then detect content type:

| Indicator | Classification |
|-----------|----------------|
| Has `---` YAML frontmatter | Markdown |
| Has `#`, `##`, `###` headings | Markdown |
| Has `**bold**`, `*italic*`, lists, code blocks, blockquotes | Markdown |
| None of above | Plain text |

### Step 2: Analyze Content (Reader's Perspective)

Read the entire content carefully. Think from a reader's perspective: what would help them quickly understand and remember the key information?

**2.1 Highlights & Key Insights**
- Core arguments or conclusions the author makes
- Surprising facts, data points, or counterintuitive claims
- Memorable quotes or well-phrased sentences

**2.2 Structure Assessment**
- Does the content have a clear logical flow?
- Are there natural section boundaries that lack headings?
- Are there long walls of text that could benefit from visual breaks?

**2.3 Formatting Issues**
- Missing or inconsistent heading hierarchy
- Paragraphs that mix multiple topics
- Parallel items written as prose instead of lists
- Code, commands, or technical terms not marked as code

### Step 3: Format Content

Apply formatting guided by the Step 2 analysis.

**Formatting toolkit:**

| Element | When to use | Format |
|---------|-------------|--------|
| Headings | Natural topic boundaries | `##`, `###` hierarchy |
| Bold | Key conclusions, important terms | `**bold**` |
| Unordered lists | Parallel items, feature lists | `- item` |
| Ordered lists | Sequential steps, ranked items | `1. item` |
| Tables | Comparisons, structured data | Markdown table |
| Code | Commands, file paths | `` `inline` `` |
| Blockquotes | Notable quotes, warnings | `> quote` |
| Separators | Major topic transitions | `---` |

### Step 4: Save Formatted File

Save as `{original-filename}-formatted.md`

### Step 5: Completion Report

Display a report summarizing all changes made.
