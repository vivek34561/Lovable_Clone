import os
import json
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel
import time

from agent.graph import agent
from agent.tools import init_project_root


# Load environment variables early
load_dotenv()

# Ensure generated_project exists
PROJECT_DIR = Path(init_project_root())

st.set_page_config(page_title="Lovable Clone UI", page_icon="🛠️", layout="wide")
st.title("Lovable Clone – Project-from-Prompt")
st.caption("Plan → Architect → Code → Files written to generated_project/")

with st.sidebar:
    st.header("Settings")
    recursion_limit = st.slider(
        "Recursion limit",
        min_value=5,
        max_value=200,
        value=30,
        step=5,
        help="Maximum iterations through the coder loop."
    )
    show_file_contents = st.checkbox("Show generated file contents", value=False)

# Prompt input
user_prompt = st.text_area(
    "Enter your project prompt",
    placeholder="e.g., Build a colourful modern todo app in HTML, CSS, and JS",
    height=120,
)

col_run, col_clear = st.columns([1, 1])
run_clicked = col_run.button("Run agent", type="primary", use_container_width=True, disabled=not bool(user_prompt.strip()))
clear_clicked = col_clear.button("Clear outputs", use_container_width=True)

# Optional: display token status
with st.expander("Environment / Model configuration", expanded=False):
    has_token = bool(os.environ.get("GITHUB_TOKEN"))
    st.write("GITHUB_TOKEN present:", "✅" if has_token else "❌")
    st.code(
        "Model and endpoint are configured in agent/graph.py using ChatOpenAI (OpenAI-compatible)",
        language="text",
    )

if clear_clicked:
    # Clear previously generated files (dangerous). Provide gentle cleanup that removes only files, not folder tree.
    removed = []
    if PROJECT_DIR.exists():
        for p in PROJECT_DIR.glob("**/*"):
            if p.is_file():
                try:
                    p.unlink()
                    removed.append(str(p))
                except Exception:
                    pass
    st.success(f"Cleared {len(removed)} files from generated_project/")

if run_clicked:
    if not os.environ.get("GITHUB_TOKEN"):
        st.error("GITHUB_TOKEN not set. Add it to a .env file or environment variables and restart.")
    else:
        with st.spinner("Running planner → architect → coder loop…"):
            final_state = None
            attempts = 3
            waits = [12, 24, 36]
            for i in range(attempts):
                try:
                    final_state = agent.invoke(
                        {"user_prompt": user_prompt},
                        {"recursion_limit": recursion_limit}
                    )
                    st.success("Agent run complete.")
                    break
                except KeyboardInterrupt:
                    st.warning("Operation cancelled.")
                    final_state = None
                    break
                except Exception as e:
                    message = str(e)
                    is_rate_limit = ("429" in message) or ("Rate limit" in message) or ("RateLimit" in message)
                    if i < attempts - 1 and is_rate_limit:
                        wait_s = waits[i]
                        st.info(f"Rate limit hit. Retrying in {wait_s} seconds… ({i+1}/{attempts})")
                        time.sleep(wait_s)
                        continue
                    st.exception(e)
                    final_state = None
                    break

        if final_state is not None:
            st.subheader("Final State")
            def to_primitive(obj):
                """Recursively convert Pydantic models and other objects to JSON-serializable primitives."""
                if isinstance(obj, BaseModel):
                    return obj.model_dump(mode="json", exclude_none=True)
                if isinstance(obj, dict):
                    return {k: to_primitive(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple, set)):
                    return [to_primitive(x) for x in obj]
                if isinstance(obj, Path):
                    return str(obj)
                # Best-effort: if still not serializable, cast to string
                try:
                    json.dumps(obj)
                    return obj
                except TypeError:
                    return str(obj)

            st.json(to_primitive(final_state))

# List generated files
st.subheader("generated_project/ contents")
if not PROJECT_DIR.exists():
    st.info("Folder not created yet. Run the agent to generate files.")
else:
    files = [p for p in PROJECT_DIR.glob("**/*") if p.is_file()]
    if not files:
        st.info("No files yet. After a successful run, outputs will appear here.")
    else:
        for f in sorted(files):
            rel = f.relative_to(PROJECT_DIR)
            with st.expander(str(rel), expanded=False):
                if show_file_contents:
                    try:
                        text = f.read_text(encoding="utf-8", errors="replace")
                        st.code(text, language="text")
                    except Exception as e:
                        st.write(f"(Could not read file: {e})")
                else:
                    st.write(f"Size: {f.stat().st_size} bytes")
                    st.caption("Enable 'Show generated file contents' in the sidebar to view content.")
