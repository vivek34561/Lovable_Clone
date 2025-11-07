# Lovable Clone

A minimalist, end-to-end “project-from-prompt” pipeline built with LangGraph + LangChain. It turns a natural-language idea into a concrete plan, breaks it into implementable tasks, and writes the resulting files into a safe project folder.

- Planner agent: turns your idea into a structured Plan.
- Architect agent: expands the plan into ordered implementation steps with explicit file targets.
- Coder agent: iteratively edits/creates files using tools (read/write/list) until all steps are done.

Outputs are written into `generated_project/`, keeping your repo safe by design.

## Why this exists

This repo is a compact, hackable template for building “Lovable”-style autonomous coding flows. It favors clarity over magic so you can extend it with your own tools, prompts, or model providers.

## Architecture at a glance

Flow: `planner → architect → coder (loop) → END`

- `agent/graph.py` wires a LangGraph `StateGraph` with three nodes.
- Each node uses the same LLM (`ChatOpenAI` interface) with structured outputs via Pydantic.
- File operations are sandboxed under `generated_project/` via safe path checks.

Key models (in `agent/states.py`):
- `Plan`: name, description, techstack, features, files (with purpose).
- `TaskPlan`: ordered list of `ImplementationTask` items.
- `CoderState`: current step index and optional current file content.

Key tools (in `agent/tools.py`):
- `write_file(path, content)` – writes to `generated_project/…`
- `read_file(path)` – reads from `generated_project/…`
- `list_files(directory)` – lists files inside `generated_project/…`
- `get_current_directory()` – returns the project root path
- `run_cmd(cmd, cwd, timeout)` – optional shell execution inside the sandbox (not enabled by default in the coder agent)

## Requirements

- Python 3.10+
- A GitHub Models access token set as `GITHUB_TOKEN` (used via the OpenAI-compatible API). The model runs through `https://models.inference.ai.azure.com` using the `ChatOpenAI` interface.

Python packages (see `requirements.txt`):
- `langgraph`, `langchain`, `langchain-openai`, `openai`, `pydantic`, `requests`, `dotenv` (aka `python-dotenv`)

Note: If you encounter import issues for `dotenv`, install `python-dotenv` explicitly.

## Setup (Windows / PowerShell)

1) Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) Install dependencies

```powershell
pip install -r requirements.txt
```

3) Provide your model credentials

Create a `.env` file in the repo root or export in your session:

```
GITHUB_TOKEN=ghp_your_token_here
```

Or in PowerShell for a one-off session:

```powershell
$env:GITHUB_TOKEN = "ghp_your_token_here"
```

## Run

Start the CLI and follow the prompt:

```powershell
python main.py
```

Optional:

```powershell
python main.py --recursion-limit 150
```

You’ll be asked: “Enter your project prompt:”. For example:

```
Build a colourful modern todo app in HTML, CSS, and JS
```

The system will:
- Create a high-level plan → expand to detailed steps → iteratively code files
- Write outputs to `generated_project/`
- Print the final state on completion

### Streamlit UI

Run an interactive UI in your browser:

```powershell
streamlit run streamlit_app.py
```

- Enter your prompt, adjust recursion limit, and run.
- Outputs appear under `generated_project/` and are viewable in the UI.

### Deploy (Procfile)

This repo includes a `Procfile` for platform deployment (e.g., Heroku/Render/Railway). The web process runs Streamlit:

```
web: streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0
```

Ensure the environment variable `GITHUB_TOKEN` is set on the platform, and that `requirements.txt` is installed at build time.

## Project structure

```
.
├─ main.py                  # CLI entrypoint
├─ requirements.txt         # Dependencies
├─ agent/
│  ├─ graph.py              # LangGraph wiring (planner → architect → coder loop)
│  ├─ prompt.py             # System and task prompts for agents
│  ├─ states.py             # Pydantic models for plan/tasks/state
│  └─ tools.py              # Sandbox file + optional shell tools
├─ LICENSE                  # MIT License
└─ generated_project/       # Created at runtime; all files are written here
```

## Configuration

- Model: change the `model` name or `temperature` in `agent/graph.py` where `ChatOpenAI` is created.
- Provider/endpoint: `base_url` is set to `https://models.inference.ai.azure.com`. Keep or modify as needed for your provider.
- Tools: to enable shell execution inside the agent, add `run_cmd` to `coder_tools` in `agent/graph.py` (use carefully).
- Safety: writes are restricted to `generated_project/` by `safe_path_for_project`. If a task references a path outside this folder, it will fail by design.

## Tips and troubleshooting

- No files appear? Ensure your prompt requests concrete files or that the planner/architect produce file targets.
- Empty reads are allowed: `read_file` returns `""` if a path doesn’t exist yet.
- “Attempt to write outside project root”: Tasks must target paths under `generated_project/`.
- Authentication errors: verify `GITHUB_TOKEN` and that the token has access to GitHub Models.
- `dotenv` vs `python-dotenv`: If `.env` isn’t loading, `pip install python-dotenv` explicitly.

## Extending

- Add domain-specific tools (e.g., run linters/tests, formatters, simple HTTP calls) and register them in `coder_tools`.
- Tighten prompts in `agent/prompt.py` to enforce file layouts, coding standards, or test-first workflows.
- Introduce validation steps (e.g., a test runner node) between coding iterations.

## License

MIT © 2025 vivek kumar gupta. See [LICENSE](./LICENSE).
