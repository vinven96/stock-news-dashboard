import feedparser
import re
import html as html_lib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict, Optional, Tuple


# ============================================================
# CONFIG
# ============================================================

WATCHLIST = [
    "NVDA", "AMD", "MU", "AVGO", "LITE", "AAOI",
    "AAPL", "MSFT", "AMZN", "META", "GOOGL",
    "TSLA", "NFLX", "JPM", "LLY", "SMCI", "ANET"
]

QUALITY_STOCKS = {
    "NVDA", "AMD", "MU", "AVGO", "LITE", "AAOI",
    "AAPL", "MSFT", "AMZN", "META", "GOOGL",
    "TSLA", "NFLX", "JPM", "LLY", "SMCI", "ANET",
    "MRVL", "QCOM", "ARM", "ASML", "TSM", "CRM",
    "ORCL", "ADBE", "UBER", "COST", "WMT", "PANW",
    "CRWD", "SNOW", "DELL", "HPE", "PLTR", "INTC"
}

TICKER_TO_SECTOR = {
    "NVDA": "Semiconductors",
    "AMD": "Semiconductors",
    "MU": "Memory",
    "AVGO": "Semiconductors",
    "LITE": "Optical Networking",
    "AAOI": "Optical Networking",
    "AAPL": "Consumer Technology",
    "MSFT": "Software / Cloud",
    "AMZN": "Internet / Cloud",
    "META": "Internet / Advertising",
    "GOOGL": "Internet / Advertising",
    "TSLA": "EV / Auto",
    "NFLX": "Media / Streaming",
    "JPM": "Financials",
    "LLY": "Pharma / Biotech",
    "SMCI": "AI Infrastructure",
    "ANET": "Networking",
    "MRVL": "Semiconductors",
    "QCOM": "Semiconductors",
    "ARM": "Semiconductors",
    "ASML": "Semiconductor Equipment",
    "TSM": "Foundry",
    "CRM": "Software / Cloud",
    "ORCL": "Software / Cloud",
    "ADBE": "Software",
    "UBER": "Internet",
    "COST": "Consumer",
    "WMT": "Consumer",
    "PANW": "Cybersecurity",
    "CRWD": "Cybersecurity",
    "SNOW": "Software / Cloud",
    "DELL": "AI Infrastructure",
    "HPE": "AI Infrastructure",
    "PLTR": "Software / AI",
    "INTC": "Semiconductors",
}

SECTOR_KEYWORDS = {
    "Semiconductors": [
        "semiconductor", "chip", "chips", "gpu", "ai chip", "foundry",
        "fab", "wafer", "chipmaker", "datacenter chip", "accelerator"
    ],
    "Memory": [
        "dram", "nand", "memory prices", "memory pricing", "hbm",
        "memory chip", "memory market", "ddr5"
    ],
    "Optical Networking": [
        "optical", "transceiver", "photonics", "coherent", "datacenter interconnect"
    ],
    "Software / Cloud": [
        "cloud", "software", "saas", "enterprise software", "enterprise ai"
    ],
    "Internet / Cloud": [
        "e-commerce", "internet", "online retail", "aws"
    ],
    "Internet / Advertising": [
        "advertising", "digital ads", "ad spend", "internet platform"
    ],
    "EV / Auto": [
        "electric vehicle", "battery", "auto sales", "autonomous", "automaker"
    ],
    "Financials": [
        "bank", "banking", "loan growth", "credit quality", "net interest income"
    ],
    "AI Infrastructure": [
        "server", "rack", "ai server", "liquid cooling", "infrastructure buildout", "datacenter buildout"
    ],
    "Networking": [
        "ethernet", "switching", "routing", "networking", "datacenter network"
    ],
    "Pharma / Biotech": [
        "drug trial", "fda", "approval", "phase 3", "clinical trial"
    ],
    "Consumer": [
        "consumer spending", "retail sales", "same-store sales"
    ],
    "Cybersecurity": [
        "cybersecurity", "cyber attack", "security software", "endpoint security"
    ],
    "Software / AI": [
        "ai software", "large language model", "llm", "artificial intelligence platform"
    ]
}

RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.reuters.com/news/usmarkets",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://finance.yahoo.com/news/rssindex",
    "http://feeds.marketwatch.com/marketwatch/topstories/",
]

