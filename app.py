import os
import json
from pathlib import Path
import time
import io
import zipfile
import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel   
from agent.graph import build_agent
from agent.tools import init_project_root


# Load environment variables early
load_dotenv()

# If running on Streamlit Cloud, surface GROQ_API_KEY from secrets to env
try:
    if "GROQ_API_KEY" in st.secrets and not os.environ.get("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
except Exception:
    pass

# Ensure generated_project exists
PROJECT_DIR = Path(init_project_root())

# Page setup
st.set_page_config(page_title="Lovable Clone", page_icon="💜", layout="wide")
# Initialize session state for API keys (not persisted to disk)
if "OPENAI_API_KEY" not in st.session_state:
    # Do not prefill from environment; require user input
    st.session_state["OPENAI_API_KEY"] = ""


# Lightweight custom CSS to evoke a "lovable" colorful aesthetic
st.markdown(
    """
    <style>
      :root {
        --lovable-grad: linear-gradient(135deg,#7C3AED 0%, #EC4899 50%, #F59E0B 100%);
        --card-bg: rgba(255,255,255,0.7);
        --card-border: rgba(255,255,255,0.4);
      }
      .lovable-hero {
        background: var(--lovable-grad);
        color: #fff;
        border-radius: 16px;
        padding: 28px 28px;
        box-shadow: 0 16px 48px rgba(124,58,237,0.25);
      }
      .lovable-card {
        backdrop-filter: saturate(140%) blur(8px);
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 12px;
        padding: 18px 18px;
      }
      .lovable-btn {
        border-radius: 10px !important;
      }
      .lovable-caption { color: rgba(255,255,255,0.9); }
      .lovable-small { color: #6b7280; font-size: 0.9rem; }
      .lovable-divider { border-top: 1px dashed rgba(0,0,0,0.08); margin: 12px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Hero
st.markdown(
    """
    <div class="lovable-hero">
      <h1 style="margin:0">💜 Lovable Clone</h1>
      <p style="margin:6px 0 0">Turn prompts into projects: Plan → Architect → Code → Preview</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Settings")
    # Provider selection
    provider = st.radio("Provider", ["Groq", "OpenAI"], horizontal=True)
    # Model selection inputs
    if provider == "Groq":
        groq_model = st.text_input("Groq model", value="openai/gpt-oss-120b")
        groq_key_present = bool(os.environ.get("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY"))
        st.caption(f"GROQ_API_KEY: {'✅ present' if groq_key_present else '❌ missing'}")
    else:
        openai_model = st.text_input("OpenAI model", value="gpt-4o-mini")
        # Allow entering key when using OpenAI; keep in session state
        openai_api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=st.session_state.get("OPENAI_API_KEY", ""),
            help="Key is kept in memory for this session only.",
        )
        # Update session + environment live so run button enables immediately
        st.session_state["OPENAI_API_KEY"] = openai_api_key
        if openai_api_key:
            os.environ["OPENAI_API_KEY"] = openai_api_key
        st.caption("Provide your OpenAI API key to run with OpenAI.")

    recursion_limit = st.slider(
        "Recursion limit",
        min_value=5,
        max_value=200,
        value=30,
        step=5,
        help="Maximum iterations through the coder loop."
    )
    show_file_contents = st.checkbox("Show generated file contents", value=False)
    # (Environment status removed per request)

# Sidebar: Live preview & download (render later too after run)
def inline_assets(html_text: str, html_path: Path) -> str:
    """Inline local CSS/JS referenced by relative tags for more reliable Streamlit preview."""
    try:
        base_dir = html_path.parent
        # Inline <link rel="stylesheet" href="...">
        import re
        def repl_link(m):
            href = m.group(1).strip().strip('"\'')
            target = (base_dir / href).resolve()
            try:
                if PROJECT_DIR.resolve() in target.parents or target.parent == PROJECT_DIR.resolve() or target == PROJECT_DIR.resolve():
                    css = target.read_text(encoding="utf-8", errors="replace")
                    return f"<style>\n{css}\n</style>"
            except Exception:
                pass
            return m.group(0)
        html_text = re.sub(r"<link[^>]*rel=\"stylesheet\"[^>]*href=\"([^\"]+)\"[^>]*>", repl_link, html_text, flags=re.IGNORECASE)

        # Inline <script src="..."></script>
        def repl_script(m):
            src = m.group(1).strip().strip('"\'')
            target = (base_dir / src).resolve()
            try:
                if PROJECT_DIR.resolve() in target.parents or target.parent == PROJECT_DIR.resolve() or target == PROJECT_DIR.resolve():
                    js = target.read_text(encoding="utf-8", errors="replace")
                    return f"<script>\n{js}\n</script>"
            except Exception:
                pass
            return m.group(0)
        html_text = re.sub(r"<script[^>]*src=\"([^\"]+)\"[^>]*>\s*</script>", repl_script, html_text, flags=re.IGNORECASE)
        return html_text
    except Exception:
        return html_text

def sidebar_live_preview_and_download(final_state):
    with st.sidebar:
        st.divider()
        st.subheader("Generated Project (Live)")
        if not PROJECT_DIR.exists():
            st.caption("Folder will appear after a successful run.")
            return
        files = [p for p in PROJECT_DIR.glob("**/*") if p.is_file()]
        if not files:
            st.caption("No files yet.")
        else:
            # HTML file selection
            html_files = sorted([p for p in PROJECT_DIR.glob("**/*.html")])
            default_index = 0
            if html_files:
                # Prefer index.html if present
                for i, p in enumerate(html_files):
                    if p.name.lower() == "index.html":
                        default_index = i
                        break
                selected = st.selectbox(
                    "Preview HTML file",
                    options=[str(p.relative_to(PROJECT_DIR)) for p in html_files],
                    index=default_index,
                )
                try:
                    html_path = PROJECT_DIR / selected
                    html_text = html_path.read_text(encoding="utf-8", errors="replace")
                    html_text = inline_assets(html_text, html_path)
                    st.components.v1.html(html_text, height=500, scrolling=True)
                except Exception as e:
                    st.caption(f"(Could not render HTML: {e})")
            else:
                st.caption("No HTML files to preview yet.")

            # Download zip after full generation completes
            if files:
                st.divider()
                st.caption("Download generated files:")
                # Zip only generated_project
                try:
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        for p in PROJECT_DIR.rglob("*"):
                            if p.is_file():
                                zf.write(p, arcname=str(p.relative_to(PROJECT_DIR)))
                    buf.seek(0)
                    st.download_button(
                        label="Download generated_project.zip",
                        data=buf.getvalue(),
                        file_name="generated_project.zip",
                        mime="application/zip",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.caption(f"(Could not create zip: {e})")

                # Zip source code + generated_project
                try:
                    root = Path.cwd()
                    src_buf = io.BytesIO()
                    include_files = [
                        root / "app.py",
                        root / "main.py",
                        root / "README.md",
                        root / "requirements.txt",
                        root / "Procfile",
                        root / "LICENSE",
                        root / "streamlit_app.py",
                    ]
                    exclude_dirs = {"loveable_env", "myenv", ".venv", "venv", "Scripts", "build", "dist", "__pycache__"}
                    with zipfile.ZipFile(src_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        # Add source files
                        for f in include_files:
                            if f.exists() and f.is_file():
                                zf.write(f, arcname=str(f.name))
                        # Add agent and generated_project directories
                        for base in [root / "agent", PROJECT_DIR]:
                            if base.exists():
                                for p in base.rglob("*"):
                                    if p.is_file():
                                        # Skip excluded directories
                                        if any(part in exclude_dirs for part in p.parts):
                                            continue
                                        arc = str(p.relative_to(root))
                                        zf.write(p, arcname=arc)
                    src_buf.seek(0)
                    st.download_button(
                        label="Download code_and_generated_project.zip",
                        data=src_buf.getvalue(),
                        file_name="code_and_generated_project.zip",
                        mime="application/zip",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.caption(f"(Could not create full zip: {e})")

# Prompt input card
st.markdown("<div class='lovable-card'>", unsafe_allow_html=True)
user_prompt = st.text_area(
    "Your project prompt",
    placeholder="e.g., Build a colourful modern todo app in HTML, CSS, and JS",
    height=120,
)
col_run, col_clear = st.columns([1, 1])
run_disabled = not bool(user_prompt.strip()) or (
    (provider == "Groq" and not bool(os.environ.get("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY"))) or
    (provider == "OpenAI" and not bool(st.session_state.get("OPENAI_API_KEY")))
)
run_clicked = col_run.button(
    "Run agent", type="primary", use_container_width=True,
    disabled=run_disabled,
)
clear_clicked = col_clear.button("Clear outputs", use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)

if clear_clicked:
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

final_state = None

if run_clicked:
    # Build LLM based on provider selection
    try:
        if provider == "Groq":
            from langchain_groq.chat_models import ChatGroq
            api_key = os.environ.get("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY")
            llm = ChatGroq(model=groq_model, api_key=api_key)
        else:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model=openai_model, api_key=st.session_state.get("OPENAI_API_KEY"))
    except Exception as e:
        st.error(f"Failed to initialize LLM: {e}")
        llm = None

    if llm is None:
        st.stop()

    # Compile agent dynamically with chosen LLM
    dynamic_agent = build_agent(llm)

    with st.spinner("Running planner → architect → coder loop…"):
        attempts = 3
        waits = [12, 24, 36]
        for i in range(attempts):
            try:
                final_state = dynamic_agent.invoke(
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
                msg = str(e)
                is_rate_limit = ("429" in msg) or ("Rate limit" in msg) or ("RateLimit" in msg)
                if i < attempts - 1 and is_rate_limit:
                    wait_s = waits[i]
                    st.info(f"Rate limit hit. Retrying in {wait_s} seconds… ({i+1}/{attempts})")
                    time.sleep(wait_s)
                    continue
                st.exception(e)
                final_state = None
                break

def to_primitive(obj):
    """Convert Pydantic models and other objects to JSON-serializable primitives."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", exclude_none=True)
    if isinstance(obj, dict):
        return {k: to_primitive(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_primitive(x) for x in obj]
    if isinstance(obj, Path):
        return str(obj)
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return str(obj)

# Structured result view
if final_state is not None:
    st.markdown("<div class='lovable-card'>", unsafe_allow_html=True)
    st.subheader("Run Results")
    tab_plan, tab_tasks, tab_progress, tab_json = st.tabs(["Plan", "Tasks", "Progress", "Final JSON"])

    with tab_plan:
        plan = final_state.get("plan")
        if plan:
            primitive = to_primitive(plan)
            st.markdown(f"**Name:** {primitive.get('name','')}")
            st.markdown(f"**Description:** {primitive.get('description','')}")
            st.markdown(f"**Techstack:** {primitive.get('techstack','')}")
            features = primitive.get("features") or []
            st.markdown("**Features:**")
            for f in features:
                st.write("- ", f)
            files = primitive.get("files") or []
            st.markdown("**Files:**")
            for f in files:
                st.write(f"- {f.get('path','')} — {f.get('purpose','')}")
        else:
            st.info("No plan returned.")

    with tab_tasks:
        task_plan = final_state.get("task_plan")
        if task_plan:
            primitive = to_primitive(task_plan)
            steps = primitive.get("implementation_steps") or []
            for i, step in enumerate(steps, start=1):
                st.write(f"**Step {i}:**")
                st.write(f"- File: {step.get('filepath','')}")
                st.write(f"- Task: {step.get('task_description','')}")
                st.divider()
        else:
            st.info("No task plan returned.")

    with tab_progress:
        coder_state = final_state.get("coder_state")
        if coder_state:
            primitive = to_primitive(coder_state)
            st.write("**Current step index:**", primitive.get("current_step_idx"))
            st.write("**Status:**", final_state.get("status", "Unknown"))
            current_content = primitive.get("current_file_content")
            if current_content:
                st.code(current_content, language="text")
        else:
            st.info("No coder state returned.")

    with tab_json:
        st.json(to_primitive(final_state))
    st.markdown("</div>", unsafe_allow_html=True)

    # Update sidebar with live preview and download once we have final_state
    sidebar_live_preview_and_download(final_state)

# File outputs
st.subheader("generated_project/ contents")
if not PROJECT_DIR.exists():
    st.info("Folder not created yet. Run the agent to generate files.")
else:
    files = [p for p in PROJECT_DIR.glob("**/*") if p.is_file()]
    if not files:
        st.info("No files yet. After a successful run, outputs will appear here.")
    else:
        # Quick preview for index.html if present
        index_html = PROJECT_DIR / "index.html"
        if index_html.exists():
            with st.expander("Live Preview: index.html", expanded=True):
                try:
                    html = index_html.read_text(encoding="utf-8", errors="replace")
                    html = inline_assets(html, index_html)
                    st.components.v1.html(html, height=600, scrolling=True)
                except Exception as e:
                    st.write(f"(Could not render HTML: {e})")

        # File list with optional content display
        for f in sorted(files):
            rel = f.relative_to(PROJECT_DIR)
            with st.expander(str(rel), expanded=False):
                if show_file_contents:
                    try:
                        text = f.read_text(encoding="utf-8", errors="replace")
                        ext = f.suffix.lower()
                        lang = {
                            ".js": "javascript",
                            ".ts": "typescript",
                            ".py": "python",
                            ".css": "css",
                            ".html": "html",
                            ".json": "json",
                            ".md": "markdown",
                        }.get(ext, "text")
                        st.code(text, language=lang)
                        if ext == ".html":
                            st.components.v1.html(text, height=450, scrolling=True)
                    except Exception as e:
                        st.write(f"(Could not read file: {e})")
                else:
                    st.write(f"Size: {f.stat().st_size} bytes")
                    st.caption("Enable 'Show generated file contents' in the sidebar to view content.")

# Also show sidebar live preview even before/without a run (if files exist)
if final_state is None:
    sidebar_live_preview_and_download(final_state)
