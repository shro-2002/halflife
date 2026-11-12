"""W1: claim extraction. Offline tests script FakeChat; one live test (deselected by default)."""

import json
from datetime import date

import pytest

from halflife.clients.bifrost import ModelError
from halflife.clients.fakes import FakeChat
from halflife.extract import MAX_CLAIMS, MAX_TOKENS, extract_claims
from halflife.schemas import VolatilityClass as V

AS_OF = date(2026, 6, 30)
TODAY = date(2026, 11, 12)


def item(span: str, cls: str, p: object = 0.5, **kw: object) -> dict:
    return {"text": kw.pop("text", span), "span": span, "volatility_class": cls, "p_outdated_model": p, **kw}


async def run(answer: str, output: object):
    text = output if isinstance(output, str) else json.dumps(output)
    fake = FakeChat([text])
    res = await extract_claims(answer, fake, as_of=AS_OF, today=TODAY)
    return res, fake


# --- one case per class / answer type -------------------------------------------------------

CASES = [
    pytest.param(
        "ChatGPT Plus costs $20 per month.",
        [item("ChatGPT Plus costs $20 per month", "price", 0.3, subject="ChatGPT Plus",
              authoritative_domain="openai.com")],
        [(V.PRICE, 0.3)], id="price",
    ),
    pytest.param(
        "Netflix's Standard plan is $17.99/month in the US, and Spotify Premium Individual is $11.99.",
        [item("Netflix's Standard plan is $17.99/month in the US", "price", 0.4),
         item("Spotify Premium Individual is $11.99", "price", 0.5)],
        [(V.PRICE, 0.4), (V.PRICE, 0.5)], id="two-prices",
    ),
    pytest.param(
        "The latest stable Python release is 3.13, available from python.org.",
        [item("The latest stable Python release is 3.13", "software_version", 0.8,
              authoritative_domain="python.org", subject="Python")],
        [(V.SOFTWARE_VERSION, 0.8)], id="software-version",
    ),
    pytest.param(
        "Use the OpenAI API with model gpt-4o; Node.js 22 is the current LTS line.",
        [item("Node.js 22 is the current LTS line", "software_version", 0.7)],
        [(V.SOFTWARE_VERSION, 0.7)], id="api-version-instruction-skipped",
    ),
    pytest.param(
        "Under GDPR, fines can reach 4% of global annual turnover.",
        [item("fines can reach 4% of global annual turnover", "law_or_regulation", 0.05,
              text="Under GDPR, fines can reach 4% of global annual turnover.")],
        [(V.LAW_OR_REGULATION, 0.05)], id="law",
    ),
    pytest.param(
        "The US federal minimum wage is $7.25 per hour.",
        [item("The US federal minimum wage is $7.25 per hour", "law_or_regulation", 0.1)],
        [(V.LAW_OR_REGULATION, 0.1)], id="regulation-wage",
    ),
    pytest.param(
        "Satya Nadella is the CEO of Microsoft.",
        [item("Satya Nadella is the CEO of Microsoft", "office_holder", 0.02, subject="Microsoft")],
        [(V.OFFICE_HOLDER, 0.02)], id="office-holder",
    ),
    pytest.param(
        "The Fed funds target range is 4.25%-4.50%.",
        [item("The Fed funds target range is 4.25%-4.50%", "rate_or_statistic", 0.9)],
        [(V.RATE_OR_STATISTIC, 0.9)], id="rate",
    ),
    pytest.param(
        "The iPhone 16 Pro has a 6.3-inch display and starts with 128 GB of storage.",
        [item("The iPhone 16 Pro has a 6.3-inch display", "product_spec", 0.1),
         item("starts with 128 GB of storage", "product_spec", 0.2)],
        [(V.PRODUCT_SPEC, 0.1), (V.PRODUCT_SPEC, 0.2)], id="product-spec",
    ),
    pytest.param(
        "Water boils at 100 °C at sea level. Rust 1.80 is the newest release and costs nothing.",
        [item("Water boils at 100 °C at sea level", "timeless", 0.4),
         item("Rust 1.80 is the newest release", "software_version", 0.95),
         item("costs nothing", "price", 0.01)],
        [(V.TIMELESS, 0.0), (V.SOFTWARE_VERSION, 0.95), (V.PRICE, 0.01)], id="mixed-timeless-forced-zero",
    ),
]


@pytest.mark.parametrize(("answer", "output", "expected"), CASES)
async def test_extracts_validated_claims(answer, output, expected):
    res, fake = await run(answer, output)
    assert res.errors == []
    assert [(c.volatility_class, c.p_outdated_model) for c in res.claims] == expected
    assert [c.id for c in res.claims] == [f"c{i}" for i in range(1, len(expected) + 1)]
    assert all(c.span in answer for c in res.claims)
    assert res.model_calls == 1 and res.request_id == "fake-1" and len(fake.calls) == 1


@pytest.mark.parametrize("answer", [
    "Try restarting your router, then check the cable. I think that usually helps!",
    "A haiku has three lines with five, seven and five syllables.",
])
async def test_nothing_time_sensitive_returns_no_claims(answer):
    res, _ = await run(answer, [])
    assert res.claims == [] and res.errors == [] and res.model_calls == 1


async def test_dated_past_event_keeps_tense():
    answer = "Andy Jassy became CEO of Amazon in 2021."
    res, _ = await run(answer, [item("Andy Jassy became CEO of Amazon in 2021", "office_holder", 0.05,
                                     is_past_event=True, explicit_date="2021")])
    (c,) = res.claims
    assert c.is_past_event is True and c.explicit_date == date(2021, 1, 1)


async def test_prompt_carries_dates_and_classes():
    _, fake = await run("x", [])
    system = fake.calls[0][0]["content"]
    assert "given it was accurate as of 2026-06-30" in system and "2026-11-12" in system
    for cls in V:
        assert f'"{cls.value}"' in system