MAX_ITEMS_PER_FEED = 150

IMPORTANT_MACRO = [
    "cpi", "ppi", "pce", "inflation", "nonfarm payrolls", "payrolls",
    "jobs report", "jobless claims", "unemployment rate", "gdp",
    "retail sales", "consumer confidence", "ism manufacturing", "ism services",
    "treasury yield", "treasury yields", "10-year yield", "bond yields",
    "opec", "oil prices", "crude oil", "recession", "trade deficit",
    "growth slowdown", "growth worries"
]

IMPORTANT_FED = [
    "fomc", "federal reserve", "fed meeting", "fed minutes", "powell",
    "jerome powell", "rate cut", "rate cuts", "rate hike", "rate hikes",
    "dot plot", "hawkish", "dovish"
]

IMPORTANT_ANALYST = [
    "upgrade", "upgraded", "downgrade", "downgraded",
    "price target", "raises target", "cuts target",
    "raises price target", "cuts price target",
    "outperform", "overweight", "underperform", "neutral",
    "buy rating", "sell rating", "initiated", "reiterated"
]

IMPORTANT_COMPANY = [
    "earnings", "guidance", "forecast", "outlook", "revenue beat", "revenue miss",
    "eps beat", "eps miss", "raises guidance", "cuts guidance",
    "sec", "doj", "investigation", "probe", "lawsuit",
    "merger", "acquisition", "deal talks", "bankruptcy",
    "tariff", "sanctions", "export restriction", "ban",
    "product launch", "order backlog", "large order", "supply agreement",
    "buyback", "share repurchase", "capital raise", "offering"
]

IMPORTANT_SECTOR = [
    "pricing", "prices rise", "prices fall", "demand surge", "weak demand",
    "backlog", "capex", "capacity", "utilization", "supply glut", "supply shortage",
    "cloud spending", "ai spending", "server demand", "memory pricing", "hbm demand",
    "bookings", "lead times", "inventory correction", "inventory build",
    "datacenter demand", "enterprise demand"
]

NOISE_PATTERNS = [
    "top stocks",
    "best stocks",
    "3 stocks",
    "5 stocks",
    "technical analysis",
    "opinion",
    "editorial",
    "motley fool",
    "zacks",
    "penny stock",
    "hot stock"
]


# ============================================================
# DATA MODEL
# ============================================================

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
    tier: str
    sentiment: str
    impact_score: float
    reasons: List[str]


# ============================================================
# HELPERS
# ============================================================

def clean_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title(title: str) -> str:
    title = title.lower().strip()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def parse_published(entry: dict) -> Optional[datetime]:
    for key in ["published", "updated", "pubDate"]:
        value = entry.get(key)
        if not value:
            continue
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return None


def contains_any(text: str, patterns: List[str]) -> bool:
    text = text.lower()
    return any(p.lower() in text for p in patterns)


def matched_keywords(text: str, patterns: List[str]) -> List[str]:
    text = text.lower()
    return [p for p in patterns if p.lower() in text]


def fmt_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "unknown-time"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def keyword_present(text: str, keyword: str) -> bool:
    keyword = keyword.lower().strip()
    text = text.lower()

    if len(keyword) <= 3 and " " not in keyword:
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None

    return keyword in text


def extract_sector_hits(text: str) -> Dict[str, List[str]]:
    hits: Dict[str, List[str]] = {}
    for sector, keywords in SECTOR_KEYWORDS.items():
        matched = [k for k in keywords if keyword_present(text, k)]
        if matched:
            hits[sector] = matched
    return hits


# ============================================================
# AGENT
# ============================================================

