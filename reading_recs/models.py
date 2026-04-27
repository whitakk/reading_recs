from dataclasses import dataclass, field


@dataclass
class Article:
    url: str
    title: str
    source: str
    text: str
    source_section: str = ""
    comment_count: int = 0
    is_above_average: bool = False
    limited_data: bool = False


@dataclass
class ScoredArticle:
    article: Article
    llm_score: float = 0.0
    reason: str = ""
    adjusted_score: float = 0.0
