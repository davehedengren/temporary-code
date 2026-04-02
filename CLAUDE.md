# Temporary Code — Mobile Workspace

General-purpose scratch workspace for quick coding from Claude Code on mobile. Projects here are experiments, prototypes, and one-offs that may graduate to their own repos.

## How This Repo Works

- Each project gets its own subdirectory (e.g., `my-project/`)
- When something is worth keeping, move it to a standalone repo
- Anything here can be deleted without warning — don't store anything precious

## Preferred Stack

Dave works across several stacks depending on the project. Default to whatever is simplest for the task:

- **Quick web apps:** Python + Flask, Jinja2 templates, vanilla JS, SQLite
- **Static pages:** Plain HTML/CSS/JS
- **Data work:** Python (pandas, matplotlib)
- **LLM integrations:** Anthropic Claude API (claude-opus-4-6), OpenAI, Gemini — keys in `.env`
- **Deployment:** Replit-ready when possible (host on `0.0.0.0:8080`, `start.py` entry point)

## Code Style

- Keep it simple. No frameworks unless the project demands it.
- Each project should be self-contained and runnable independently.
- Include a `requirements.txt` in any Python project.
- Use `.env` for API keys — never commit secrets.

## .env Keys (when needed)

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `HUGGING_FACE_API_KEY`

## Context

Dave is often working from his phone via Claude Code, so prefer concise responses and avoid unnecessary back-and-forth. Bias toward action — build the thing, then iterate.
