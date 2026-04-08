from __future__ import annotations

import streamlit as st

AGENT_ICONS = {
    "planner": "🧠",
    "coder": "👨‍💻",
    "reviewer": "🔍",
    "system": "⚙️",
}

EVENT_LABELS = {
    "status_change": "Status",
    "agent_complete": "Complete",
    "error": "Error",
    "run_complete": "Done",
    "stream_end": "Stream ended",
}


def render_event(event: dict) -> None:
    """Render a single RunEvent in the live feed."""
    event_type = event.get("event_type", "")
    agent = event.get("agent", "system")
    icon = AGENT_ICONS.get(agent, "⚙️")
    status = event.get("status", "")
    payload = event.get("payload") or {}
    iteration = event.get("iteration", 1)

    if event_type == "status_change":
        label = status.replace("_", " ").title() if status else "Update"
        iter_tag = f" (iter {iteration})" if iteration > 1 else ""
        st.info(f"{icon} **{label}**{iter_tag}")

    elif event_type == "agent_complete":
        agent_name = agent.title() if agent else "Agent"
        iter_tag = f" — iteration {iteration}" if iteration > 1 else ""
        with st.expander(f"{icon} {agent_name} finished{iter_tag}", expanded=False):
            if agent == "planner" and payload:
                _render_planner_summary(payload)
            elif agent == "coder" and payload:
                _render_coder_summary(payload)
            elif agent == "reviewer" and payload:
                _render_reviewer_summary(payload)
            else:
                st.json(payload)

    elif event_type == "run_complete":
        pr_url = payload.get("pr_url", "")
        branch = payload.get("branch_name", "")
        decision = payload.get("final_decision", "")
        iters = payload.get("iterations", 1)
        st.success(
            f"✅ **Run complete!** Decision: {decision} | Iterations: {iters} | "
            f"Branch: `{branch}`"
        )
        if pr_url:
            st.markdown(f"**[Open Pull Request]({pr_url})**")

    elif event_type == "error":
        error_msg = payload.get("error", "Unknown error")
        st.error(f"❌ **Error:** {error_msg}")


def _render_planner_summary(payload: dict) -> None:
    dev = payload.get("developer_notes", {})
    steps = dev.get("step_by_step_plan", [])
    files = dev.get("impacted_files", [])

    if steps:
        st.markdown("**Implementation Steps:**")
        for i, step in enumerate(steps, 1):
            st.markdown(f"{i}. {step}")

    if files:
        st.markdown("**Impacted Files:**")
        for f in files:
            st.markdown(f"- `{f.get('path')}` — {f.get('change_type')} ({f.get('reason')})")

    tasks = payload.get("task_breakdown", {}).get("tasks", [])
    if tasks:
        st.markdown(f"**Tasks:** {len(tasks)} tasks identified")


def _render_coder_summary(payload: dict) -> None:
    changes = payload.get("code_changes", [])
    tests = payload.get("tests", [])
    commits = payload.get("commits", [])

    st.markdown(f"**Files changed:** {len(changes)} | **Tests:** {len(tests)} | **Commits:** {len(commits)}")

    for change in changes:
        op = change.get("operation", "modify")
        path = change.get("file_path", "")
        summary = change.get("diff_summary", "")
        op_icon = {"create": "➕", "modify": "✏️", "delete": "🗑️"}.get(op, "✏️")
        st.markdown(f"{op_icon} `{path}` — {summary}")


def _render_reviewer_summary(payload: dict) -> None:
    decision = payload.get("final_decision", "")
    summary = payload.get("summary", "")
    issues = payload.get("review_feedback", [])
    pr = payload.get("pr_details", {})

    decision_color = "green" if decision == "Approve" else "orange"
    st.markdown(f"**Decision:** :{decision_color}[{decision}]")

    if summary:
        st.markdown(summary)

    critical = [i for i in issues if i.get("severity") == "critical"]
    major = [i for i in issues if i.get("severity") == "major"]

    if critical:
        st.markdown(f"🔴 **{len(critical)} critical issue(s)**")
    if major:
        st.markdown(f"🟠 **{len(major)} major issue(s)**")

    if pr.get("title"):
        st.markdown(f"**PR Title:** {pr['title']}")
