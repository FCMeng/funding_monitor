# Funding Monitor

`funding_monitor` fetches curated funding opportunities, screens them against CV-derived research profiles with OpenAI models, publishes a static GitHub Pages report, and emails proposal guidance for newly matched opportunities.

## What It Monitors

- Grants.gov, including NIH and FDA opportunities posted there.
- NSF funding RSS feeds.
- DOE Office of Science funding pages.
- South Carolina research sources such as SCRA.
- Quantum computing, quantum information science, quantum systems, and quantum materials opportunities surfaced by the curated sources.

## Screening

- `gpt-5.5` screens opportunities for fit.
- `gpt-5.5` writes proposal guidance for matched opportunities.
- Profiles are derived from the two supplied CV PDFs and encoded in `config/profiles.json`.
- The GitHub Pages report lets you select a run from the left sidebar and view that run's matched and fetched opportunities.

## Secrets

Configure these GitHub Actions secrets:

- `OPENAI_API_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- optional `SMTP_SECURITY` (`ssl`, `starttls`, or `plain`; defaults to SSL on port 465 and STARTTLS otherwise)
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`
- optional `GRANTS_GOV_API_KEY`

## Schedule

The workflow runs on Tuesdays at 11:00 and 12:00 UTC, then the app gates execution to exactly 7:00 AM in `America/New_York`. That follows EST/EDT automatically.

## Local Commands

```bash
python -m funding_monitor.cli dry-run
python -m funding_monitor.cli render
python -m unittest discover -s tests -p 'test*.py'
```

For a local heuristic run without OpenAI or email:

```bash
FUNDING_MONITOR_ALLOW_HEURISTIC=1 python -m funding_monitor.cli dry-run
```

Useful runtime knobs:

- `FUNDING_MONITOR_MAX_LLM_SCREENS`: maximum prefiltered new opportunities to screen with OpenAI per run, default `8`.
- `FUNDING_MONITOR_RECIPIENT`: overrides `EMAIL_TO`.

## GitHub Pages

The generated static page is written to `docs/index.html`. Configure Pages for the repository `FCMeng/funding_monitor` to publish from the `docs/` folder on `main`.
