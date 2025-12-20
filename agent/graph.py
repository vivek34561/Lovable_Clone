from dotenv import load_dotenv
try:
    from langchain_core.globals import set_verbose, set_debug
except ImportError:
    # Fallback for older LangChain versions
    from langchain.globals import set_verbose, set_debug
from langchain_groq.chat_models import ChatGroq
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.prebuilt import create_react_agent
import re

from agent.prompt import *
from agent.states import *
from agent.tools import write_file, read_file, get_current_directory, list_files

_ = load_dotenv()

set_debug(True)
set_verbose(True)


def build_agent(llm):
    """Build and return a compiled LangGraph agent using the provided LLM."""

    def planner_agent(state: dict) -> dict:
        """Converts user prompt into a structured Plan."""
        user_prompt = state["user_prompt"]
        resp = llm.with_structured_output(Plan, strict=True).invoke(
            planner_prompt(user_prompt)
        )
        if resp is None:
            raise ValueError("Planner did not return a valid response.")
        return {"plan": resp}

    def architect_agent(state: dict) -> dict:
        """Creates TaskPlan from Plan."""
        plan: Plan = state["plan"]
        resp = llm.with_structured_output(TaskPlan, strict=True).invoke(
            architect_prompt(plan=plan.model_dump_json())
        )
        if resp is None:
            raise ValueError("Planner did not return a valid response.")

        # Log the structured task plan
        try:
            print(resp.model_dump_json())
        except Exception:
            pass
        return {"task_plan": resp}

    def coder_agent(state: dict) -> dict:
        """LangGraph tool-using coder agent."""
        coder_state: CoderState = state.get("coder_state")
        if coder_state is None:
            coder_state = CoderState(task_plan=state["task_plan"], current_step_idx=0)

        steps = coder_state.task_plan.implementation_steps
        if coder_state.current_step_idx >= len(steps):
            return {"coder_state": coder_state, "status": "DONE"}

        current_task = steps[coder_state.current_step_idx]
        existing_content = read_file.run(current_task.filepath)

        system_prompt = coder_system_prompt()
        user_prompt = (
            f"Task: {current_task.task_description}\n"
            f"File: {current_task.filepath}\n"
            f"Existing content:\n{existing_content}\n"
            "Use write_file(path, content) to save your changes."
        )

        coder_tools = [read_file, write_file, list_files, get_current_directory]
        react_agent = create_react_agent(llm, coder_tools)

        react_agent.invoke({"messages": [{"role": "system", "content": system_prompt},
                                         {"role": "user", "content": user_prompt}]})

        coder_state.current_step_idx += 1
        return {"coder_state": coder_state}

    def frontend_check_agent(state: dict) -> dict:
        """Validate that HTML links to CSS/JS correctly within generated_project."""
        # List all files in the project
        listing = list_files.run(".")
        files = [line.strip() for line in listing.splitlines() if line.strip()]
        html_files = [f for f in files if f.lower().endswith(".html")]

        if not html_files:
            return {
                "frontend_validation": {
                    "status": "NO_HTML",
                    "details": "No HTML files found in generated_project.",
                }
            }

        # Prefer index.html if present
        html_file = next((f for f in html_files if f.lower().endswith("index.html")), html_files[0])
        html_content = read_file.run(html_file)

        # Extract CSS href and JS src
        css_href_match = re.search(r"<link[^>]*href=\"([^\"]+)\"", html_content, re.IGNORECASE)
        js_src_match = re.search(r"<script[^>]*src=\"([^\"]+)\"", html_content, re.IGNORECASE)

        css_href = css_href_match.group(1) if css_href_match else None
        js_src = js_src_match.group(1) if js_src_match else None

        css_exists = bool(css_href and read_file.run(css_href))
        js_exists = bool(js_src and read_file.run(js_src))

        status = "OK" if css_exists and js_exists else "ISSUES"
        details = []
        if not css_href:
            details.append("Missing <link ... href=...> to CSS")
        elif not css_exists:
            details.append(f"CSS file not found: {css_href}")
        if not js_src:
            details.append("Missing <script ... src=...> to JS")
        elif not js_exists:
            details.append(f"JS file not found: {js_src}")

        return {
            "frontend_validation": {
                "status": status,
                "html_file": html_file,
                "css_href": css_href,
                "js_src": js_src,
                "css_exists": css_exists,
                "js_exists": js_exists,
                "details": "; ".join(details) if details else "",
            }
        }

    graph = StateGraph(dict)

    graph.add_node("planner", planner_agent)
    graph.add_node("architect", architect_agent)
    graph.add_node("coder", coder_agent)
    graph.add_node("frontend_check", frontend_check_agent)

    graph.add_edge("planner", "architect")
    graph.add_edge("architect", "coder")
    graph.add_conditional_edges(
        "coder",
        lambda s: "frontend_check" if s.get("status") == "DONE" else "coder",
        {"frontend_check": "frontend_check", "coder": "coder"}
    )
    graph.add_edge("frontend_check", END)

    graph.set_entry_point("planner")
    return graph.compile()


# Default agent for CLI usage
default_llm = ChatGroq(model="openai/gpt-oss-120b")
agent = build_agent(default_llm)

if __name__ == "__main__":
    result = agent.invoke({"user_prompt": "Build a colourful modern todo app in html css and js"},
                          {"recursion_limit": 100})
    print("Final State:", result)