# --- validation ----------------------------------------------------------------------------

async def test_span_not_in_answer_is_dropped_with_error():
    answer = "Python 3.13 is the latest release."
    res, _ = await run(answer, [item("Python 3.12 is the latest release", "software_version"),
                                item("Python 3.13 is the latest release", "software_version")])
    assert [c.span for c in res.claims] == ["Python 3.13 is the latest release"]
    assert res.claims[0].id == "c1"
    assert len(res.errors) == 1 and "span not in answer" in res.errors[0]


async def test_whitespace_normalised_span_maps_back_to_answer_text():
    answer = "The plan costs\n$20   per month."
    res, _ = await run(answer, [item("The plan costs $20 per month", "price")])
    assert res.claims[0].span == "The plan costs\n$20   per month"


async def test_unknown_class_dropped_with_error():
    res, _ = await run("Bitcoin is at $60,000.", [item("Bitcoin is at $60,000", "crypto_price")])
    assert res.claims == [] and "unknown volatility_class" in res.errors[0]


@pytest.mark.parametrize(("raw", "expected"), [(1.7, 1.0), (-0.2, 0.0), ("0.25", 0.25), ("high", None),
                                                (None, None), (True, None)])
async def test_probability_clamped_or_none(raw, expected):
    res, _ = await run("Rust 1.80 is newest.", [item("Rust 1.80 is newest", "software_version", raw)])
    assert res.claims[0].p_outdated_model == expected


async def test_bad_explicit_date_becomes_none():
    res, _ = await run("Rates rose in spring.", [item("Rates rose in spring", "rate_or_statistic",
                                                      explicit_date="spring")])
    assert res.claims[0].explicit_date is None


async def test_duplicate_spans_deduped():
    res, _ = await run("Go 1.23 is current.", [item("Go 1.23 is current", "software_version"),
                                               item("Go 1.23 is current", "software_version")])
    assert len(res.claims) == 1


async def test_capped_at_max_claims():
    answer = " ".join(f"Fact{i}." for i in range(30))
    res, _ = await run(answer, [item(f"Fact{i}", "rate_or_statistic") for i in range(30)])
    assert len(res.claims) == MAX_CLAIMS and res.claims[-1].id == f"c{MAX_CLAIMS}"
    assert any("capped" in e for e in res.errors)


# --- model output shapes and failures ------------------------------------------------------

async def test_fenced_json_with_leading_prose():
    answer = "Kubernetes 1.31 is the latest minor."
    body = json.dumps([item("Kubernetes 1.31 is the latest minor", "software_version", 0.9)])
    res, _ = await run(answer, f"Here are the claims:\n```json\n{body}\n```")
    assert len(res.claims) == 1 and res.errors == []


async def test_claims_wrapper_object_accepted():
    res, _ = await run("Go 1.23 is current.", {"claims": [item("Go 1.23 is current", "software_version")]})
    assert len(res.claims) == 1


@pytest.mark.parametrize("text", ["I could not find any claims.", "[{\"span\": \"x\"", "{\"foo\": 1}"])
async def test_malformed_json_gives_zero_claims_and_error(text):
    res, _ = await run("Go 1.23 is current.", text)
    assert res.claims == [] and len(res.errors) == 1 and "malformed JSON" in res.errors[0]
    assert res.model_calls == 1


async def test_model_error_fails_open():
    fake = FakeChat([ModelError("bifrost 503")])
    res = await extract_claims("Go 1.23 is current.", fake, as_of=AS_OF, today=TODAY)
    assert res.claims == [] and "bifrost 503" in res.errors[0] and res.request_id is None


async def test_non_object_items_dropped():
    res, _ = await run("Go 1.23 is current.", ["junk", 3, item("Go 1.23 is current", "software_version")])
    assert len(res.claims) == 1 and len(res.errors) == 2


async def test_empty_answer_makes_no_call():
    fake = FakeChat([])
    res = await extract_claims("   ", fake, as_of=AS_OF, today=TODAY)
    assert res.claims == [] and res.model_calls == 0 and fake.calls == []


async def test_max_tokens_is_generous():
    seen = {}

    class Spy(FakeChat):
        async def chat(self, messages, *, max_tokens=1500, **kw):
            seen["max_tokens"] = max_tokens
            return await super().chat(messages, max_tokens=max_tokens, **kw)

    await extract_claims("x", Spy(["[]"]), as_of=AS_OF, today=TODAY)
    assert seen["max_tokens"] == MAX_TOKENS >= 2000


# --- live (3 calls through the real gateway) -----------------------------------------------

LIVE_ANSWERS = [
    "The latest stable version of Python is 3.12, and you can download it from python.org.",
    "Tim Cook became CEO of Apple in 2011. Apple's iPhone 15 starts at $799.",
    "Light travels at about 299,792 km per second in a vacuum. Try turning it off and on again.",
]


@pytest.mark.live
async def test_live_extract_through_bifrost():
    from halflife.clients.bifrost import BifrostClient
    from halflife.config import load_settings

    client = BifrostClient(load_settings())
    try:
        for answer in LIVE_ANSWERS:
            res = await extract_claims(answer, client, as_of=AS_OF, today=TODAY)
            print(f"\nANSWER: {answer}\n  request_id={res.request_id} errors={res.errors}")
            for c in res.claims:
                print(f"  {c.id} [{c.volatility_class.value}] p={c.p_outdated_model} past={c.is_past_event} "
                      f"date={c.explicit_date} domain={c.authoritative_domain} span={c.span!r}")
            assert res.model_calls == 1
            assert all(c.span in answer for c in res.claims)
    finally:
        await client.aclose()
