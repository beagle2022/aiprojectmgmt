"""
generate_dashboard.py — Render project data from data/ltm.json into a
standalone, shareable HTML dashboard.

USAGE:
    cd D:\\AI-CapstoneProjects
    python generate_dashboard.py

    # custom paths:
    python generate_dashboard.py --ltm data/ltm.json --out dashboard.html

This reads whatever is actually in your long-term memory file and renders
it — no fabricated data. If a category is empty, that section is omitted
from the dashboard rather than filled with placeholders.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone


def load_ltm(path: str) -> dict:
    if not os.path.exists(path):
        print(f"[Error] LTM file not found: {path}")
        print("Run 'python data/seed.py' or use the copilot first to create it.")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Lightweight parsers that extract structure from free-text LTM entries ──

TICKET_RE = re.compile(
    r"(?P<id>[A-Z]+-\d+)\s+(?P<title>.+?)\s*[—\-]\s*"
    r"(?P<pts>\d+)\s*pts?\s*[—\-]\s*(?P<owner>[\w ]+?)\s*[—\-]\s*"
    r"(?P<priority>High|Medium|Low)\s*[—\-]\s*(?P<status>[\w ]+?)\.?$",
    re.IGNORECASE,
)

RISK_RE = re.compile(r"Risk:\s*(?P<text>.+?)\.\s*Impact:\s*(?P<impact>HIGH|MEDIUM|LOW)", re.IGNORECASE)

DECISION_RE = re.compile(r"Decision:\s*(?P<text>.+?)\.\s*Rationale:\s*(?P<rationale>.+?)\.", re.IGNORECASE)

TEAM_RE = re.compile(r"^(?P<name>[\w]+(?: [\w]+)?)\s*[—\-]\s*(?P<role>.+?)\.", re.IGNORECASE)


def parse_tickets(signals: list) -> list:
    tickets = []
    for entry in signals:
        text = entry.get("content", "")
        m = TICKET_RE.search(text)
        if m:
            tickets.append({
                "id": m["id"],
                "title": m["title"].strip(),
                "pts": int(m["pts"]),
                "owner": m["owner"].strip(),
                "priority": m["priority"].capitalize(),
                "status": m["status"].strip().title(),
            })
    return tickets


def parse_risks(signals: list) -> list:
    risks = []
    for entry in signals:
        text = entry.get("content", "")
        m = RISK_RE.search(text)
        if m:
            risks.append({"text": m["text"].strip(), "impact": m["impact"].upper()})
    return risks


def parse_decisions(decisions: list) -> list:
    out = []
    for entry in decisions:
        text = entry.get("content", "")
        m = DECISION_RE.search(text)
        if m:
            out.append({"text": m["text"].strip(), "rationale": m["rationale"].strip(),
                        "ts": entry.get("timestamp", "")})
        else:
            out.append({"text": text.strip(), "rationale": "", "ts": entry.get("timestamp", "")})
    return out


def parse_team(team: list) -> list:
    out = []
    for entry in team:
        text = entry.get("content", "")
        m = TEAM_RE.search(text)
        if m:
            out.append({"name": m["name"].strip(), "role": m["role"].strip()})
    return out


def parse_project_facts(project: list) -> list:
    return [e.get("content", "").strip() for e in project if e.get("content")]


# ── HTML rendering ──────────────────────────────────────────────────────────

def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


STATUS_CLASS = {
    "done": "st-done", "in progress": "st-prog", "to do": "st-todo",
    "blocked": "st-blocked", "review": "st-review",
}
PRIORITY_CLASS = {"high": "pr-high", "medium": "pr-med", "low": "pr-low"}
IMPACT_CLASS = {"HIGH": "ri-high", "MEDIUM": "ri-med", "LOW": "ri-low"}


def render_tickets_rows(tickets: list) -> str:
    if not tickets:
        return '<tr><td colspan="6" class="empty-row">No tickets found in signals memory.</td></tr>'
    rows = []
    for t in tickets:
        st_key = t["status"].lower()
        st_cls = STATUS_CLASS.get(st_key, "st-todo")
        pr_cls = PRIORITY_CLASS.get(t["priority"].lower(), "pr-med")
        rows.append(
            "<tr>"
            f'<td class="mono">{esc(t["id"])}</td>'
            f'<td>{esc(t["title"])}</td>'
            f'<td>{esc(t["owner"])}</td>'
            f'<td><span class="status-pill {st_cls}">{esc(t["status"])}</span></td>'
            f'<td><span class="pri-pill {pr_cls}">{esc(t["priority"])}</span></td>'
            f'<td class="mono num">{t["pts"]}</td>'
            "</tr>"
        )
    return "\n".join(rows)


def render_risk_rows(risks: list) -> str:
    if not risks:
        return '<div class="empty-row">No risks recorded in signals memory.</div>'
    rows = []
    for r in risks:
        cls = IMPACT_CLASS.get(r["impact"], "ri-med")
        rows.append(
            '<div class="risk-row">'
            f'<span class="risk-dot {cls}"></span>'
            f'<span class="risk-text">{esc(r["text"])}</span>'
            f'<span class="risk-impact {cls}">{esc(r["impact"])}</span>'
            "</div>"
        )
    return "\n".join(rows)


def render_decision_rows(decisions: list) -> str:
    if not decisions:
        return '<div class="empty-row">No decisions recorded.</div>'
    rows = []
    for d in decisions[-8:][::-1]:
        date = d["ts"][:10] if d["ts"] else ""
        rationale = f'<div class="decision-rationale">{esc(d["rationale"])}</div>' if d["rationale"] else ""
        rows.append(
            '<div class="decision-row">'
            f'<div class="decision-date mono">{esc(date)}</div>'
            f'<div><div class="decision-text">{esc(d["text"])}</div>{rationale}</div>'
            "</div>"
        )
    return "\n".join(rows)


def render_team_rows(team: list) -> str:
    if not team:
        return '<div class="empty-row">No team members recorded.</div>'
    colors = ["#5B7A99", "#3F6B3F", "#B68A2E", "#A6593C", "#7A5B99", "#3F8B8B"]
    rows = []
    for i, m in enumerate(team):
        initials = "".join(w[0] for w in m["name"].split()[:2]).upper()
        color = colors[i % len(colors)]
        rows.append(
            '<div class="team-row">'
            f'<div class="avatar" style="background:{color}22;color:{color};border-color:{color}55">{esc(initials)}</div>'
            f'<div><div class="team-name">{esc(m["name"])}</div><div class="team-role">{esc(m["role"])}</div></div>'
            "</div>"
        )
    return "\n".join(rows)


def render_project_facts(facts: list) -> str:
    if not facts:
        return '<div class="empty-row">No project facts recorded.</div>'
    rows = []
    for f in facts[:10]:
        rows.append(f'<div class="fact-row"><span class="fact-bullet">&rsaquo;</span>{esc(f)}</div>')
    return "\n".join(rows)


def compute_metrics(tickets: list) -> dict:
    total = len(tickets)
    done = sum(1 for t in tickets if t["status"].lower() == "done")
    blocked = sum(1 for t in tickets if t["status"].lower() == "blocked")
    total_pts = sum(t["pts"] for t in tickets)
    done_pts = sum(t["pts"] for t in tickets if t["status"].lower() == "done")
    return {"total": total, "done": done, "blocked": blocked,
            "total_pts": total_pts, "done_pts": done_pts,
            "pct": round((done_pts / total_pts) * 100) if total_pts else 0}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sprint Dashboard — Generated from LTM</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:        #1B2430;
  --bg2:       #212C3A;
  --paper:     #F7F5F0;
  --ink:       #2A2A28;
  --ink-muted: #6B6B66;
  --border:    #D8D4C8;
  --border-dk: #3A4658;
  --steel:     #5B7A99;
  --moss:      #3F6B3F;
  --ochre:     #B68A2E;
  --clay:      #A6593C;
  --cream:     #F7F5F0;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--cream);
  font-family: 'Inter', sans-serif;
  font-size: 14px;
  line-height: 1.6;
  padding: 32px 24px 64px;
}}
.mono {{ font-family: 'IBM Plex Mono', monospace; }}
.wrap {{ max-width: 1080px; margin: 0 auto; }}
.masthead {{
  display: flex; justify-content: space-between; align-items: flex-end;
  border-bottom: 2px solid var(--border-dk);
  padding-bottom: 18px; margin-bottom: 6px;
}}
.masthead h1 {{
  font-family: 'Source Serif 4', serif; font-weight: 700; font-size: 30px;
  letter-spacing: -0.3px; color: var(--cream);
}}
.masthead .sub {{ font-size: 12.5px; color: #9FB0C2; margin-top: 4px; }}
.freshness {{
  font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #7E92A8;
  text-align: right; line-height: 1.7;
}}
.freshness .dot {{ display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--moss); margin-right:6px; }}
.metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
  background: var(--border-dk); margin: 24px 0; border: 1px solid var(--border-dk); }}
.metric {{ background: var(--bg); padding: 16px 18px; }}
.metric-label {{ font-size: 11px; color: #8294A8; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }}
.metric-value {{ font-family: 'Source Serif 4', serif; font-size: 28px; font-weight: 600; color: var(--cream); }}
.metric-value.moss {{ color: #8FBF8F; }}
.metric-value.clay {{ color: #D88F77; }}
.metric-value.ochre {{ color: #D9B05C; }}
.progress-block {{ background: var(--bg2); border: 1px solid var(--border-dk); padding: 14px 18px; margin-bottom: 28px; }}
.progress-label {{ display: flex; justify-content: space-between; font-size: 12px; color: #9FB0C2; margin-bottom: 8px; }}
.progress-track {{ height: 6px; background: #2A3648; overflow: hidden; }}
.progress-fill {{ height: 100%; background: var(--moss); }}
.card {{ background: var(--paper); color: var(--ink); border-radius: 2px; padding: 22px 24px; margin-bottom: 20px; }}
.card-title {{
  font-family: 'Source Serif 4', serif; font-weight: 700; font-size: 16px;
  color: var(--ink); margin-bottom: 14px; display: flex; align-items: baseline; gap: 8px;
}}
.card-title .count {{ font-family:'IBM Plex Mono',monospace; font-size: 11px; color: var(--ink-muted); font-weight: 400; margin-left: 2px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
thead th {{
  text-align: left; font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--ink-muted); font-weight: 600; padding: 0 8px 8px; border-bottom: 1px solid var(--border);
}}
tbody td {{ padding: 9px 8px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
tbody tr:last-child td {{ border-bottom: none; }}
td.num {{ text-align: right; }}
.status-pill, .pri-pill {{
  display: inline-block; font-size: 10.5px; font-weight: 600; padding: 2px 8px;
  border-radius: 2px; letter-spacing: .02em;
}}
.st-done    {{ background: #E3EEDD; color: var(--moss); }}
.st-prog    {{ background: #E2EBF2; color: var(--steel); }}
.st-todo    {{ background: #EDEAE2; color: var(--ink-muted); }}
.st-blocked {{ background: #F4E2DB; color: var(--clay); }}
.st-review  {{ background: #F4EAD3; color: var(--ochre); }}
.pr-high {{ background: #F4E2DB; color: var(--clay); }}
.pr-med  {{ background: #F4EAD3; color: var(--ochre); }}
.pr-low  {{ background: #E3EEDD; color: var(--moss); }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
.risk-row {{ display: flex; align-items: baseline; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px; }}
.risk-row:last-child {{ border-bottom: none; }}
.risk-dot {{ width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }}
.risk-dot.ri-high {{ background: var(--clay); }}
.risk-dot.ri-med  {{ background: var(--ochre); }}
.risk-dot.ri-low  {{ background: var(--moss); }}
.risk-text {{ flex: 1; }}
.risk-impact {{
  font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 600;
  padding: 2px 7px; border-radius: 2px; letter-spacing: .03em;
}}
.risk-impact.ri-high {{ background: #F4E2DB; color: var(--clay); }}
.risk-impact.ri-med  {{ background: #F4EAD3; color: var(--ochre); }}
.risk-impact.ri-low  {{ background: #E3EEDD; color: var(--moss); }}
.decision-row {{ display: grid; grid-template-columns: 78px 1fr; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); }}
.decision-row:last-child {{ border-bottom: none; }}
.decision-date {{ font-size: 11px; color: var(--ink-muted); padding-top: 2px; }}
.decision-text {{ font-size: 13px; color: var(--ink); }}
.decision-rationale {{ font-size: 12px; color: var(--ink-muted); margin-top: 3px; font-style: italic; }}
.team-row {{ display: flex; align-items: center; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--border); }}
.team-row:last-child {{ border-bottom: none; }}
.avatar {{ width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center;
  font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; border: 1px solid; flex-shrink: 0; }}
.team-name {{ font-size: 13px; color: var(--ink); font-weight: 500; }}
.team-role {{ font-size: 11.5px; color: var(--ink-muted); }}
.fact-row {{ font-size: 13px; color: var(--ink); padding: 7px 0; border-bottom: 1px solid var(--border); }}
.fact-row:last-child {{ border-bottom: none; }}
.fact-bullet {{ color: var(--steel); margin-right: 8px; font-weight: 600; }}
.empty-row {{ font-size: 12.5px; color: var(--ink-muted); font-style: italic; padding: 12px 0; }}
footer {{ text-align: center; font-size: 11px; color: #5E7088; margin-top: 36px; }}
@media (max-width: 720px) {{
  .metrics {{ grid-template-columns: repeat(2, 1fr); }}
  .cols {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="masthead">
    <div>
      <h1>Sprint Dashboard</h1>
      <div class="sub">Rendered from AI PM Copilot long-term memory</div>
    </div>
    <div class="freshness">
      <div><span class="dot"></span>Source: {ltm_path}</div>
      <div>Generated: {generated_at}</div>
    </div>
  </div>
  <div class="metrics">
    <div class="metric"><div class="metric-label">Total tickets</div><div class="metric-value">{m_total}</div></div>
    <div class="metric"><div class="metric-label">Completed</div><div class="metric-value moss">{m_done}</div></div>
    <div class="metric"><div class="metric-label">Blocked</div><div class="metric-value clay">{m_blocked}</div></div>
    <div class="metric"><div class="metric-label">Story points</div><div class="metric-value ochre">{m_done_pts} / {m_total_pts}</div></div>
  </div>
  <div class="progress-block">
    <div class="progress-label"><span>Points delivered</span><span>{m_pct}%</span></div>
    <div class="progress-track"><div class="progress-fill" style="width:{m_pct}%"></div></div>
  </div>
  <div class="card">
    <div class="card-title">Backlog tickets <span class="count">{ticket_count} from signals memory</span></div>
    <table>
      <thead><tr><th>ID</th><th>Summary</th><th>Owner</th><th>Status</th><th>Priority</th><th style="text-align:right">Pts</th></tr></thead>
      <tbody>
        {tickets_html}
      </tbody>
    </table>
  </div>
  <div class="cols">
    <div class="card">
      <div class="card-title">Risk register <span class="count">{risk_count}</span></div>
      {risks_html}
    </div>
    <div class="card">
      <div class="card-title">Team <span class="count">{team_count}</span></div>
      {team_html}
    </div>
  </div>
  <div class="cols">
    <div class="card">
      <div class="card-title">Recent decisions <span class="count">{decision_count}</span></div>
      {decisions_html}
    </div>
    <div class="card">
      <div class="card-title">Project facts <span class="count">{fact_count}</span></div>
      {facts_html}
    </div>
  </div>
  <footer>Generated by generate_dashboard.py &middot; Data reflects only what is stored in long-term memory at generation time</footer>
</div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Render LTM data into an HTML dashboard")
    parser.add_argument("--ltm", default="data/ltm.json", help="Path to ltm.json")
    parser.add_argument("--out", default="dashboard.html", help="Output HTML file path")
    args = parser.parse_args()

    ltm = load_ltm(args.ltm)

    tickets = parse_tickets(ltm.get("signals", []))
    risks = parse_risks(ltm.get("signals", []))
    decisions = parse_decisions(ltm.get("decisions", []))
    team = parse_team(ltm.get("team", []))
    facts = parse_project_facts(ltm.get("project", []))
    metrics = compute_metrics(tickets)

    html = HTML_TEMPLATE.format(
        ltm_path=esc(args.ltm),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        m_total=metrics["total"], m_done=metrics["done"], m_blocked=metrics["blocked"],
        m_done_pts=metrics["done_pts"], m_total_pts=metrics["total_pts"], m_pct=metrics["pct"],
        ticket_count=len(tickets), risk_count=len(risks),
        team_count=len(team), decision_count=len(decisions), fact_count=len(facts),
        tickets_html=render_tickets_rows(tickets),
        risks_html=render_risk_rows(risks),
        team_html=render_team_rows(team),
        decisions_html=render_decision_rows(decisions),
        facts_html=render_project_facts(facts),
    )

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDashboard generated: {args.out}")
    print(f"  Parsed: {len(tickets)} tickets, {len(risks)} risks, "
          f"{len(team)} team members, {len(decisions)} decisions, {len(facts)} project facts")
    print(f"  Open {args.out} in any browser to view.\n")


if __name__ == "__main__":
    main()
