"""The LangGraph state machine that drives the travel agent.

Compared to the original `agents/agent.py`, this version:
- Takes its LLM, tools, and EmailService as constructor arguments (dependency
  injection) instead of constructing a global ChatOpenAI client inline. That's
  what makes the graph unit-testable with a fake LLM and a fake email service.
- Uses Groq instead of OpenAI for the LLM calls (see agent_factory.py).
- Caps the number of tool-calling round-trips per query (`max_iterations`), so
  a confused model can't loop indefinitely and rack up API calls.
- Raises/handles errors from the email step instead of only printing them.
"""

from __future__ import annotations

import logging
import operator
from typing import Annotated, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from travel_agent.agents.prompts import EMAILS_SYSTEM_PROMPT, TOOLS_SYSTEM_PROMPT
from travel_agent.services import EmailDeliveryError, EmailService

logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    tool_call_count: int
    # Populated only when the human-in-the-loop email step is going to run.
    from_email: str
    to_email: str
    subject: str


class TravelAgent:
    def __init__(
        self,
        llm: BaseChatModel,
        tools: list,
        email_service: EmailService,
        max_iterations: int = 6,
    ) -> None:
        self._tools = {t.name: t for t in tools}
        self._tools_llm = llm.bind_tools(tools)
        self._email_llm = llm
        self._email_service = email_service
        self._max_iterations = max_iterations

        builder = StateGraph(AgentState)
        builder.add_node("call_tools_llm", self.call_tools_llm)
        builder.add_node("invoke_tools", self.invoke_tools)
        builder.add_node("email_sender", self.email_sender)
        builder.set_entry_point("call_tools_llm")

        builder.add_conditional_edges(
            "call_tools_llm",
            self._route_after_llm,
            {"more_tools": "invoke_tools", "email_sender": "email_sender"},
        )
        builder.add_edge("invoke_tools", "call_tools_llm")
        builder.add_edge("email_sender", END)

        memory = MemorySaver()
        self.graph = builder.compile(checkpointer=memory, interrupt_before=["email_sender"])

    def _route_after_llm(self, state: AgentState) -> str:
        last_message = state["messages"][-1]
        has_tool_calls = bool(getattr(last_message, "tool_calls", None))
        if not has_tool_calls:
            return "email_sender"
        if state.get("tool_call_count", 0) >= self._max_iterations:
            logger.warning("Hit max_iterations=%s tool-call rounds; forcing a final answer.", self._max_iterations)
            return "email_sender"
        return "more_tools"

    def call_tools_llm(self, state: AgentState) -> dict:
        messages = [SystemMessage(content=TOOLS_SYSTEM_PROMPT)] + state["messages"]
        response = self._tools_llm.invoke(messages)
        return {"messages": [response]}

    def invoke_tools(self, state: AgentState) -> dict:
        tool_calls = state["messages"][-1].tool_calls
        results = []
        for call in tool_calls:
            logger.info("Calling tool: %s(%s)", call["name"], call["args"])
            if call["name"] not in self._tools:
                content = f"Unknown tool '{call['name']}'. Available tools: {list(self._tools)}"
            else:
                try:
                    content = str(self._tools[call["name"]].invoke(call["args"]))
                except Exception as exc:  # a tool bug shouldn't crash the whole agent run
                    logger.exception("Tool %s raised an exception", call["name"])
                    content = f"Tool '{call['name']}' failed: {exc}"
            results.append(ToolMessage(tool_call_id=call["id"], name=call["name"], content=content))
        return {"messages": results, "tool_call_count": state.get("tool_call_count", 0) + 1}

    def email_sender(self, state: AgentState) -> dict:
        email_message = [SystemMessage(content=EMAILS_SYSTEM_PROMPT), HumanMessage(content=state["messages"][-1].content)]
        email_response = self._email_llm.invoke(email_message)

        from_email = state.get("from_email")  # type: ignore[typeddict-item]
        to_email = state.get("to_email")  # type: ignore[typeddict-item]
        subject = state.get("subject")  # type: ignore[typeddict-item]
        if not (from_email and to_email and subject):
            logger.info("Email step reached without recipient details; skipping send.")
            return {}

        try:
            self._email_service.send_html_email(
                from_email=from_email, to_email=to_email, subject=subject, html_content=email_response.content
            )
        except EmailDeliveryError:
            logger.exception("Failed to send travel itinerary email")
            raise
        return {}
