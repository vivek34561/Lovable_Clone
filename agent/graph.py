import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from .prompt import planner_prompt, architect_prompt, coder_system_prompt
from .states import Plan, TaskPlan, CoderState
from .tools import write_file, read_file, get_current_directory, list_files, init_project_root

# Load environment variables (expects GITHUB_TOKEN for GitHub Models)
load_dotenv()

# Instantiate an LCEL-compatible LLM for LangGraph agents
# Flexible environment resolution for API credentials and base URL.
_model_name = os.environ.get("MODEL_NAME", "gpt-4o")
_base_url = (
    os.environ.get("OPENAI_BASE_URL")
    or os.environ.get("AZURE_OPENAI_BASE_URL")
    or os.environ.get("GITHUB_MODELS_BASE_URL")
    or "https://models.inference.ai.azure.com"
)
_api_key = (
    os.environ.get("GITHUB_TOKEN")
    or os.environ.get("AZURE_OPENAI_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or ""
)

llm = ChatOpenAI(
    model=_model_name,
    base_url=_base_url,
    api_key=_api_key,
    temperature=0.7,
)



def planner_agent(state: dict) -> dict:
    """Converts user prompt into a structured Plan."""
    user_prompt = state["user_prompt"]
    resp = llm.with_structured_output(Plan, method="function_calling").invoke(
        planner_prompt(user_prompt)
    )
    if resp is None:
        raise ValueError("Planner did not return a valid response.")
    return {"plan": resp}


def architect_agent(state: dict) -> dict:
    """Creates TaskPlan from Plan."""
    plan: Plan = state["plan"]
    resp = llm.with_structured_output(TaskPlan, method="function_calling").invoke(
        architect_prompt(plan=plan.model_dump_json())
    )
    if resp is None:
        raise ValueError("Planner did not return a valid response.")

    resp.plan = plan
    print(resp.model_dump_json())
    return {"task_plan": resp}


def coder_agent(state: dict) -> dict:
    """LangGraph tool-using coder agent."""
    # Ensure the project root exists before any read/write operations
    init_project_root()
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

    react_agent.invoke({
        "messages": [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    })

    coder_state.current_step_idx += 1
    return {"coder_state": coder_state}


graph = StateGraph(dict)

graph.add_node("planner", planner_agent)
graph.add_node("architect", architect_agent)
graph.add_node("coder", coder_agent)

graph.add_edge("planner", "architect")
graph.add_edge("architect", "coder")
graph.add_conditional_edges(
    "coder",
    lambda s: "END" if s.get("status") == "DONE" else "coder",
    {"END": END, "coder": "coder"}
)

graph.set_entry_point("planner")
agent = graph.compile()
if __name__ == "__main__":
    result = agent.invoke({"user_prompt": "Build a colourful modern todo app in html css and js"},
                          {"recursion_limit": 100})
    print("Final State:", result)