class StockNewsAgent:
    def __init__(self) -> None:
        self.watchlist = [t.upper() for t in WATCHLIST]
        self.quality_stocks = {t.upper() for t in QUALITY_STOCKS}
        self.ticker_to_sector = {k.upper(): v for k, v in TICKER_TO_SECTOR.items()}
        self.all_tickers = sorted(set(self.watchlist).union(self.quality_stocks))

    def fetch_all_feeds(self) -> List[dict]:
        entries = []
        for feed_url in RSS_FEEDS:
            try:
                parsed = feedparser.parse(feed_url)
                feed_title = parsed.feed.get("title", feed_url)
                for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
                    entry["_feed_title"] = feed_title
                    entry["_feed_url"] = feed_url
                    entries.append(entry)
            except Exception as exc:
                print(f"Feed parse failed for {feed_url}: {exc}")
        return entries

    def run(self) -> List[NewsItem]:
        raw_entries = self.fetch_all_feeds()
        processed: List[NewsItem] = []

        for entry in raw_entries:
            item = self.process_entry(entry)
            if item is not None:
                processed.append(item)

        deduped = self.deduplicate(processed)

        ranked = sorted(
            deduped,
            key=lambda x: (
                x.impact_score,
                x.published or datetime.min.replace(tzinfo=timezone.utc)
            ),
            reverse=True
        )
        return ranked

    def process_entry(self, entry: dict) -> Optional[NewsItem]:
        title = clean_text(entry.get("title", ""))
        summary = clean_text(entry.get("summary", entry.get("description", "")))
        link = entry.get("link", "")
        source = entry.get("_feed_title", "Unknown Source")
        published = parse_published(entry)

        full_text = f"{title}. {summary}".lower()

        if contains_any(full_text, NOISE_PATTERNS):
            if not any(t.lower() in full_text for t in self.all_tickers):
                sector_tmp = extract_sector_hits(full_text)
                if not sector_tmp and not contains_any(full_text, IMPORTANT_MACRO + IMPORTANT_FED):
                    return None

        tickers = self.find_tickers(full_text)
        sector_hit_map = extract_sector_hits(full_text)
        sectors = self.find_sectors_from_hits(tickers, sector_hit_map)

        category, tier, sentiment, reasons, score = self.classify_item(
            title=title,
            summary=summary,
            tickers=tickers,
            sectors=sectors,
            sector_hit_map=sector_hit_map
        )

        if not self.is_important(
            text=full_text,
            tickers=tickers,
            sectors=sectors,
            category=category,
            tier=tier,
            score=score
        ):
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
            tier=tier,
            sentiment=sentiment,
            impact_score=round(score, 2),
            reasons=reasons
        )

    def find_tickers(self, text: str) -> List[str]:
        hits = []
        for ticker in self.all_tickers:
            patterns = [
                rf"\b{re.escape(ticker.lower())}\b",
                rf"\({re.escape(ticker.lower())}\)",
                rf"\b{re.escape(ticker.lower())}:"
            ]
            if any(re.search(p, text) for p in patterns):
                hits.append(ticker)
        return sorted(set(hits))

    def find_sectors_from_hits(self, tickers: List[str], sector_hit_map: Dict[str, List[str]]) -> List[str]:
        sectors = set()

        for ticker in tickers:
            sector = self.ticker_to_sector.get(ticker)
            if sector:
                sectors.add(sector)

        for sector in sector_hit_map.keys():
            sectors.add(sector)

        return sorted(sectors)

    def classify_item(
        self,
        title: str,
        summary: str,
        tickers: List[str],
        sectors: List[str],
        sector_hit_map: Dict[str, List[str]]
    ) -> Tuple[str, str, str, List[str], float]:
        text = f"{title}. {summary}".lower()
        reasons: List[str] = []
        score = 0.0
        sentiment = "neutral"
        category = "general"
        tier = "MORE RELEVANT NEWS"

        macro_hits = matched_keywords(text, IMPORTANT_MACRO)
        fed_hits = matched_keywords(text, IMPORTANT_FED)
        analyst_hits = matched_keywords(text, IMPORTANT_ANALYST)
        company_hits = matched_keywords(text, IMPORTANT_COMPANY)
        sector_signal_hits = matched_keywords(text, IMPORTANT_SECTOR)

        if macro_hits:
            category = "macro"
            tier = "MARKET MOVING"
            score += 4.0
            reasons.append("Macro data event: " + ", ".join(macro_hits[:4]))

        if fed_hits:
            category = "macro"
            tier = "MARKET MOVING"
            score += 4.5
            reasons.append("Fed-related event: " + ", ".join(fed_hits[:4]))

        if analyst_hits and tickers:
            category = "analyst"
            tier = "ACTIONABLE"
            score += 3.5
            reasons.append("Analyst action: " + ", ".join(analyst_hits[:4]))

        if company_hits and tickers:
            category = "company"
            tier = "ACTIONABLE"
            score += 3.5
            reasons.append("Important company event: " + ", ".join(company_hits[:4]))

        if sector_signal_hits and sectors and tier == "MORE RELEVANT NEWS":
            category = "sector"
            tier = "SECTOR SIGNAL"
            score += 3.0
            reasons.append("Sector signal: " + ", ".join(sector_signal_hits[:4]))

        quality_hits = [t for t in tickers if t in self.quality_stocks]
        if quality_hits:
            score += 2.0
            reasons.append("Mentions quality stock(s): " + ", ".join(quality_hits[:5]))

        watch_hits = [t for t in tickers if t in self.watchlist]
        if watch_hits:
            score += 1.5
            reasons.append("Mentions watchlist ticker(s): " + ", ".join(watch_hits[:5]))

        if sectors:
            score += 1.5
            reasons.append("Touches tracked sector(s): " + ", ".join(sectors[:4]))

        if sector_hit_map and not tickers:
            score += 1.5
            if tier == "MORE RELEVANT NEWS":
                tier = "SECTOR SIGNAL"
                category = "sector"
            reasons.append("Sector theme without ticker mention")

        if tickers and score < 4.0:
            score += 1.5
            if tier == "MORE RELEVANT NEWS":
                tier = "ACTIONABLE"
                category = "company"
            reasons.append("Broad ticker relevance")

        if sectors and score < 4.0:
            score += 1.0
            if tier == "MORE RELEVANT NEWS":
                tier = "SECTOR SIGNAL"
                category = "sector"
            reasons.append("Broad sector relevance")

        if not tickers and not sectors and contains_any(text, IMPORTANT_ANALYST + IMPORTANT_COMPANY):
            score += 1.0
            reasons.append("General important company/analyst headline")

        bullish_words = [
            "beat", "raises guidance", "surge", "strong demand", "upside",
            "upgrade", "raised price target", "bullish", "outperform"
        ]
        bearish_words = [
            "miss", "cuts guidance", "weak demand", "investigation",
            "downgrade", "cut price target", "bearish", "underperform"
        ]

        bullish_count = sum(1 for x in bullish_words if x in text)
        bearish_count = sum(1 for x in bearish_words if x in text)

        if bullish_count > bearish_count:
            sentiment = "bullish"
        elif bearish_count > bullish_count:
            sentiment = "bearish"

        if tier == "MARKET MOVING":
            score += 1.0
        elif tier == "ACTIONABLE":
            score += 0.75
        elif tier == "SECTOR SIGNAL":
            score += 0.5

        return category, tier, sentiment, reasons, score

    def is_important(
        self,
        text: str,
        tickers: List[str],
        sectors: List[str],
        category: str,
        tier: str,
        score: float
    ) -> bool:
        return (
            bool(tickers)
            or bool(sectors)
            or contains_any(text, IMPORTANT_MACRO + IMPORTANT_FED)
            or contains_any(text, IMPORTANT_ANALYST + IMPORTANT_COMPANY + IMPORTANT_SECTOR)
        )

    def deduplicate(self, items: List[NewsItem]) -> List[NewsItem]:
        seen: Dict[str, NewsItem] = {}
        for item in items:
            key = normalize_title(item.title)
            if key not in seen:
                seen[key] = item
            else:
                if item.impact_score > seen[key].impact_score:
                    seen[key] = item
        return list(seen.values())


