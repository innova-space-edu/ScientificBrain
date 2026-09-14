from scientific_brain.autonomous_discovery import (
    canonical_candidate_key,
    fallback_plan,
    preliminary_score,
)


def test_canonical_candidate_key_prefers_stable_identifiers():
    assert canonical_candidate_key({"doi": "https://doi.org/10.1000/ABC"}) == "doi:10.1000/abc"
    assert canonical_candidate_key({"arxiv_id": "2401.01234"}) == "arxiv:2401.01234"
    assert canonical_candidate_key({"title": "A Plasma Focus Result"}).startswith("title:")


def test_fallback_plan_is_bounded_and_contains_adversarial_search():
    context = {
        "topic": "PF-PPT CubeSat",
        "research_brief": {
            "topic": "PF-PPT CubeSat",
            "questions": ["What controls impulse bit?"],
        },
        "evidence_gaps": ["direct thrust measurement"],
        "contradictions": ["different impulse estimates"],
    }
    plan = fallback_plan(context, max_queries=4)
    assert 1 <= len(plan["queries"]) <= 4
    purposes = " ".join(item["purpose"] for item in plan["queries"]).lower()
    assert "adversarial" in purposes
    assert plan["inclusion_criteria"]
    assert plan["exclusion_criteria"]


def test_preliminary_score_rewards_context_and_readable_full_text():
    terms = {"impulse", "thrust", "pulsed", "plasma", "cubesat", "metrology"}
    strong = preliminary_score(
        {
            "title": "Impulse bit metrology for pulsed plasma thrusters on CubeSats",
            "abstract": "Direct thrust and impulse measurements for pulsed plasma propulsion.",
            "result_type": "paper",
            "system_can_read": True,
            "cited_by_count": 30,
            "publication_date": "2025-01-01",
        },
        terms,
        origin_count=2,
    )
    weak = preliminary_score(
        {
            "title": "Unrelated materials processing study",
            "abstract": "A manufacturing process outside spacecraft propulsion.",
            "result_type": "web",
            "system_can_read": False,
            "cited_by_count": 0,
            "publication_date": "2001",
        },
        terms,
        origin_count=1,
    )
    assert 0 <= weak < strong <= 1
