import json
import os
from pathlib import Path
from typing import Literal

ProductivityLabel = Literal["productive", "neutral", "distracting", "idle"]

DEFAULT_RULES = {
    "productive_title_keywords": [
        "github", "gitlab", "bitbucket", "jira", "linear", "notion", "confluence",
        "documentation", "docs", "readme", "spreadsheet", "budget", "proposal",
        "research", "figma", "dashboard", "report", "fastapi", "react", "python",
        "javascript", "typescript", "nodejs", "node.js", "sql", "backend", "frontend",
        "system design", "algorithm", "api", "docker", "kubernetes", "ci/cd", "devops",
        "antigravity", "vscode", "vs code", "stackoverflow", "mdn web docs",
        "machine learning", "deep learning", "neural network", "llm", "gpt", "gemini",
        "claude", "mistral", "llama", "transformer", "bert", "fine-tuning", "rag",
        "langchain", "hugging face", "pytorch", "tensorflow", "keras", "scikit-learn",
        "data science", "data analysis", "pandas", "numpy", "jupyter", "notebook",
        "aws", "google cloud", "gcp", "azure", "cloudflare", "vercel", "serverless",
        "tutorial", "how to", "learn", "course", "lecture", "explained",
        "fundamentals", "masterclass", "coursera", "udemy", "freecodecamp",
        "leetcode", "hackerrank", "ted talk", "ted-ed", "book summary",
        "lok sabha", "budget", "proposal", "research", "figma", "dashboard", "report", "rajya sabha"
    ],
    "neutral_title_keywords": [
        "slack", "gmail", "calendar", "meet", "zoom", "teams", "mail", "inbox",
        "outlook", "whatsapp", "telegram", "wikipedia", "google search", "translate"
    ],
    "distracting_title_keywords": [
        "shorts", "vlog", "reaction", "try not to laugh", "meme", "funny",
        "roast", "prank", "challenge", "satisfying", "asmr", "music video",
        "official video", "lyric video", "live concert", "unboxing", "haul",
        "top 10", "viral", "celebrity", "gossip", "netflix", "prime video",
        "hotstar", "disney+", "spotify", "crunchyroll", "watch online",
        "full movie", "full episode", "instagram", "facebook", "x.com", "twitter",
        "tiktok", "snapchat", "reddit", "steam", "epic games", "gaming",
        "playthrough", "speedrun", "esports", "roblox", "minecraft", "fortnite",
        "valorant", "playlist", "trending", "songs", "bollywood", "web series"
    ],
}

class ProductivityClassifier:
    def __init__(self, rules_path: str | Path | None = None):
        self.rules = DEFAULT_RULES.copy()
        if rules_path:
            self._load_rules(Path(rules_path))

    def _load_rules(self, path: Path):
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for key in ["productive_title_keywords", "neutral_title_keywords", "distracting_title_keywords"]:
                if key in data and isinstance(data[key], list):
                    # Merge and deduplicate
                    self.rules[key] = list(set(self.rules[key] + data[key]))
        except Exception:
            pass

    def classify(self, title: str | None, domain: str | None = None) -> ProductivityLabel:
        text = f"{(title or '').lower()} {(domain or '').lower()}".strip()
        if not text:
            return "neutral"

        for kw in self.rules["productive_title_keywords"]:
            if kw.lower() in text:
                return "productive"

        for kw in self.rules["neutral_title_keywords"]:
            if kw.lower() in text:
                return "neutral"

        for kw in self.rules["distracting_title_keywords"]:
            if kw.lower() in text:
                return "distracting"

        return "neutral"

# Global instance
RULES_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "agent", "productivity_rules.json")
classifier = ProductivityClassifier(RULES_FILE)
