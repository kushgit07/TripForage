"""Streamlit front-end. Run with: streamlit run src/travel_agent/ui/streamlit_app.py

Behavioural changes from the original app.py:
- Settings are validated at startup via Settings() — a missing API key now fails
  with one clear message instead of a KeyError deep inside a tool call mid-conversation.
- Errors from the agent/email step are shown to the user with a clear message
  instead of a raw exception, and logged server-side for debugging.
"""

from __future__ import annotations

import logging
import uuid

import streamlit as st
from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from travel_agent.agents import build_agent
from travel_agent.config import get_settings
from travel_agent.logging_config import configure_logging
from travel_agent.services import EmailDeliveryError

logger = logging.getLogger(__name__)


def initialize_agent() -> bool:
    """Returns False (and shows a setup error) if configuration is invalid."""
    if "agent" in st.session_state:
        return True
    try:
        settings = get_settings()
    except ValidationError as exc:
        st.error(
            "Missing or invalid configuration. Copy `.env.example` to `.env` and fill in "
            "your API keys.\n\nDetails:\n```\n" + str(exc) + "\n```"
        )
        return False

    configure_logging(settings.log_level)
    st.session_state.agent = build_agent(settings)
    st.session_state.settings = settings
    return True


def render_custom_css() -> None:
    st.markdown(
        """
        <style>
        .main-title { font-size: 2.5em; color: #333; text-align: center; margin-bottom: 0.5em; font-weight: bold; }
        .sub-title { font-size: 1.2em; color: #333; text-align: left; margin-bottom: 0.5em; }
        .center-container { display: flex; flex-direction: column; align-items: center; width: 100%; }
        .query-container { width: 80%; max-width: 600px; margin: 0 auto; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_ui() -> str:
    st.markdown('<div class="center-container">', unsafe_allow_html=True)
    st.markdown('<div class="main-title">✈️🌍 AI Travel Agent 🏨🗺️</div>', unsafe_allow_html=True)
    st.markdown('<div class="query-container">', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-title">Enter your travel query and get flight and hotel information:</div>',
        unsafe_allow_html=True,
    )
    user_input = st.text_area(
        "Travel Query", height=200, key="query", placeholder="e.g. Flights and 4-star hotels from Madrid to Amsterdam, Oct 1-7"
    )
    st.markdown("</div>", unsafe_allow_html=True)
    try:
        st.sidebar.image("images/ai-travel.png", caption="AI Travel Assistant")
    except Exception:
        pass  # image is cosmetic; don't block the app if it's missing (e.g. in some deploy setups)
    return user_input


def process_query(user_input: str) -> None:
    if not user_input:
        st.error("Please enter a travel query.")
        return

    thread_id = str(uuid.uuid4())
    st.session_state.thread_id = thread_id
    config = {"configurable": {"thread_id": thread_id}}

    with st.spinner("Searching flights and hotels..."):
        try:
            result = st.session_state.agent.graph.invoke({"messages": [HumanMessage(content=user_input)]}, config=config)
        except Exception as exc:
            logger.exception("Agent run failed")
            st.error(f"Something went wrong while processing your request: {exc}")
            return

    st.subheader("Travel Information")
    st.write(result["messages"][-1].content)
    st.session_state.travel_info = result["messages"][-1].content


def render_email_form() -> None:
    send_email_option = st.radio("Do you want to send this information via email?", ("No", "Yes"))
    if send_email_option != "Yes":
        return

    with st.form(key="email_form"):
        sender_email = st.text_input("Sender Email")
        receiver_email = st.text_input("Receiver Email")
        subject = st.text_input("Email Subject", "Your Travel Information")
        submit_button = st.form_submit_button(label="Send Email")

    if not submit_button:
        return
    if not (sender_email and receiver_email and subject):
        st.error("Please fill out all email fields.")
        return

    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    update = {"from_email": sender_email, "to_email": receiver_email, "subject": subject}
    try:
        st.session_state.agent.graph.update_state(config, update)
        st.session_state.agent.graph.invoke(None, config=config)
        st.success("Email sent successfully!")
        for key in ("travel_info", "thread_id"):
            st.session_state.pop(key, None)
    except EmailDeliveryError as exc:
        st.error(f"Could not send email: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error while sending email")
        st.error(f"Unexpected error while sending email: {exc}")


def main() -> None:
    st.set_page_config(page_title="AI Travel Agent", page_icon="✈️")
    if not initialize_agent():
        return
    render_custom_css()
    user_input = render_ui()

    if st.button("Get Travel Information"):
        process_query(user_input)

    if "travel_info" in st.session_state:
        render_email_form()


if __name__ == "__main__":
    main()
