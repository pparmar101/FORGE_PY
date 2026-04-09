from __future__ import annotations

import streamlit as st


def render_ticket_tab(ticket: dict) -> None:
    if not ticket:
        st.info("Jira ticket has not been fetched yet.")
        return

    summary = ticket.get("summary", "")
    ticket_id = ticket.get("ticket_id", "")
    issue_type = ticket.get("issue_type", "")
    priority = ticket.get("priority", "")
    status = ticket.get("status", "")
    assignee = ticket.get("assignee") or "Unassigned"
    labels = ticket.get("labels", [])
    description = ticket.get("description", "")
    comments = ticket.get("comments", [])

    priority_colors = {"Highest": "red", "High": "orange", "Medium": "blue", "Low": "gray", "Lowest": "gray"}
    priority_color = priority_colors.get(priority, "blue")

    st.markdown(f"### 🎫 {ticket_id}")
    st.markdown(f"**{summary}**")
    st.divider()

    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(f"**Type**  \n{issue_type}")
    col2.markdown(f"**Priority**  \n:{priority_color}[{priority}]")
    col3.markdown(f"**Status**  \n{status}")
    col4.markdown(f"**Assignee**  \n{assignee}")

    if labels:
        st.markdown(" ".join(f"`{l}`" for l in labels))

    st.divider()

    if description:
        st.markdown("**Description**")
        st.markdown(description)
        st.divider()

    if comments:
        st.markdown(f"**Comments ({len(comments)})**")
        for i, c in enumerate(comments, 1):
            with st.expander(f"Comment #{i}", expanded=False):
                st.markdown(c)


def render_planner_tab(planner_output: dict) -> None:
    if not planner_output:
        st.info("Planner has not run yet.")
        return

    dev = planner_output.get("developer_notes", {})
    qa = planner_output.get("qa_notes", {})
    tasks = planner_output.get("task_breakdown", {}).get("tasks", [])

    with st.expander("🗺️ Developer Notes", expanded=True):
        steps = dev.get("step_by_step_plan", [])
        if steps:
            st.markdown("**Implementation Plan:**")
            for i, s in enumerate(steps, 1):
                st.markdown(f"{i}. {s}")

        files = dev.get("impacted_files", [])
        if files:
            st.markdown("**Impacted Files:**")
            rows = [
                {"File": f["path"], "Operation": f["change_type"], "Reason": f["reason"]}
                for f in files
            ]
            st.dataframe(rows, use_container_width=True)

        for section, key in [
            ("API Changes", "api_changes"),
            ("DB Changes", "db_changes"),
            ("Edge Cases", "edge_cases"),
            ("Assumptions", "assumptions"),
        ]:
            items = dev.get(key, [])
            if items:
                st.markdown(f"**{section}:**")
                for item in items:
                    st.markdown(f"- {item}")

    with st.expander("🧪 QA Notes"):
        for tc in qa.get("test_cases", []):
            badge = {"positive": "✅", "negative": "❌", "regression": "🔄"}.get(
                tc.get("test_type", ""), "•"
            )
            st.markdown(f"{badge} **{tc.get('description', '')}**")
            for step in tc.get("steps", []):
                st.markdown(f"  - {step}")
            st.caption(f"Expected: {tc.get('expected_result', '')}")
            st.divider()

        reg = qa.get("regression_areas", [])
        if reg:
            st.markdown("**Regression Risk Areas:**")
            for area in reg:
                st.markdown(f"- {area}")

    with st.expander("📋 Task Breakdown"):
        for task in sorted(tasks, key=lambda t: t.get("order", 0)):
            complexity = task.get("estimated_complexity", "medium")
            color = {"low": "green", "medium": "orange", "high": "red"}.get(complexity, "gray")
            st.markdown(
                f"**{task.get('order')}. {task.get('title')}** "
                f":{color}[{complexity.upper()}]"
            )
            st.markdown(task.get("description", ""))
            st.divider()


