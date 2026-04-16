import feedparser
import requests
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote_plus

# ============================================================
# STOCK NEWS AGENT
# ------------------------------------------------------------
# What it does:
# 1. Pulls RSS feeds for broad market, sectors, and tickers
# 2. Detects analyst upgrades / downgrades / initiations
# 3. Detects important macro / sector / company-impacting news
# 4. Scores each item by importance
# 5. Maps each item to one or more tickers / sectors
# 6. Prints a ranked watchlist for the user
# ------------------------------------------------------------
# Install:
#   pip install feedparser requests pandas
#
# Optional:
#   You can later wire this into email / Slack / DB / scheduler.
# ============================================================

# -----------------------------
# USER CONFIG
# -----------------------------
WATCHLIST = [
    "NVDA", "AMD", "MU", "AVGO", "LITE", "AAOI", "AAPL", "MSFT", "AMZN", "TSLA"
]

TICKER_TO_SECTOR = {
    "NVDA": "Semiconductors",
    "AMD": "Semiconductors",
    "MU": "Semiconductors",
    "AVGO": "Semiconductors",
    "LITE": "Optical Networking",
    "AAOI": "Optical Networking",
    "AAPL": "Consumer Technology",
    "MSFT": "Software",
    "AMZN": "Internet / Cloud",
    "TSLA": "EV / Auto",
}

SECTOR_KEYWORDS = {
    "Semiconductors": ["semiconductor", "chip", "chips", "gpu", "memory", "dram", "nand", "foundry", "fab"],
    "Optical Networking": ["optical", "datacenter interconnect", "transceiver", "photonics", "networking"],
    "Software": ["software", "cloud", "saas", "ai software", "enterprise software"],
    "Internet / Cloud": ["cloud", "e-commerce", "retail", "ad spending", "aws", "consumer internet"],
    "Consumer Technology": ["iphone", "smartphone", "consumer electronics", "devices", "wearables"],
    "EV / Auto": ["ev", "electric vehicle", "autonomous", "battery", "auto sales"],
}

# Broad RSS feeds. Add/remove as needed.
RSS_FEEDS = [
    # Reuters markets/business
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.reuters.com/news/usmarkets",

    # MarketWatch top stories
    "http://feeds.marketwatch.com/marketwatch/topstories/",

    # Seeking Alpha symbols and market news (some feeds may vary over time)
    "https://seekingalpha.com/feed.xml",

    # CNBC world / finance
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",

    # Yahoo Finance general news
    "https://finance.yahoo.com/news/rssindex",
]

# Analyst signal words
UPGRADE_WORDS = [
    "upgrade", "upgraded", "raises rating", "raised to buy", "raised to overweight",
    "raised to outperform", "initiated with buy", "initiated at buy", "bullish on"
]
DOWNGRADE_WORDS = [
    "downgrade", "downgraded", "cuts rating", "cut to hold", "cut to underperform",
    "cut to neutral", "initiated with sell", "bearish on"
]
TARGET_UP_WORDS = [
    "raises price target", "raised price target", "pt raised", "target raised"
]
TARGET_DOWN_WORDS = [
    "cuts price target", "cut price target", "pt cut", "target lowered", "lowers price target"
]

# Important market / sector impact words
HIGH_IMPACT_KEYWORDS = [
    "guidance", "warns", "warning", "sec", "doj", "probe", "investigation",
    "export restriction", "ban", "tariff", "sanctions", "ceasefire", "war",
    "ai spending", "capex", "demand surge", "supply shortage", "supply glut",
    "layoffs", "merger", "acquisition", "bankruptcy", "default", "recall",
    "earnings beat", "earnings miss", "revenue beat", "revenue miss",
    "cpi", "ppi", "inflation", "fed", "rate cut", "rate hike", "treasury yield",
    "opec", "oil prices", "guidance raised", "guidance cut"
]

MACRO_KEYWORDS = [
    "federal reserve", "fed", "inflation", "cpi", "ppi", "rates", "yield", "treasury",
    "jobs report", "payrolls", "pce", "gdp", "consumer confidence", "retail sales"
]

SECTOR_MOVING_KEYWORDS = [
    "sector", "industry", "peer", "competitor", "supply chain", "orders", "backlog",
    "pricing", "memory prices", "gpu demand", "server demand", "datacenter", "cloud spend"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StockNewsAgent/1.0)"
}

MAX_ITEMS_PER_FEED = 80
REQUEST_TIMEOUT = 20


