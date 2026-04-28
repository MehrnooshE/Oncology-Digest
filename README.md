# Oncology Research Digest 🔬

A fully automated pipeline that fetches one new oncology / ML×cancer paper daily from **Nature** and **Cell** journals, generates a one-page AI summary via Claude, and publishes it to a GitHub Pages site.

---

## What it does

| Step | What happens |
|---|---|
| **07:00 UTC daily** | GitHub Actions triggers the workflow |
| **Feed scraping** | Checks 12 RSS feeds across Nature and Cell families |
| **Keyword filtering** | Keeps papers matching oncology/ML keywords |
| **Claude summarization** | Generates structured JSON summary via Claude API |
| **Commit & push** | New JSON file + updated index pushed to repo |
| **GitHub Pages** | Site automatically reflects new paper |

---

## Repository structure

```
your-repo/
├── .github/
│   └── workflows/
│       └── daily_digest.yml       ← GitHub Actions workflow
├── scripts/
│   └── fetch_and_summarize.py     ← Main pipeline script
└── docs/                          ← GitHub Pages root
    ├── index.html                 ← The website UI
    └── papers/
        ├── index.json             ← Master index of all papers
        └── {date}_{slug}.json     ← One file per paper
```

---

## Setup (10 minutes)

### 1. Create your GitHub repository

```bash
git init oncology-digest
cd oncology-digest
# Copy all files from this package into the directory
git add .
git commit -m "initial setup"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Add your Anthropic API key as a GitHub Secret

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: your key from [console.anthropic.com](https://console.anthropic.com)

### 3. Enable GitHub Pages

1. Go to **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, Folder: `/docs`
4. Click **Save**

Your site will be at: `https://YOUR_USERNAME.github.io/YOUR_REPO/`

### 4. Run the first digest manually

Go to **Actions** → **Daily Oncology Paper Digest** → **Run workflow**

Within ~2 minutes, a new paper will appear on your site.

---

## Customization

### Change the schedule

Edit `.github/workflows/daily_digest.yml`:
```yaml
- cron: "0 7 * * *"   # 07:00 UTC daily
```
Use [crontab.guru](https://crontab.guru) to pick your time.

### Fetch more papers per day

In `scripts/fetch_and_summarize.py`, change the last line of `main()`:
```python
paper = new_candidates[0]   # change index or loop for multiple papers
```

### Add more journals

Add RSS feed URLs to the `RSS_FEEDS` dict in the script.

### Add email delivery

After the summary is generated, add a step to the workflow using [SendGrid](https://sendgrid.com) or [Resend](https://resend.com) to email yourself the paper.

---

## Local testing

```bash
pip install anthropic feedparser
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/fetch_and_summarize.py
```

Then open `docs/index.html` in a browser (via a local server, e.g. `python -m http.server 8000` from `docs/`).

---

## Cost estimate

- ~1,200 tokens per summary (Claude Opus)
- ~$0.015 per day at current pricing
- ~$5/year

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Workflow fails with auth error | Check `ANTHROPIC_API_KEY` secret is set correctly |
| "No new papers" in logs | All recent papers already processed, or feeds returned no oncology matches — check logs |
| Site shows blank | GitHub Pages may take 5–10 min after first push; check Pages is set to `/docs` |
| JSON parse error | Rare; re-run the workflow — Claude occasionally adds preamble text |
