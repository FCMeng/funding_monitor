from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def render_site(path: Path, state: dict[str, Any], latest_matches: list[dict[str, Any]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    runs = state.get("runs", [])
    opportunities = state.get("opportunities", {})
    fetched_opportunities = state.get("fetched_opportunities", {})
    latest_ids = {item["opportunity"]["stable_id"] for item in latest_matches or []}
    cards = []
    for opp_id, opp in sorted(opportunities.items(), key=lambda item: item[1].get("due_date", "") or "9999"):
        is_new = opp_id in latest_ids
        cards.append(render_card(opp, is_new=is_new))
    if not cards:
        cards.append('<p class="empty">No matched opportunities have been recorded yet.</p>')
    fetched_cards = []
    for opp_id, opp in sorted(fetched_opportunities.items(), key=lambda item: item[1].get("due_date", "") or "9999"):
        fetched_cards.append(render_card(opp, is_new=False, compact=True))
    if not fetched_cards:
        fetched_cards.append('<p class="empty">No fetched opportunities have been recorded yet.</p>')

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Funding Monitor</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #1f2933;
      --muted: #667085;
      --line: #d9e2ec;
      --paper: #f7f9fb;
      --panel: #ffffff;
      --accent: #1f7a8c;
      --accent-2: #7c3aed;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--paper);
    }}
    header {{
      padding: 28px clamp(18px, 4vw, 48px);
      background: #0f172a;
      color: white;
    }}
    h1 {{ margin: 0 0 8px; font-size: clamp(28px, 5vw, 44px); letter-spacing: 0; }}
    header p {{ margin: 0; color: #cbd5e1; max-width: 900px; }}
    main {{
      display: grid;
      grid-template-columns: minmax(220px, 300px) minmax(0, 1fr);
      gap: 24px;
      padding: 24px clamp(18px, 4vw, 48px) 48px;
    }}
    aside, .opportunity {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    aside {{ padding: 18px; align-self: start; position: sticky; top: 16px; }}
    aside h2, section h2 {{ margin: 0 0 12px; font-size: 18px; }}
    .run {{ border-top: 1px solid var(--line); padding: 12px 0; font-size: 14px; }}
    .run:first-of-type {{ border-top: 0; }}
    .list {{ display: grid; gap: 16px; }}
    .opportunity {{ padding: 18px; }}
    .opportunity.compact {{ padding: 14px 16px; }}
    .opportunity h3 {{ margin: 0 0 8px; font-size: 20px; line-height: 1.25; }}
    .opportunity.compact h3 {{ font-size: 17px; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 13px;
      color: var(--muted);
      background: #fbfdff;
    }}
    .new {{ color: white; background: var(--accent); border-color: var(--accent); }}
    .label {{ color: var(--muted); font-size: 13px; text-transform: uppercase; }}
    p {{ line-height: 1.55; }}
    a {{ color: var(--accent); }}
    .empty {{ background: white; border: 1px dashed var(--line); border-radius: 8px; padding: 24px; }}
    .section-note {{ color: var(--muted); margin: 0 0 14px; }}
    section + section {{ margin-top: 28px; }}
    @media (max-width: 780px) {{
      main {{ grid-template-columns: 1fr; }}
      aside {{ position: static; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Funding Monitor</h1>
    <p>Curated opportunities screened for computational materials science, AI4Science, computational biophysics, protein folding, and protein interaction research profiles.</p>
  </header>
  <main>
    <aside>
      <h2>Fetch History</h2>
      {render_runs(runs)}
    </aside>
    <div>
      <section>
        <h2>Matched Opportunities</h2>
        <div class="list">
          {''.join(cards)}
        </div>
      </section>
      <section>
        <h2>Fetched Opportunities</h2>
        <p class="section-note">All opportunities fetched by the monitor, including items that were not selected as profile matches.</p>
        <div class="list">
          {''.join(fetched_cards)}
        </div>
      </section>
    </div>
  </main>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def render_runs(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return '<p class="empty">No fetches yet.</p>'
    return "".join(
        f"""<div class="run">
  <strong>{escape(run.get("fetched_at", "unknown"))}</strong><br>
  fetched {int(run.get("fetched_count", 0))}, matched {int(run.get("matched_count", 0))}, new {int(run.get("new_count", 0))}
</div>"""
        for run in runs[:20]
    )


def render_card(opp: dict[str, Any], *, is_new: bool, compact: bool = False) -> str:
    documents = opp.get("documents") or []
    docs = ", ".join(escape(str(doc)) for doc in documents) if documents else "See source notice/package."
    badge = '<span class="pill new">New this run</span>' if is_new else ""
    screening = opp.get("screening") or {}
    profiles = ", ".join(escape(str(profile)) for profile in screening.get("matched_profiles", [])) or "Not recorded"
    rationale = escape(screening.get("rationale") or "Screening rationale was not recorded for this opportunity.")
    score = escape(str(screening.get("fit_score", "Not recorded")))
    class_name = "opportunity compact" if compact else "opportunity"
    details = "" if compact else f"""
  <p><span class="label">Eligibility</span><br>{escape(opp.get("eligibility") or "Check notice")}</p>
  <p><span class="label">Documents needed</span><br>{docs}</p>
  <p><span class="label">Screening fit</span><br>Score: {score}; profiles: {profiles}</p>
  <p><span class="label">Rationale</span><br>{rationale}</p>"""
    return f"""<article class="{class_name}">
  <h3><a href="{escape(opp.get("url", "#"))}">{escape(opp.get("title", "Untitled"))}</a></h3>
  <div class="meta">
    {badge}
    <span class="pill">{escape(opp.get("agency", "Unknown agency"))}</span>
    <span class="pill">Due: {escape(opp.get("due_date") or "Check notice")}</span>
    <span class="pill">Amount: {escape(opp.get("amount") or "Check notice")}</span>
  </div>
  <p>{escape(opp.get("description") or "No summary available. Review the source notice for details.")}</p>
  <p><span class="label">Opportunity number</span><br>{escape(opp.get("opportunity_number") or "Not listed")}</p>
  {details}
</article>"""
