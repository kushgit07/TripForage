from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from travel_agent.agents.graph import TravelAgent
from travel_agent.services import SearchCache
from travel_agent.tools.flights import build_flights_tool


class FakeChatModel:
    """Minimal stand-in for a LangChain chat model: bind_tools() then a queue of canned invoke() responses."""

    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return self._responses.pop(0)


class FakeDuffelClient:
    def post(self, path, json_body, params=None):
        return {"data": {"offers": []}}  # "no flights found" branch — content doesn't matter for this test


def _build_agent(tools_llm_responses, email_llm_response, email_service=None):
    flights_tool = build_flights_tool(FakeDuffelClient(), SearchCache(ttl_seconds=60))
    llm = FakeChatModel(tools_llm_responses + [email_llm_response])
    return TravelAgent(llm=llm, tools=[flights_tool], email_service=email_service or MagicMock(), max_iterations=6)


def test_agent_calls_tool_then_answers_then_pauses_before_email():
    tool_call_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "flights_finder",
                "args": {"params": {"departure_airport": "MAD", "arrival_airport": "JFK", "outbound_date": "2026-10-01"}},
                "id": "call_1",
            }
        ],
    )
    final_answer = AIMessage(content="No flights found for those dates.", tool_calls=[])
    email_html = AIMessage(content="<html>irrelevant</html>", tool_calls=[])

    agent = _build_agent([tool_call_response, final_answer], email_html)
    config = {"configurable": {"thread_id": "test-thread"}}

    result = agent.graph.invoke({"messages": [HumanMessage(content="flights MAD to JFK Oct 1")]}, config=config)

    # graph paused before email_sender (interrupt_before) — the final tool-loop answer is visible
    assert result["messages"][-1].content == "No flights found for those dates."
    assert result["tool_call_count"] == 1


def test_agent_sends_email_after_resume_when_recipient_details_present():
    final_answer = AIMessage(content="Here is your info.", tool_calls=[])
    email_html = AIMessage(content="<html>trip details</html>", tool_calls=[])
    email_service = MagicMock()

    agent = _build_agent([final_answer], email_html, email_service=email_service)
    config = {"configurable": {"thread_id": "test-thread-2"}}

    agent.graph.invoke({"messages": [HumanMessage(content="flights MAD to JFK Oct 1")]}, config=config)
    agent.graph.update_state(config, {"from_email": "a@x.com", "to_email": "b@x.com", "subject": "Trip"})
    agent.graph.invoke(None, config=config)

    email_service.send_html_email.assert_called_once_with(
        from_email="a@x.com", to_email="b@x.com", subject="Trip", html_content="<html>trip details</html>"
    )


def test_agent_skips_email_when_no_recipient_details():
    final_answer = AIMessage(content="Here is your info.", tool_calls=[])
    email_html = AIMessage(content="<html>trip details</html>", tool_calls=[])
    email_service = MagicMock()

    agent = _build_agent([final_answer], email_html, email_service=email_service)
    config = {"configurable": {"thread_id": "test-thread-3"}}

    agent.graph.invoke({"messages": [HumanMessage(content="flights MAD to JFK Oct 1")]}, config=config)
    agent.graph.invoke(None, config=config)  # resume without ever setting recipient details

    email_service.send_html_email.assert_not_called()
