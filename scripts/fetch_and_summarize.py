#!/usr/bin/env python3
"""
Daily Oncology Paper Digest
Fetches latest papers from Nature/Cell RSS feeds, filters for oncology/ML topics,
generates AI summaries via Claude API, and saves structured JSON for GitHub Pages.
"""

import feedparser
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import anthropic

# ─── CONFIG ───────────────────────────────────────────────────────────────────
RSS_FEEDS = {
    "Nature": [
        "https://www.nature.com/nature.rss",
        "https://www.nature.com/nm.rss",           # Nature Medicine
        "https://www.nature.com/nrc.rss",           # Nature Reviews Cancer
        "https://www.nature.com/ncb.rss",           # Nature Cancer Biology
        "https://www.nature.com/nc.rss",            # Nature Cancer
        "https://www.nature.com/nbt.rss",           # Nature Biotechnology
        "https://www.nature.com/ncomms.rss",        # Nature Communications
    ],
    "Cell": [
        "https://www.cell.com/cell/rss/current",
        "https://www.cell.com/cancer-cell/rss/current",
        "https://www.cell.com/cell-reports-medicine/rss/current",
        "https://www.cell.com/cell-systems/rss/current",
        "https://www.cell.com/med/rss/current",
    ],
}

ONCOLOGY_KEYWORDS = [
    "cancer", "tumor", "tumour", "oncology", "oncogenesis",
    "carcinoma", "sarcoma", "lymphoma", "leukemia", "leukaemia",
    "melanoma", "glioma", "metastasis", "metastatic",
    "chemotherapy", "immunotherapy", "targeted therapy", "radiotherapy",
    "BRCA", "TP53", "KRAS", "checkpoint inhibitor", "CAR-T",
    "drug resistance", "biomarker", "survival", "clinical trial",
    "mutation", "oncogene", "tumor suppressor", "angiogenesis",
    # ML/AI intersection
    "machine learning", "deep learning", "artificial intelligence",
    "neural network", "transformer", "foundation model",
    "radiomics", "pathomics", "digital pathology",
    "multi-omics", "single-cell", "spatial transcriptomics",
]

OUTPUT_DIR = Path("docs/papers")
INDEX_FILE = Path("docs/papers/index.json")
MAX_PAPERS_TO_KEEP = 90  # ~3 months


# ─── FEED PARSING ─────────────────────────────────────────────────────────────
def fetch_recent_papers(max_per_feed=30):
    """Fetch and filter papers from all RSS feeds."""
    candidates = []
    seen_titles = set()

    for journal_group, urls in RSS_FEEDS.items():
        for url in urls:
            try:
                print(f"  Fetching {url} ...")
                feed = feedparser.parse(url, request_headers={"User-Agent": "OncologyDigestBot/1.0"})
                for entry in feed.entries[:max_per_feed]:
                    title = entry.get("title", "").strip()
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    abstract = (
                        entry.get("summary", "")
                        or entry.get("description", "")
                        or ""
                    )
                    full_text = (title + " " + abstract).lower()

                    if not any(kw.lower() in full_text for kw in ONCOLOGY_KEYWORDS):
                        continue

                    pub_date = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                        pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                    candidates.append({
                        "title": title,
                        "abstract": abstract[:3000],
                        "url": entry.get("link", ""),
                        "journal_group": journal_group,
                        "journal": feed.feed.get("title", journal_group),
                        "pub_date": pub_date.isoformat() if pub_date else None,
                        "authors": _extract_authors(entry),
                    })
            except Exception as e:
                print(f"  WARNING: failed to fetch {url}: {e}")

    # Sort by pub date descending, newest first
    candidates.sort(key=lambda x: x["pub_date"] or "", reverse=True)
    print(f"Found {len(candidates)} oncology-relevant candidates.")
    return candidates


def _extract_authors(entry):
    authors = []
    if hasattr(entry, "authors"):
        authors = [a.get("name", "") for a in entry.authors if a.get("name")]
    elif hasattr(entry, "author"):
        authors = [entry.author]
    return authors[:6]  # cap at 6


# ─── DEDUP ────────────────────────────────────────────────────────────────────
def load_existing_index():
    if INDEX_FILE.exists():
        with open(INDEX_FILE) as f:
            return json.load(f)
    return {"papers": [], "last_updated": None}


def already_processed(url, index_data):
    existing_urls = {p["url"] for p in index_data.get("papers", [])}
    return url in existing_urls