# ============================================================
# OUTPUT
# ============================================================

def print_report(items: List[NewsItem], top_n: int = 200) -> None:
    print("\n" + "=" * 120)
    print("IMPORTANT STOCK NEWS")
    print("=" * 120)

    if not items:
        print("No important items found.")
        return

    for idx, item in enumerate(items[:top_n], 1):
        print(f"\n[{idx}] {item.title}")
        print(f"    Tier       : {item.tier}")
        print(f"    Category   : {item.category}")
        print(f"    Sentiment  : {item.sentiment}")
        print(f"    Score      : {item.impact_score}")
        print(f"    Published  : {fmt_dt(item.published)}")
        print(f"    Source     : {item.source}")
        print(f"    Tickers    : {', '.join(item.tickers) if item.tickers else '-'}")
        print(f"    Sectors    : {', '.join(item.sectors) if item.sectors else '-'}")
        print(f"    Reasons    : {' | '.join(item.reasons)}")
        print(f"    Summary    : {item.summary[:220]}{'...' if len(item.summary) > 220 else ''}")
        print(f"    Link       : {item.link}")


def split_by_tier(items: List[NewsItem]) -> Dict[str, List[NewsItem]]:
    grouped = {
        "MARKET MOVING": [],
        "ACTIONABLE": [],
        "SECTOR SIGNAL": [],
        "MORE RELEVANT NEWS": [],
    }
    for item in items:
        if item.tier in grouped:
            grouped[item.tier].append(item)
        else:
            grouped["MORE RELEVANT NEWS"].append(item)
    return grouped


