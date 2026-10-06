"""AgentOps-X SDK: observability for LangGraph agents.

    import agentops
    agentops.init()                      # reads AGENTOPS_ENDPOINT / AGENTOPS_API_KEY
    with agentops.run("my-agent", input=q, prompt_version=("v2", PROMPT)) as run:
        result = graph.invoke(state, config={"callbacks": [run.callback]})
        run.mark_success(is_correct(result))
"""
from agentops.tracer import Run, flush, init, run

__all__ = ["init", "run", "flush", "Run"]
__version__ = "0.1.0"