@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    source: str
    published: Optional[datetime]
    tickers: List[str]
    sectors: List[str]
    category: str
    sentiment: str
    impact_score: float
    reasons: List[str]


class StockNewsAgent:
    def __init__(self, watchlist: List[str], ticker_to_sector: Dict[str, str], rss_feeds: List[str]):
        self.watchlist = [x.upper() for x in watchlist]
        self.ticker_to_sector = {k.upper(): v for k, v in ticker_to_sector.items()}
        self.rss_feeds = rss_feeds
        self.watch_sectors = sorted({self.ticker_to_sector.get(t) for t in self.watchlist if self.ticker_to_sector.get(t)})

    # --------------------------------------------------------
    # Main run
    # --------------------------------------------------------
    def run(self) -> List[NewsItem]:
        raw_entries = self.fetch_all_feeds()
        items = []

        for entry in raw_entries:
            item = self.process_entry(entry)
            if item is not None:
                items.append(item)

        deduped = self.deduplicate(items)
        ranked = sorted(deduped, key=lambda x: (x.impact_score, x.published or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
        return ranked

    # --------------------------------------------------------
    # Feed ingestion
    # --------------------------------------------------------
    def fetch_all_feeds(self) -> List[dict]:
        entries = []
        for feed_url in self.rss_feeds:
            try:
                parsed = feedparser.parse(feed_url)
                feed_title = parsed.feed.get("title", feed_url)
                for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
                    entry["_feed_title"] = feed_title
                    entry["_feed_url"] = feed_url
                    entries.append(entry)
            except Exception as e:
                print(f"Feed parse failed for {feed_url}: {e}")
        return entries

    # --------------------------------------------------------
    # Processing
    # --------------------------------------------------------
    def process_entry(self, entry: dict) -> Optional[NewsItem]:
        title = clean_text(entry.get("title", ""))
        summary = clean_text(entry.get("summary", entry.get("description", "")))
        link = entry.get("link", "")
        source = entry.get("_feed_title", "Unknown Source")
        published = parse_published(entry)

        full_text = f"{title}. {summary}".lower()
        tickers = self.find_tickers(full_text)
        sectors = self.find_sectors(full_text, tickers)

        category, sentiment, reasons, score = self.classify_item(title, summary, tickers, sectors)

        # Filter out low-value items that do not touch watchlist, sectors, or macro
        relevant = bool(tickers or sectors or category in {"macro", "market"} or contains_any(full_text, HIGH_IMPACT_KEYWORDS))
        if not relevant:
            return None

        # Require some minimum signal strength
        if score < 1.0:
            return None

        return NewsItem(
            title=title,
            summary=summary,
            link=link,
            source=source,
            published=published,
            tickers=tickers,
            sectors=sectors,
            category=category,
            sentiment=sentiment,
            impact_score=round(score, 2),
            reasons=reasons,
        )

    def classify_item(self, title: str, summary: str, tickers: List[str], sectors: List[str]) -> Tuple[str, str, List[str], float]:
        text = f"{title}. {summary}".lower()
        reasons = []
        score = 0.0
        sentiment = "neutral"
        category = "company"

        # Direct watchlist mention
        if tickers:
            score += 2.5
            reasons.append(f"Mentions watchlist ticker(s): {', '.join(tickers)}")

        # Sector relevance
        if sectors:
            score += 1.5
            reasons.append(f"Touches tracked sector(s): {', '.join(sectors)}")

        # Analyst actions
        if contains_any(text, UPGRADE_WORDS):
            category = "analyst"
            sentiment = "bullish"
            score += 4.0
            reasons.append("Analyst upgrade / bullish rating signal")

        if contains_any(text, DOWNGRADE_WORDS):
            category = "analyst"
            sentiment = "bearish"
            score += 4.0
            reasons.append("Analyst downgrade / bearish rating signal")

        if contains_any(text, TARGET_UP_WORDS):
            category = "analyst"
            if sentiment == "neutral":
                sentiment = "bullish"
            score += 2.0
            reasons.append("Price target increased")

        if contains_any(text, TARGET_DOWN_WORDS):
            category = "analyst"
            if sentiment == "neutral":
                sentiment = "bearish"
            score += 2.0
            reasons.append("Price target reduced")

        # Macro
        if contains_any(text, MACRO_KEYWORDS):
            category = "macro"
            score += 2.0
            reasons.append("Macro signal affecting broad market")

        # Sector-moving signals
        if contains_any(text, SECTOR_MOVING_KEYWORDS):
            if category == "company":
                category = "sector"
            score += 1.5
            reasons.append("Potential sector or peer impact")

        # High-impact keywords
        matched_high_impact = matched_keywords(text, HIGH_IMPACT_KEYWORDS)
        if matched_high_impact:
            score += min(4.0, 0.8 * len(matched_high_impact))
            reasons.append("High-impact keywords: " + ", ".join(matched_high_impact[:5]))

        # Earnings / guidance intensity
        if any(x in text for x in ["earnings", "guidance", "forecast", "outlook"]):
            score += 1.2
            reasons.append("Earnings / guidance relevance")

        # Regulatory / geopolitics usually matter a lot
        if any(x in text for x in ["investigation", "probe", "sec", "doj", "tariff", "sanctions", "ban", "war", "ceasefire"]):
            score += 1.8
            reasons.append("Regulatory or geopolitical relevance")

        # Company + sector + market together => more important
        overlap_bonus = 0.0
        if tickers and sectors:
            overlap_bonus += 1.0
        if category in {"macro", "sector"} and sectors:
            overlap_bonus += 0.8
        if category == "analyst" and tickers:
            overlap_bonus += 1.0
        score += overlap_bonus
        if overlap_bonus:
            reasons.append("Multiple relevance layers overlap")

        # Simple sentiment heuristic if still neutral
        positive_words = ["beat", "surge", "strong", "raises", "expands", "growth", "bullish", "upside"]
        negative_words = ["miss", "cuts", "weak", "warning", "probe", "lawsuit", "delay", "drop"]
        pos_count = sum(1 for w in positive_words if w in text)
        neg_count = sum(1 for w in negative_words if w in text)

        if sentiment == "neutral":
            if pos_count > neg_count:
                sentiment = "bullish"
            elif neg_count > pos_count:
                sentiment = "bearish"

        return category, sentiment, reasons, score

    # --------------------------------------------------------
    # Entity mapping
    # --------------------------------------------------------
    def find_tickers(self, text: str) -> List[str]:
        hits = []
        for ticker in self.watchlist:
            patterns = [
                rf"\b{re.escape(ticker.lower())}\b",
                rf"\({re.escape(ticker.lower())}\)",
                rf"\b{re.escape(ticker.lower())}:",
            ]
            if any(re.search(p, text) for p in patterns):
                hits.append(ticker)
        return sorted(set(hits))

    def find_sectors(self, text: str, tickers: List[str]) -> List[str]:
        sectors = set()

        # infer from tickers first
        for t in tickers:
            sector = self.ticker_to_sector.get(t)
            if sector:
                sectors.add(sector)

        # infer from keywords second
        for sector, keywords in SECTOR_KEYWORDS.items():
            if any(k.lower() in text for k in keywords):
                sectors.add(sector)

        return sorted(sectors)

    # --------------------------------------------------------
    # Deduplication
    # --------------------------------------------------------
    def deduplicate(self, items: List[NewsItem]) -> List[NewsItem]:
        seen = {}
        for item in items:
            key = normalize_title(item.title)
            if key not in seen:
                seen[key] = item
            else:
                # keep the higher-scored item
                if item.impact_score > seen[key].impact_score:
                    seen[key] = item
        return list(seen.values())


# ============================================================
# Helper functions
# ============================================================
def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title(title: str) -> str:
    title = title.lower().strip()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def parse_published(entry: dict) -> Optional[datetime]:
    candidates = [
        entry.get("published"),
        entry.get("updated"),
        entry.get("pubDate"),
    ]
    for val in candidates:
        if not val:
            continue
        try:
            dt = parsedate_to_datetime(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def contains_any(text: str, patterns: List[str]) -> bool:
    return any(p.lower() in text for p in patterns)


def matched_keywords(text: str, patterns: List[str]) -> List[str]:
    return [p for p in patterns if p.lower() in text]


def fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "unknown-time"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def print_report(items: List[NewsItem], top_n: int = 25) -> None:
    print("\n" + "=" * 120)
    print("RANKED STOCK NEWS WATCHLIST")
    print("=" * 120)

    if not items:
        print("No relevant items found.")
        return

    for idx, item in enumerate(items[:top_n], 1):
        print(f"\n[{idx}] {item.title}")
        print(f"    Source     : {item.source}")
        print(f"    Published  : {fmt_dt(item.published)}")
        print(f"    Category   : {item.category}")
        print(f"    Sentiment  : {item.sentiment}")
        print(f"    Score      : {item.impact_score}")
        print(f"    Tickers    : {', '.join(item.tickers) if item.tickers else '-'}")
        print(f"    Sectors    : {', '.join(item.sectors) if item.sectors else '-'}")
        print(f"    Reasons    : {' | '.join(item.reasons)}")
        print(f"    Summary    : {item.summary[:400]}{'...' if len(item.summary) > 400 else ''}")
        print(f"    Link       : {item.link}")


def group_by_ticker(items: List[NewsItem]) -> Dict[str, List[NewsItem]]:
    out: Dict[str, List[NewsItem]] = {}
    for item in items:
        targets = item.tickers if item.tickers else [f"SECTOR::{s}" for s in item.sectors] if item.sectors else ["MACRO"]
        for target in targets:
            out.setdefault(target, []).append(item)
    return out


def print_ticker_view(items: List[NewsItem]) -> None:
    grouped = group_by_ticker(items)
    print("\n" + "=" * 120)
    print("TICKER / SECTOR VIEW")
    print("=" * 120)

    for key in sorted(grouped.keys()):
        sub = sorted(grouped[key], key=lambda x: x.impact_score, reverse=True)[:5]
        print(f"\n{key}")
        for item in sub:
            print(f"  - ({item.impact_score}) [{item.sentiment}] {item.title}")


# ============================================================
# Optional extensions
# ============================================================
def build_yahoo_symbol_rss(ticker: str) -> str:
    # Yahoo's feed patterns can vary over time. Included as a helper only.
    return f"https://finance.yahoo.com/rss/headline?s={quote_plus(ticker)}"


def build_seekingalpha_symbol_rss(ticker: str) -> str:
    # Pattern may vary; included as a helper only.
    return f"https://seekingalpha.com/api/sa/combined/{quote_plus(ticker)}.xml"


def add_symbol_specific_feeds(base_feeds: List[str], watchlist: List[str]) -> List[str]:
    feeds = list(base_feeds)
    for t in watchlist:
        feeds.append(build_yahoo_symbol_rss(t))
    return feeds


# ============================================================
# HTML OUTPUT
# ============================================================
def generate_html_dashboard(items: List[NewsItem], output_file: str = "index.html"):
    html = ["""
    <html>
    <head>
        <title>Stock News Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 10px; }
            h1 { margin: 0 0 10px 0; font-size: 20px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 8px; }
            .card { background: #1e293b; padding: 8px 10px; margin: 0; border-radius: 8px; line-height: 1.2; }
            .title { font-size: 13px; font-weight: 700; margin-bottom: 4px; }
            .meta { font-size: 11px; color: #cbd5e1; margin: 2px 0; }
            .summary { font-size: 11px; color: #e2e8f0; margin: 4px 0; }
            .bullish { color: #22c55e; font-weight: 700; }
            .bearish { color: #ef4444; font-weight: 700; }
            .neutral { color: #facc15; font-weight: 700; }
            a { color: #38bdf8; text-decoration: none; font-size: 11px; }
        </style>
    </head>
    <body>
        <h1>📊 Stock News Dashboard</h1>
        <div class='grid'>
    """]

    for item in items[:150]:
        sentiment_class = item.sentiment
        html.append(f"""
        <div class='card'>
            <div class='title'>{item.title}</div>
            <div class='meta'>{item.source} | Score: {item.impact_score} | <span class='{sentiment_class}'>{item.sentiment}</span></div>
            <div class='meta'>Tickers: {', '.join(item.tickers) if item.tickers else '-'} | Sectors: {', '.join(item.sectors) if item.sectors else '-'}</div>
            <div class='summary'>{item.summary[:180]}</div>
            <a href='{item.link}' target='_blank'>Read more</a>
        </div>
        """)

    html.append("</body></html>")
    
    with open(output_file, "w", encoding="utf-8") as f:
    	f.write("\n".join(html))

    print(f"HTML dashboard generated: {output_file}")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    # Uncomment this if you want ticker-specific RSS added automatically.
    # all_feeds = add_symbol_specific_feeds(RSS_FEEDS, WATCHLIST)
    all_feeds = RSS_FEEDS

    agent = StockNewsAgent(
        watchlist=WATCHLIST,
        ticker_to_sector=TICKER_TO_SECTOR,
        rss_feeds=all_feeds,
    )

    results = agent.run()
    print_report(results, top_n=30)
    print_ticker_view(results)

    # Generate HTML dashboard
    generate_html_dashboard(results)
