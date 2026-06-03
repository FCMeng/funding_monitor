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
    panels = render_run_panels(runs, opportunities, fetched_opportunities, latest_ids)

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
      --muted: #5f6b66;
      --line: #d3ddd7;
      --paper: #f4f7f3;
      --panel: #ffffff;
      --accent: #147a7e;
      --accent-2: #5f746b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        linear-gradient(180deg, #eef4ef 0, #f7faf7 310px, var(--paper) 100%);
    }}
    header {{
      padding: 54px clamp(18px, 7vw, 92px) 46px;
      background: transparent;
      color: #17211d;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0 0 10px; font-size: clamp(48px, 10vw, 118px); line-height: .9; letter-spacing: 0; }}
    header p {{ margin: 0; color: var(--muted); max-width: 900px; font-size: clamp(18px, 2vw, 26px); }}
    main {{
      display: grid;
      grid-template-columns: minmax(220px, 300px) minmax(0, 1fr);
      gap: 28px;
      padding: 58px clamp(18px, 7vw, 92px) 64px;
    }}
    aside, .opportunity {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    aside {{ padding: 28px; align-self: start; position: sticky; top: 16px; box-shadow: 0 1px 0 rgba(23, 33, 29, .02); }}
    aside h2, section h2 {{ margin: 0 0 16px; font-size: 18px; text-transform: uppercase; letter-spacing: .12em; color: var(--accent-2); }}
    .run {{
      display: block;
      width: 100%;
      border: 0;
      border-top: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 12px;
      text-align: left;
      font: inherit;
      color: var(--ink);
      background: transparent;
      cursor: pointer;
    }}
    .run:first-of-type {{ border-top: 0; }}
    .run[aria-selected="true"] {{ background: #e8efeb; }}
    .run[aria-selected="true"] strong {{ color: var(--accent); }}
    .run:hover strong {{ text-decoration: underline; }}
    .list {{ display: grid; gap: 18px; }}
    .opportunity {{ padding: 22px; box-shadow: 0 1px 0 rgba(23, 33, 29, .02); }}
    .opportunity.compact {{ padding: 18px 20px; }}
    .opportunity h3 {{ margin: 0 0 8px; font-size: 22px; line-height: 1.25; }}
    .opportunity.compact h3 {{ font-size: 19px; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 13px;
      color: var(--muted);
      background: #f8fbf9;
    }}
    .new {{ color: white; background: var(--accent); border-color: var(--accent); }}
    .label {{ color: var(--muted); font-size: 13px; text-transform: uppercase; }}
    p {{ line-height: 1.55; }}
    a {{ color: var(--accent); }}
    .empty {{ background: white; border: 1px dashed var(--line); border-radius: 8px; padding: 24px; }}
    .section-note {{ color: var(--muted); margin: 0 0 14px; }}
    section + section {{ margin-top: 28px; }}
    .run-panel[hidden] {{ display: none; }}
    @media (max-width: 780px) {{
      main {{ grid-template-columns: 1fr; }}
      aside {{ position: static; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Funding Monitor</h1>
    <p>Curated funding opportunities, run history, screening results, and source links for research proposal planning.</p>
  </header>
  <main>
    <aside>
      <h2>Fetch History</h2>
      {render_runs(runs)}
    </aside>
    <div id="run-results">
      {panels}
    </div>
  </main>
  <script>
    const buttons = Array.from(document.querySelectorAll(".run"));
    const panels = Array.from(document.querySelectorAll(".run-panel"));
    function selectRun(index) {{
      buttons.forEach((button) => button.setAttribute("aria-selected", button.dataset.runIndex === index ? "true" : "false"));
      panels.forEach((panel) => {{ panel.hidden = panel.dataset.runIndex !== index; }});
    }}
    buttons.forEach((button) => button.addEventListener("click", () => selectRun(button.dataset.runIndex)));
    if (buttons.length) selectRun(buttons[0].dataset.runIndex);
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def render_runs(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return '<p class="empty">No fetches yet.</p>'
    return "".join(
        f"""<button class="run" type="button" data-run-index="{index}" aria-selected="false">
  <strong>{escape(run.get("fetched_at", "unknown"))}</strong><br>
  fetched {int(run.get("fetched_count", 0))}, matched {int(run.get("matched_count", 0))}, new {int(run.get("new_count", 0))}
</button>"""
        for index, run in enumerate(runs[:20])
    )


def render_run_panels(
    runs: list[dict[str, Any]],
    opportunities: dict[str, Any],
    fetched_opportunities: dict[str, Any],
    latest_ids: set[str],
) -> str:
    if not runs:
        return """<section class="run-panel" data-run-index="0">
  <h2>Matched Opportunities</h2>
  <p class="empty">No fetches have been recorded yet.</p>
</section>"""
    panels = []
    for index, run in enumerate(runs[:20]):
        matched_ids = run.get("matched_ids") or run.get("new_ids") or list(opportunities)
        fetched_ids = run.get("fetched_ids") or list(fetched_opportunities)
        matched_cards = [
            render_card(opportunities[opp_id], is_new=opp_id in set(run.get("new_ids", [])) or opp_id in latest_ids)
            for opp_id in matched_ids
            if opp_id in opportunities
        ]
        fetched_cards = [
            render_card(fetched_opportunities[opp_id], is_new=False, compact=True)
            for opp_id in fetched_ids
            if opp_id in fetched_opportunities
        ]
        if not matched_cards:
            matched_cards.append('<p class="empty">No matched opportunities were recorded for this run.</p>')
        if not fetched_cards:
            fetched_cards.append('<p class="empty">No fetched opportunities were recorded for this run.</p>')
        panels.append(
            f"""<div class="run-panel" data-run-index="{index}" {"hidden" if index else ""}>
  <section>
    <h2>Matched Opportunities</h2>
    <div class="list">
      {''.join(matched_cards)}
    </div>
  </section>
  <section>
    <h2>Fetched Opportunities</h2>
    <p class="section-note">All opportunities fetched in this run, including items that were not selected as profile matches.</p>
    <div class="list">
      {''.join(fetched_cards)}
    </div>
  </section>
</div>"""
        )
    return "".join(panels)


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
