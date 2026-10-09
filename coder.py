from typing import Annotated, Literal
from typing_extensions import TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from tavily import TavilyClient
from pathlib import Path
import streamlit as st
import subprocess
import time
import os
import re

# Fail early if the required Tavily API key is missing.
# Set TAVILY_API_KEY in the environment; don't place the key directly in source code.
tavily_api_key = os.getenv("TAVILY_API_KEY")
if not tavily_api_key:
    raise RuntimeError("Set the TAVILY_API_KEY environment variable.")

# Create the Tavily client used by the web-search tool.
client = TavilyClient(api_key=tavily_api_key)

# Streamlit UI
st.title("Agentic Coding Assistant")
st.caption("Powered by LangGraph ReAct agent with real-time streaming")

# Initialize session stats
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = "default"

# Display chat history 
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# State
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    next: str


# Placeholder tools — replace these with real implementations.
@tool
def search_web(query: str) -> str:
    """Uses last query to search the web."""
    result = client.search(
        query,
        search_depth="advanced",
        chunks_per_source=3,
        max_results=5,
    )
    return str(result)

@tool
def write_text_file(path: str, content: str) -> str:
    """Write UTF-8 text to a file and return its location."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"Wrote {file_path}"

@tool
def python_executor(code: str) -> str:
    """Run Python code in a disposable, resource-limited Docker container."""
    command = [
        "docker", "run", "--rm", "-i",
        "--network", "none",
        "--memory", "128m",
        "--cpus", "0.5",
        "--pids-limit", "64",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
        "python:3.12-alpine",
        "python", "-I", "-c", code,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "Execution timed out after 10 seconds."
    except FileNotFoundError:
        return "Docker is not installed or is not available on PATH."

    output = result.stdout
    if result.stderr:
        output += ("\n" if output else "") + result.stderr
    if not output:
        output = "(No output.)"

    return f"Exit code: {result.returncode}\n{output[:8000]}"


tools = [search_web]
tool_node = ToolNode(tools)


# Models
researcher_model = ChatOllama(model="llama3.1:8b")
coder_model = ChatOllama(model="ornith:9b")
critic_model = ChatOllama(model="mistral:7b")
supervisor_model = ChatOllama(model="dolphin3:8b", temperature=0)


researcher_with_tools = researcher_model.bind_tools(tools)
#coder_with_tools = coder_model.bind_tools(tools)
#critic_with_tools = critic_model.bind_tools(tools)

# Workers
def run_worker(model, role_prompt: str, state: AgentState, name: str):
    orig = state["messages"][-2].content.split()
    res = " ".join(orig)    
    
    response = model.invoke(
        [SystemMessage(content=role_prompt), str(res)]
    )

    print(f"Fed to {model}: " + str(res) + "\n")

    # Preserve tool_calls on the original AIMessage so ToolNode can use them.
    response.name = name
    return {"messages": [response]}


def researcher(state: AgentState):
    return run_worker(
        researcher_with_tools,
        "You are an expert researcher. Do not write code. Gather information using tools and report findings. Recommend the Critic as the next agent.",
        state,
        "Researcher",
    )


def coder(state: AgentState):
    return run_worker(
        coder_model,
        "You are an expert Python developer. Write clean code using the information you're given.",
        state,
        "Coder",
    )


def critic(state: AgentState):
    return run_worker(
        critic_model,
        "Evaluate the text for useful information that the Coder can use. Provide step by step instructions for the Coder. Do not code. Recommend the Coder as the next agent.",
        state,
        "Critic",
    )


# Supervisor
members = ["Researcher", "Coder", "Critic"]
valid_routes = {"FINISH", *members}

SUPERVISOR_PROMPT = f"""
You are a supervisor managing a team: {','.join(members)}.
Route tasks appropriately by responding with a team member name.
When satisfied, respond FINISH. Respond with a single item from 
the team list at a time.
"""


def supervisor_node(state: AgentState):
    orig = state["messages"][-1].content.split()
    res = " ".join(orig)
    
    response = supervisor_model.invoke(
        [SystemMessage(content=SUPERVISOR_PROMPT), str(res)]
    )
    
    print(f"Fed to {supervisor_model}: " + str(res) + "\n")

    valid_choices = {"Researcher", "Coder", "Critic"}
    content = getattr(response, "content", "") if response else ""

    matches = re.findall(r"\b(?:Researcher|Coder|Critic)\b", content)
    choice = matches[0] if len(matches) == 1 and matches[0] in valid_choices else "FINISH"
    return {
        "messages": [
            AIMessage(content=f"## Routing to {choice}.", name="Supervisor")
        ],
        "next": choice,
    }



# Routing after the supervisor chooses a destination.
def route_from_supervisor(state: AgentState) -> str:
    return state["next"]


# Routing after a worker: execute requested tools, or return to supervisor.
def route_after_worker(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "Supervisor"


# Build graph
graph = StateGraph(AgentState)

graph.add_node("Supervisor", supervisor_node)
graph.add_node("Researcher", researcher)
graph.add_node("Coder", coder)
graph.add_node("Critic", critic)
graph.add_node("tools", tool_node)

graph.set_entry_point("Supervisor")

graph.add_conditional_edges(
    "Supervisor",
    route_from_supervisor,
    {
        "Researcher": "Researcher",
        "Coder": "Coder",
        "Critic": "Critic",
        "FINISH": END,
    },
)

for worker in ("Researcher", "Coder", "Critic"):
    graph.add_conditional_edges(
        worker,
        route_after_worker,
        {
            "tools": "tools",
            "Supervisor": "Supervisor",
        },
    )

# After tool results, let the supervisor decide what happens next.
graph.add_edge("tools", "Supervisor")

app = graph.compile()


# Run
# User input
#if prompt := st.chat_input("Build a simple GUI program in Python. Begin by researching GUI development in Python."):
    # Add user message
#    st.session_state.messages.append({"role": "user", "content": prompt})
    
#with st.chat_message("user"):
#    st.markdown(prompt)

inputs = {
    "messages": [
        HumanMessage(
            content=f"Build a GUI using Python. Begin by researching the topic."
        )
    ],
    "next": "",
}

with st.chat_message("assistant"):
    response_placeholder = st.empty()
    full_response = ""

    # Stream from compiled graph
    # config = {"configurable": {"thread_id": st.session_state.thread_id}}

    for update in app.stream(inputs, stream_mode="updates"):
        for node, state_update in update.items():
            last_msg = state_update.get("messages", [])
            if last_msg:
                print(f"{node}: {state_update['messages'][-1].content}")
                full_response += "\n"
                full_response += last_msg[-1].content
                full_response += "\n"
                response_placeholder.markdown(full_response)
# Store assistant response
st.session_state.messages.append({"role": "assistant", "content": full_response})