# ─── SUMMARIZATION ────────────────────────────────────────────────────────────
SUMMARY_PROMPT = SUMMARY_PROMPT = """You are a science communicator explaining cutting-edge cancer research 
to a smart but non-specialist audience — someone curious about science but new to biology.

Paper Title: {title}
Journal: {journal}
Authors: {authors}
Abstract: {abstract}

Return ONLY valid JSON (no markdown, no backticks) with this exact schema:
{{
  "headline": "One plain-English sentence (≤20 words) capturing the core finding — no jargon",
  "why_it_matters": "2-3 sentences on why this matters for patients or medicine. Use simple language.",
  "key_findings": [
    "Finding 1 — explain any technical terms in plain words in parentheses",
    "Finding 2",
    "Finding 3",
    "Finding 4 (optional)",
    "Finding 5 (optional)"
  ],
  "methods_snapshot": "2 sentences on how the study was done. Explain any technical methods simply.",
  "glossary": [
    {{"term": "technical term", "definition": "plain English definition in 1 sentence"}},
    {{"term": "another term", "definition": "plain English definition"}}
  ],
  "cancer_types": ["list", "of", "cancer", "types", "studied"],
  "ml_angle": "If AI/ML was used: 1 plain-English sentence on what the AI did. Otherwise null.",
  "limitations": "1-2 sentences on caveats, in simple language",
  "tags": ["relevant", "keyword", "tags", "max8"],
  "study_type": "one of: clinical trial | preclinical | computational | review | multi-omics | single-cell | imaging | other",
  "impact_score": 1-5
}}

Rules:
- Write as if explaining to a curious friend with no science background
- Always define acronyms the first time you use them
- Avoid Latin or Greek terms without explanation
- Use analogies where helpful
- impact_score: 5=landmark finding, 4=significant advance, 3=solid contribution, 2=incremental, 1=limited scope"""

def generate_summary(paper, client):
    """Call Claude API to generate structured summary."""
    prompt = SUMMARY_PROMPT.format(
        title=paper["title"],
        journal=paper["journal"],
        authors=", ".join(paper["authors"]) if paper["authors"] else "Not listed",
        abstract=paper["abstract"] or "(no abstract available)",
    )

    # message = client.messages.create(
    #     model="claude-opus-4-5",
    #     max_tokens=1200,
    #     messages=[{"role": "user", "content": prompt}],
    # )
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip accidental markdown fences
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index_data = load_existing_index()

    print("=== Fetching papers ===")
    candidates = fetch_recent_papers()

    # Filter out already-processed papers
    new_candidates = [p for p in candidates if not already_processed(p["url"], index_data)]
    print(f"{len(new_candidates)} new papers to process (after dedup).")

    if not new_candidates:
        print("No new papers today. Exiting.")
        return

    # Pick 1 paper: highest relevance (first after sort = most recent)
    paper = new_candidates[0]
    print(f"\n=== Summarizing: {paper['title'][:80]}... ===")

    try:
        summary = generate_summary(paper, client)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"API error: {e}")
        sys.exit(1)

    # Build full paper record
    paper_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d')}_{re.sub(r'[^a-z0-9]', '_', paper['title'].lower())[:40]}"
    record = {
        "id": paper_id,
        "title": paper["title"],
        "url": paper["url"],
        "journal": paper["journal"],
        "journal_group": paper["journal_group"],
        "authors": paper["authors"],
        "pub_date": paper["pub_date"],
        "fetched_date": datetime.now(timezone.utc).isoformat(),
        "abstract": paper["abstract"],
        **summary,
    }

    # Save individual paper JSON
    paper_file = OUTPUT_DIR / f"{paper_id}.json"
    with open(paper_file, "w") as f:
        json.dump(record, f, indent=2)
    print(f"Saved: {paper_file}")

    # Update index
    index_data["papers"].insert(0, {
        "id": paper_id,
        "title": paper["title"],
        "url": paper["url"],
        "journal": paper["journal"],
        "pub_date": paper["pub_date"],
        "fetched_date": record["fetched_date"],
        "headline": summary.get("headline", ""),
        "cancer_types": summary.get("cancer_types", []),
        "tags": summary.get("tags", []),
        "study_type": summary.get("study_type", ""),
        "impact_score": summary.get("impact_score", 3),
        "ml_angle": summary.get("ml_angle"),
    })
    # Prune old entries
    index_data["papers"] = index_data["papers"][:MAX_PAPERS_TO_KEEP]
    index_data["last_updated"] = datetime.now(timezone.utc).isoformat()

    with open(INDEX_FILE, "w") as f:
        json.dump(index_data, f, indent=2)
    print(f"Index updated: {INDEX_FILE}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
