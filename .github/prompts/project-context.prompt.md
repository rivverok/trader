---
description: "Regenerate copilot-instructions.md by scanning the current project structure, tech stack, and architecture plans"
agent: "agent"
tools: ["file_search", "read_file", "list_dir", "grep_search", "semantic_search", "replace_string_in_file", "create_file"]
---

# Regenerate Project Context

You are updating the AI Trader project context file at `.github/copilot-instructions.md`. This file is automatically loaded into every Copilot chat session to provide project awareness.

## Your Task

1. **Scan the current project structure** — list all directories and files to understand what has been built so far. Walk `backend/app/`, `frontend/src/`, `scripts/`, and root config files.

2. **Read key configuration files** to extract the actual tech stack and versions:
   - `backend/pyproject.toml`
   - `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tailwind.config.ts`
   - `docker-compose.yml`, `docker-compose.override.yml`
   - `backend/app/config.py`
   - Any `.env.example` or config files

3. **Read the architecture plans** in `plans/` to understand the full vision and domain concepts.

4. **Determine build progress** — which areas are complete, in-progress, or not started based on what code exists.

5. **Regenerate `.github/copilot-instructions.md`** with the following sections:
   - **What Is This** — one-paragraph project summary
   - **Tech Stack** — table of actual technologies and versions from pyproject.toml / package.json
   - **Project Structure** — current directory tree (not planned, actual)
   - **API Routes** — table of route files, prefixes, and descriptions from `backend/app/api/`
   - **Architecture** — pipeline layers, ensemble signals, risk management, scheduling
   - **Key Domain Concepts** — ProposedTrade, ContextSynthesis, RiskState, AnalystInput, Growth Mode, Stock Discovery
   - **Coding Standards** — extracted from config files and observed patterns
   - **Build Progress** — which areas are done vs. remaining

## Rules

- Only document what ACTUALLY EXISTS in the codebase for structure and versions. Use the plans for domain concepts and architecture principles.
- Keep it concise — this loads into every chat session. Target under 200 lines of content.
- Use tables and code blocks for scan-friendly reading.
- Add the header: `> **Auto-generated project context.** Refresh by running '/project-context' in chat.`
- Preserve the locked tech stack table from the plans if packages haven't been installed yet.