def render_coder_tab(coder_output: dict, iteration: int = 1) -> None:
    if not coder_output:
        st.info("Coder has not run yet.")
        return

    if iteration > 1:
        st.caption(f"Showing output from iteration {iteration}")

    changes = coder_output.get("code_changes", [])
    tests = coder_output.get("tests", [])
    commits = coder_output.get("commits", [])
    notes = coder_output.get("implementation_notes", "")

    if notes:
        st.info(notes)

    st.markdown(f"**{len(changes)} file(s) changed | {len(tests)} test(s) | {len(commits)} commit(s)**")

    with st.expander("💻 Code Changes", expanded=True):
        for change in changes:
            op = change.get("operation", "modify")
            path = change.get("file_path", "")
            content = change.get("content", "")
            summary = change.get("diff_summary", "")

            op_icon = {"create": "➕", "modify": "✏️", "delete": "🗑️"}.get(op, "✏️")
            st.markdown(f"{op_icon} **`{path}`** — {summary}")
            if content:
                lang = _detect_language(path)
                st.code(content, language=lang)

    with st.expander("🧪 Tests"):
        for test in tests:
            st.markdown(f"**`{test.get('file_path')}`**")
            st.code(test.get("test_content", ""), language="python")

    with st.expander("📝 Commits"):
        for commit in commits:
            st.markdown(f"`{commit.get('message')}`")
            for f in commit.get("files", []):
                st.markdown(f"  - `{f}`")


def render_reviewer_tab(reviewer_output: dict, iteration: int = 1) -> None:
    if not reviewer_output:
        st.info("Reviewer has not run yet.")
        return

    if iteration > 1:
        st.caption(f"Showing review from iteration {iteration}")

    decision = reviewer_output.get("final_decision", "")
    summary = reviewer_output.get("summary", "")
    issues = reviewer_output.get("review_feedback", [])
    risks = reviewer_output.get("risks", [])

    # Decision badge
    if decision == "Approve":
        st.success("✅ APPROVED")
    else:
        st.warning("⚠️ REQUEST CHANGES")

    if summary:
        st.markdown(summary)

    with st.expander("🔍 Review Feedback", expanded=bool(issues)):
        if not issues:
            st.success("No issues found.")
        for issue in sorted(issues, key=lambda i: ["critical", "major", "minor", "suggestion"].index(i.get("severity", "suggestion"))):
            sev = issue.get("severity", "suggestion")
            color = {"critical": "red", "major": "orange", "minor": "blue", "suggestion": "gray"}.get(sev, "gray")
            loc = f" — `{issue.get('file_path')}`" if issue.get("file_path") else ""
            st.markdown(f":{color}[**{sev.upper()}**]{loc}")
            st.markdown(issue.get("description", ""))
            st.caption(f"Fix: {issue.get('suggested_fix', '')}")
            st.divider()

    with st.expander("⚠️ Risks"):
        if not risks:
            st.success("No risks identified.")
        for risk in risks:
            cat = risk.get("category", "")
            st.markdown(f"**{cat.replace('_', ' ').title()}:** {risk.get('description', '')}")
            st.caption(f"Mitigation: {risk.get('mitigation', '')}")


def render_pr_tab(reviewer_output: dict, pr_url: str | None, branch_name: str | None) -> None:
    if not reviewer_output:
        st.info("PR details not yet available.")
        return

    pr = reviewer_output.get("pr_details", {})

    if pr_url:
        st.success(f"✅ PR Created!")
        st.markdown(f"### [{pr.get('title', 'Pull Request')}]({pr_url})")
        if branch_name:
            st.caption(f"Branch: `{branch_name}`")
        st.link_button("Open Pull Request", pr_url)
        st.divider()

    if pr.get("description"):
        st.markdown("**Description:**")
        st.markdown(pr["description"])

    steps = pr.get("testing_steps", [])
    if steps:
        st.markdown("**Testing Steps:**")
        for step in steps:
            st.markdown(f"- {step}")

    risk_notes = pr.get("risks", [])
    if risk_notes:
        st.markdown("**Risks:**")
        for r in risk_notes:
            st.markdown(f"- ⚠️ {r}")


def _detect_language(file_path: str) -> str:
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "tsx": "tsx",
        "jsx": "jsx",
        "java": "java",
        "go": "go",
        "rs": "rust",
        "yaml": "yaml",
        "yml": "yaml",
        "json": "json",
        "sql": "sql",
        "sh": "bash",
        "md": "markdown",
    }.get(ext, "text")
