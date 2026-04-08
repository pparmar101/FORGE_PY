from __future__ import annotations

import streamlit as st

STEPS = [
    ("fetching_ticket", "Fetch Ticket"),
    ("planning", "Plan"),
    ("coding", "Code"),
    ("reviewing", "Review"),
    ("applying", "Apply"),
    ("creating_pr", "Create PR"),
    ("complete", "Done"),
]

STATUS_COLORS = {
    "pending": "gray",
    "fetching_ticket": "blue",
    "planning": "blue",
    "coding": "orange",
    "reviewing": "violet",
    "applying": "green",
    "creating_pr": "green",
    "complete": "green",
    "failed": "red",
}

STATUS_ICONS = {
    "pending": "⏳",
    "fetching_ticket": "🔍",
    "planning": "🧠",
    "coding": "👨‍💻",
    "reviewing": "🔍",
    "applying": "⚙️",
    "creating_pr": "🔀",
    "complete": "✅",
    "failed": "❌",
}


def render_status_bar(current_status: str, iteration: int = 1) -> None:
    step_keys = [s[0] for s in STEPS]
    current_idx = step_keys.index(current_status) if current_status in step_keys else -1
    progress = (current_idx + 1) / len(STEPS) if current_idx >= 0 else 0

    icon = STATUS_ICONS.get(current_status, "⏳")
    color = STATUS_COLORS.get(current_status, "gray")
    label = dict(STEPS).get(current_status, current_status.replace("_", " ").title())

    col1, col2 = st.columns([3, 1])
    with col1:
        st.progress(progress)
    with col2:
        st.markdown(f":{color}[{icon} {label}]")

    if iteration > 1:
        st.caption(f"Coder iteration {iteration} (reviewer requested changes)")

    # Step pills
    pills = []
    for idx, (key, name) in enumerate(STEPS):
        if idx < current_idx:
            pills.append(f"~~{name}~~ ✓")
        elif idx == current_idx:
            pills.append(f"**{name}**")
        else:
            pills.append(name)
    st.caption(" → ".join(pills))