def generate_html_dashboard(items: List[NewsItem], output_file: str = "index.html") -> None:
    grouped = split_by_tier(items)

    html_parts = ["""
<html>
<head>
    <meta charset="utf-8">
    <title>Important Stock News Dashboard</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            margin: 0;
            padding: 8px;
        }
        h1 {
            margin: 0 0 8px 0;
            font-size: 18px;
        }
        h2 {
            margin: 10px 0 6px 0;
            font-size: 14px;
            color: #93c5fd;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 6px;
        }
        .card {
            background: #1e293b;
            border-radius: 7px;
            padding: 7px 8px;
            line-height: 1.15;
        }
        .title {
            font-size: 12px;
            font-weight: 700;
            margin-bottom: 3px;
        }
        .meta {
            font-size: 10px;
            color: #cbd5e1;
            margin: 1px 0;
        }
        .summary {
            font-size: 10px;
            margin-top: 3px;
            color: #e2e8f0;
        }
        .bullish { color: #22c55e; font-weight: 700; }
        .bearish { color: #ef4444; font-weight: 700; }
        .neutral { color: #facc15; font-weight: 700; }
        a {
            color: #38bdf8;
            text-decoration: none;
            font-size: 10px;
        }
        .empty {
            font-size: 10px;
            color: #94a3b8;
            padding: 4px 0 8px 0;
        }
    </style>
</head>
<body>
    <h1>Important Stock News Dashboard</h1>
"""]

    for section_name in ["MARKET MOVING", "ACTIONABLE", "SECTOR SIGNAL", "MORE RELEVANT NEWS"]:
        section_items = grouped.get(section_name, [])
        html_parts.append(f"<h2>{html_lib.escape(section_name)}</h2>")

        if not section_items:
            html_parts.append("<div class='empty'>No items in this section.</div>")
            continue

        html_parts.append("<div class='grid'>")

        for item in section_items[:150]:
            safe_title = html_lib.escape(item.title)
            safe_source = html_lib.escape(item.source)
            safe_summary = html_lib.escape(item.summary[:150])
            safe_link = html_lib.escape(item.link, quote=True)
            safe_tickers = html_lib.escape(", ".join(item.tickers) if item.tickers else "-")
            safe_sectors = html_lib.escape(", ".join(item.sectors) if item.sectors else "-")
            safe_tier = html_lib.escape(item.tier)
            safe_time = html_lib.escape(fmt_dt(item.published))
            sentiment_class = item.sentiment if item.sentiment in {"bullish", "bearish", "neutral"} else "neutral"

            html_parts.append(f"""
            <div class='card'>
                <div class='title'>{safe_title}</div>
                <div class='meta'>{safe_source} | {safe_time}</div>
                <div class='meta'>Tier: {safe_tier} | Score: {item.impact_score} | <span class='{sentiment_class}'>{html_lib.escape(item.sentiment)}</span></div>
                <div class='meta'>Tickers: {safe_tickers}</div>
                <div class='meta'>Sectors: {safe_sectors}</div>
                <div class='summary'>{safe_summary}</div>
                <a href='{safe_link}' target='_blank'>Read more</a>
            </div>
            """)

        html_parts.append("</div>")

    html_parts.append("</body></html>")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))

    print(f"HTML dashboard generated: {output_file}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    agent = StockNewsAgent()
    results = agent.run()

    print_report(results, top_n=200)
    generate_html_dashboard(results, output_file="index.html")