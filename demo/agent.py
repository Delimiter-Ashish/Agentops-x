"""Demo LangGraph agent: a finance assistant with tools, retries, and two prompt versions."""
import os

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import RetryPolicy

from demo.tools import TOOLS

AGENT_NAME = "fin-agent"

# Output cap on every LLM call: the fix for the runaway generation AgentOps-X caught
# (one call that generated for 330 s and cost ~100x a normal run). 0 disables it.
MAX_OUTPUT_TOKENS = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "2048")) or None

PROMPTS = {
    "v1": "You are a financial assistant. Use the tools to answer the user's question.",
    "v2": (
        "You are a precise financial assistant.\n"
        "1. Find tickers with lookup_ticker, prices (USD) with get_stock_price, and currency rates with get_fx_rate.\n"
        "2. Never do arithmetic in your head: always use calculator.\n"
        "3. If a tool returns an ERROR, fix your input and call it again.\n"
        "4. Finish with one line exactly like: FINAL: <number> (rounded to 2 decimals, no currency symbol)."
    ),
}


def make_llm(profile=None):
    """profile: None -> settings from .env (LLM_*), "local" -> the self-hosted vLLM server (LOCAL_*)."""
    if profile == "local":
        from langchain_openai import ChatOpenAI
        # Streaming lets the tracer measure time-to-first-token and decode speed.
        return ChatOpenAI(base_url=f"http://127.0.0.1:{os.environ.get('VLLM_PORT', '8001')}/v1",
                          api_key=os.environ.get("VLLM_API_KEY", "local"),
                          model=os.environ.get("LOCAL_MODEL", "Qwen/Qwen2.5-14B-Instruct"),
                          temperature=0.2, timeout=120, max_retries=2, streaming=True, stream_usage=True,
                          max_tokens=MAX_OUTPUT_TOKENS)
    if os.environ.get("DEMO_FAKE_LLM") == "1":
        from demo.fake_llm import FakeFinanceLLM
        return FakeFinanceLLM()
    if os.environ.get("LLM_PROVIDER", "openai") == "google":
        # Native Gemini client: keeps Gemini 3 "thought signatures" across tool-calling turns,
        # which the OpenAI-compatible endpoint path drops (-> HTTP 400).
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=os.environ["LLM_MODEL"], google_api_key=os.environ["LLM_API_KEY"],
                                      timeout=90, max_retries=4, max_output_tokens=MAX_OUTPUT_TOKENS)
    from langchain_openai import ChatOpenAI  # any OpenAI-compatible server: vLLM, OpenAI, ...
    return ChatOpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"],
                      model=os.environ["LLM_MODEL"], temperature=0.2, timeout=90, max_retries=4,
                      max_tokens=MAX_OUTPUT_TOKENS)


def build_graph(llm, system_prompt):
    model = llm.bind_tools(TOOLS)

    def agent(state: MessagesState):
        return {"messages": [model.invoke([SystemMessage(system_prompt)] + state["messages"])]}

    g = StateGraph(MessagesState)
    g.add_node("agent", agent)
    # Infra faults (timeouts) raise inside the tools node; LangGraph re-executes the node -> traced as retries.
    g.add_node("tools", ToolNode(TOOLS, handle_tool_errors=False),
               retry_policy=RetryPolicy(max_attempts=3, initial_interval=0.2, retry_on=TimeoutError))
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", tools_condition)
    g.add_edge("tools", "agent")
    return g.compile()
