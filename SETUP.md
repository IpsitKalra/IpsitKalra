# Setup

1. Create a **public** GitHub repository whose name exactly matches your GitHub username.
2. Copy everything in this folder into that repository's default branch.
3. Replace every `YOUR_*` placeholder in `README.md`.
4. Edit `NOW.md` and `TELEMETRY.json` so the dashboard sounds like you.
5. Open **Actions** → **Render mission-control dashboard** → **Run workflow**.
6. Ensure **Settings → Actions → General → Workflow permissions** allows read and write access if the workflow cannot push generated SVG files.
7. Enable Issues if you want the `/collaborate`, `/challenge`, and `/ask` links to work.

## Customize the questionable telemetry

`TELEMETRY.json` controls the three big dashboard metrics and the one-line system status:

```json
{
  "metrics": [
    {
      "label": "CLAUDE TOKENS SACRIFICED",
      "value": "2.7M",
      "detail": "this month · probably worth it"
    },
    {
      "label": "\"QUICK FIXES\" ATTEMPTED",
      "value": "14",
      "detail": "0 remained quick"
    },
    {
      "label": "BUGS PROMOTED TO FEATURES",
      "value": "06",
      "detail": "marketing approved"
    }
  ],
  "status_line": "CURRENT SANITY: CACHED · COFFEE-to-COMMIT LATENCY: 11m"
}
```

Good replacements include:

- `CONTEXT WINDOWS DESTROYED`
- `TIMES I BLAMED DNS`
- `TODOs THAT ACHIEVED TENURE`
- `PRODUCTION INCIDENTS SURVIVED`
- `TESTS WRITTEN BEFORE THE BUG`
- `STACK OVERFLOW TABS IN ORBIT`
- `HOURS SAVED BY AUTOMATION`
- `PEOPLE USING THINGS I BUILT`

The funniest metrics work best when at least one is real and the other two are suspiciously specific.

## Optional live Claude token usage

For Anthropic API organization usage, create an Anthropic **Admin API key**, then save it in this GitHub repository as an Actions secret named:

```text
ANTHROPIC_ADMIN_KEY
```

When that secret exists, the first telemetry card is replaced with the current UTC month's token usage from Anthropic's Usage API. Never place the key in `TELEMETRY.json`, the workflow file, or any committed file.

A personal Claude Pro/Max subscription does not provide this workflow with a universal public lifetime token counter. Claude Code can expose token metrics through OpenTelemetry, but that requires sending telemetry to a backend you control. Without either setup, leave the token number as a manual running joke.

## Local preview

```bash
PROFILE_USERNAME=your-github-username python3 scripts/render_signal.py
```

Without credentials, the script uses the editable telemetry file and creates a polished placeholder preview. In GitHub Actions it uses the built-in `GITHUB_TOKEN` for public repository data.

## Personalize the visual language

Edit the palette near the top of `render_svg()` in `scripts/render_signal.py`. Keep both light and dark variants so the dashboard follows each visitor's GitHub theme.

## What to delete or replace

- Replace generic project cards with three projects that demonstrate different kinds of judgment.
- Rewrite the Mermaid flow to reflect how you genuinely work.
- Keep the Human API compact; specificity is more memorable than a giant skill-icon grid.
- Remove any section that does not teach a visitor something useful about you.
