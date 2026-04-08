"""FORGE — Multi-Agent AI Development Automation
Streamlit UI entry point. Run with: streamlit run ui/app.py
"""
from __future__ import annotations

import os
import sys

# Ensure the FORGE root is on the path so all imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from ui.api_client import get_run, start_run, stream_run
from ui.components.agent_output import (
    render_coder_tab,
    render_planner_tab,
    render_pr_tab,
    render_reviewer_tab,
)
from ui.components.chat_panel import render_event
from ui.components.run_status import render_status_bar

st.set_page_config(
    page_title="FORGE",
    page_icon="🚀",
    layout="wide",
)

# ── Session state initialisation ──────────────────────────────────────────────
if "run_id" not in st.session_state:
    st.session_state.run_id = None
if "events" not in st.session_state:
    st.session_state.events = []
if "run_state" not in st.session_state:
    st.session_state.run_state = {}
if "streaming" not in st.session_state:
    st.session_state.streaming = False
if "history" not in st.session_state:
    st.session_state.history = []  # list of {ticket_id, run_id, status, pr_url}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🚀 FORGE")
    st.caption("Multi-Agent AI Dev Automation")
    st.divider()

    ticket_id = st.text_input(
        "Jira Ticket ID",
        placeholder="PROJ-123",
        help="Enter the Jira ticket ID to automate.",
    )

    run_button = st.button(
        "Run FORGE",
        type="primary",
        disabled=not ticket_id or st.session_state.streaming,
        use_container_width=True,
    )

    st.divider()
    st.markdown("**Recent Runs**")
    if not st.session_state.history:
        st.caption("No runs yet.")
    for entry in reversed(st.session_state.history[-10:]):
        icon = "✅" if entry["status"] == "complete" else ("❌" if entry["status"] == "failed" else "🔄")
        label = f"{icon} {entry['ticket_id']}"
        if st.button(label, key=f"hist_{entry['run_id']}", use_container_width=True):
            st.session_state.run_id = entry["run_id"]
            st.session_state.streaming = False
            st.rerun()

# ── Start run ─────────────────────────────────────────────────────────────────
if run_button and ticket_id:
    try:
        result = start_run(ticket_id)
        st.session_state.run_id = result["run_id"]
        st.session_state.events = []
        st.session_state.run_state = {}
        st.session_state.streaming = True
        st.session_state.history.append({
            "ticket_id": ticket_id,
            "run_id": result["run_id"],
            "status": "pending",
            "pr_url": None,
        })
        st.rerun()
    except Exception as exc:
        st.error(f"Failed to start run: {exc}")

# ── Main area ─────────────────────────────────────────────────────────────────
st.title("🚀 FORGE")

if not st.session_state.run_id:
    st.markdown(
        "Enter a Jira ticket ID in the sidebar and click **Run FORGE** to start the pipeline."
    )
    st.markdown("""
    **Pipeline:** Jira Ticket → 🧠 Planner → 👨‍💻 Coder → 🔍 Reviewer → 🔀 Pull Request

    Each agent outputs structured results you can inspect in the tabs below.
    """)
    st.stop()

run_id = st.session_state.run_id

# ── Status bar ────────────────────────────────────────────────────────────────
run_state = st.session_state.run_state
current_status = run_state.get("status", "pending")
iteration = run_state.get("iteration", 1)
render_status_bar(current_status, iteration)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_feed, tab_planner, tab_coder, tab_reviewer, tab_pr = st.tabs(
    ["📡 Live Feed", "🧠 Planner", "👨‍💻 Coder", "🔍 Reviewer", "🔀 PR"]
)

with tab_feed:
    feed_container = st.container()

with tab_planner:
    planner_container = st.container()

with tab_coder:
    coder_container = st.container()

with tab_reviewer:
    reviewer_container = st.container()

with tab_pr:
    pr_container = st.container()

# ── Streaming loop ────────────────────────────────────────────────────────────
if st.session_state.streaming:
    try:
        for event in stream_run(run_id):
            st.session_state.events.append(event)

            # Update run state from events
            if event.get("status"):
                st.session_state.run_state["status"] = event["status"]
            if event.get("iteration"):
                st.session_state.run_state["iteration"] = event["iteration"]

            event_type = event.get("event_type", "")
            agent = event.get("agent", "")
            payload = event.get("payload") or {}

            if event_type == "agent_complete":
                if agent == "planner":
                    st.session_state.run_state["planner_output"] = payload
                elif agent == "coder":
                    st.session_state.run_state["coder_output"] = payload
                elif agent == "reviewer":
                    st.session_state.run_state["reviewer_output"] = payload

            if event_type == "run_complete":
                st.session_state.run_state["pr_url"] = payload.get("pr_url")
                st.session_state.run_state["branch_name"] = payload.get("branch_name")
                st.session_state.run_state["status"] = "complete"
                # Update history
                for entry in st.session_state.history:
                    if entry["run_id"] == run_id:
                        entry["status"] = "complete"
                        entry["pr_url"] = payload.get("pr_url")
                st.session_state.streaming = False

            if event_type in ("error", "stream_end"):
                if event_type == "error":
                    st.session_state.run_state["status"] = "failed"
                    for entry in st.session_state.history:
                        if entry["run_id"] == run_id:
                            entry["status"] = "failed"
                st.session_state.streaming = False

            st.rerun()

    except Exception as exc:
        st.error(f"Stream error: {exc}")
        st.session_state.streaming = False

# ── Render current state ──────────────────────────────────────────────────────
with feed_container:
    if not st.session_state.events:
        st.info("Waiting for events...")
    for event in st.session_state.events:
        if event.get("event_type") != "stream_end":
            render_event(event)

with planner_container:
    render_planner_tab(st.session_state.run_state.get("planner_output") or {})

with coder_container:
    render_coder_tab(
        st.session_state.run_state.get("coder_output") or {},
        iteration=st.session_state.run_state.get("iteration", 1),
    )

with reviewer_container:
    render_reviewer_tab(
        st.session_state.run_state.get("reviewer_output") or {},
        iteration=st.session_state.run_state.get("iteration", 1),
    )

with pr_container:
    render_pr_tab(
        st.session_state.run_state.get("reviewer_output") or {},
        pr_url=st.session_state.run_state.get("pr_url"),
        branch_name=st.session_state.run_state.get("branch_name"),
    )
