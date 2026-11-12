"""Typed records shared by every Half-Life module.

Every other module imports from here; nothing here imports from them.
"""

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class VolatilityClass(str, Enum):
    SOFTWARE_VERSION = "software_version"
    PRICE = "price"
    RATE_OR_STATISTIC = "rate_or_statistic"
    OFFICE_HOLDER = "office_holder"
    LAW_OR_REGULATION = "law_or_regulation"
    PRODUCT_SPEC = "product_spec"
    TIMELESS = "timeless"


# Starting half-lives in days. These are GUESSES (build prompt), replaced by fitted values
# from the ledger once outcomes exist. Timeless has no half-life (never decays).
PRIOR_HALF_LIFE_DAYS: dict[VolatilityClass, float] = {
    VolatilityClass.SOFTWARE_VERSION: 120.0,
    VolatilityClass.PRICE: 240.0,
    VolatilityClass.RATE_OR_STATISTIC: 150.0,
    VolatilityClass.OFFICE_HOLDER: 900.0,
    VolatilityClass.LAW_OR_REGULATION: 700.0,
    VolatilityClass.PRODUCT_SPEC: 300.0,
}


class AgeBasis(str, Enum):
    MODEL_CUTOFF = "model_cutoff"  # fresh answer: days since the answering model's knowledge cutoff
    CACHE_WRITE = "cache_write"  # cached answer: days since the cache entry was written
    EXPLICIT_DATE = "explicit_date"  # claim states its own as-of date


class Claim(BaseModel):
    """One time-sensitive (or explicitly timeless) factual statement found in an answer."""

    id: str
    text: str = Field(description="Claim restated as a standalone sentence")
    span: str = Field(description="Exact substring of the answer the claim came from")
    volatility_class: VolatilityClass
    explicit_date: date | None = Field(default=None, description="As-of date stated in the claim, if any")
    is_past_event: bool = Field(default=False, description="Dated past event ('became CEO in 2021'): not a current claim")
    subject: str | None = Field(default=None, description="Entity the claim is about, for search")
    authoritative_domain: str | None = Field(default=None, description="Official site, e.g. python.org")
    p_outdated_model: float | None = Field(
        default=None, ge=0, le=1,
        description="Extractor model's probability the claim is no longer accurate today, given the answer's "
        "as-of date (same call as extraction). Default ranking signal for the verification budget.",
    )


class RiskScore(BaseModel):
    claim_id: str
    age_days: float = Field(ge=0)
    age_basis: AgeBasis
    half_life_days: float | None = Field(description="None for timeless claims")
    half_life_source: Literal["prior_guess", "fitted"]
    p_stale: float = Field(ge=0, le=1, description="Half-life model: 1 - 2^(-age/h)")
    recommended_ttl_days: float | None = Field(default=None, description="Days until p_stale reaches epsilon")
    rank_score: float = Field(ge=0, le=1, description="Score used to order verification")
    rank_basis: Literal["model_p", "half_life"] = Field(
        description="model_p when the extractor returned p_outdated_model; half_life as fallback (J0.5 result)"
    )


class Evidence(BaseModel):
    """One search result exactly as Tavily returned it (ground rule 2: verdicts rest only on this)."""

    url: str
    title: str = ""
    content: str = Field(description="Snippet text returned by Tavily; quotes are checked against this")
    published_date: str | None = None
    query: str
    is_authoritative: bool = False
    retrieved_at: datetime


class VerdictLabel(str, Enum):
    CURRENT = "current"  # evidence supports the claim as still true
    CHANGED = "changed"  # evidence states a different current value
    UNVERIFIABLE = "unverifiable"  # searched, evidence insufficient (or quote check failed)


class Verdict(BaseModel):
    claim_id: str
    label: VerdictLabel
    supporting_quote: str | None = Field(default=None, description="Verbatim span from evidence content")
    supporting_url: str | None = None
    current_value: str | None = Field(default=None, description="Only when the evidence states it")
    source_urls: list[str] = Field(default_factory=list, description="Only URLs present in the evidence")
    reasoning: str = Field(default="", description="Model's explanation; shown separately from evidence")
    quote_verified: bool = False


class ScoreBasis(str, Enum):
    VERIFIED_AUTHORITATIVE = "verified_current_authoritative"  # 95
    VERIFIED_SINGLE = "verified_current_single_source"  # 80
    CHANGED = "changed"  # 5
    UNVERIFIED = "unverified"  # 100*(1-p), capped 50
    ESTIMATED = "estimated"  # 100*(1-p), not searched (over budget)
    NOT_TIME_SENSITIVE = "not_time_sensitive"  # timeless: no score


class ClaimReport(BaseModel):
    claim: Claim
    risk: RiskScore
    searched: bool
    evidence: list[Evidence] = Field(default_factory=list)
    verdict: Verdict | None = None
    freshness_score: float | None = Field(default=None, ge=0, le=100)
    score_basis: ScoreBasis
    errors: list[str] = Field(default_factory=list, description="What failed (fail open)")

    @model_validator(mode="after")
    def _consistent(self) -> "ClaimReport":
        if self.score_basis is ScoreBasis.NOT_TIME_SENSITIVE and self.freshness_score is not None:
            raise ValueError("timeless claims get no score")
        if self.score_basis is not ScoreBasis.NOT_TIME_SENSITIVE and self.freshness_score is None:
            raise ValueError("time-sensitive claims need a score")
        if self.verdict is not None and not self.searched:
            raise ValueError("a verdict requires a search")
        return self


class Usage(BaseModel):
    model_calls: int = 0
    model_cost_usd: float = 0.0
    tavily_calls: int = 0
    tavily_credits: int = 0
    tavily_cache_hits: int = 0
    latency_ms: float = 0.0


class AnswerReport(BaseModel):
    answer: str
    model: str | None = Field(default=None, description="Model that produced the answer, if known")
    mode: Literal["check", "gateway"]
    checked_at: datetime
    verification_budget: int | None = Field(default=None, description="Max claims searched; None = all")
    claims: list[ClaimReport]
    answer_score: float | None = Field(default=None, description="Mean of scored claims; None if none scored")
    usage: Usage = Field(default_factory=Usage)
    errors: list[str] = Field(default_factory=list)
    bifrost_request_id: str | None = None


class StaleRateRow(BaseModel):
    """Gateway audit aggregate for one (model, virtual key) slice."""

    model: str
    virtual_key: str | None
    answers_seen: int
    answers_checked: int
    claims_found: int
    claims_verified: int
    claims_changed: int
    stale_rate: float | None = Field(description="claims_changed / claims_verified; None if nothing verified")
    mean_answer_score: float | None = None


class GatewaySummary(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    logs_scanned: int
    sample_cap: int
    verification_budget: int
    rows: list[StaleRateRow]
    half_lives: dict[str, float] = Field(description="Class -> half-life days in use")
    half_life_source: dict[str, Literal["prior_guess", "fitted"]]
    usage: Usage = Field(default_factory=Usage)
    errors: list[str] = Field(default_factory=list)
