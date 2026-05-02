import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobpilot.steps.bullet_scorer import (  # noqa: E402
    _bullet_key,
    _has_weak_verb,
    question_for_rating,
)


def test_bullet_key_basic():
    assert _bullet_key(0, 0, 0) == "0-0-0"
    assert _bullet_key(2, 1, 3) == "2-1-3"


def test_weak_verb_passive():
    assert _has_weak_verb("was responsible for building the API") is True
    assert _has_weak_verb("helped the team ship faster") is True
    assert _has_weak_verb("assisted with onboarding 12 engineers") is True


def test_weak_verb_strong():
    assert _has_weak_verb("Led a team of 10 engineers") is False
    assert _has_weak_verb("Reduced P1 incidents 60% through RCA") is False
    assert _has_weak_verb("Built payments platform generating $26M") is False


def test_question_for_known_ratings():
    for rating in ["weak_no_metric", "weak_no_outcome", "weak_passive_verb", "vague"]:
        q = question_for_rating(rating)
        assert isinstance(q, str) and len(q) > 0


def test_question_for_unknown_rating_returns_fallback():
    q = question_for_rating("unknown_rating")
    assert isinstance(q, str) and len(q) > 0


def test_score_bullets_empty_profile_returns_empty_dict():
    from jobpilot.steps.bullet_scorer import score_bullets

    assert score_bullets({"experience": []}, None, None, None) == {}


def test_score_bullets_no_experience_key():
    from jobpilot.steps.bullet_scorer import score_bullets

    assert score_bullets({}, None, None, None) == {}


def test_render_bullet_analysis_all_strong():
    from jobpilot.routes.profile import _render_bullet_analysis

    profile = {
        "experience": [
            {
                "company": "Acme",
                "positions": [
                    {
                        "title": "SWE",
                        "dates": "2023-present",
                        "achievements": ["Led team of 8"],
                    }
                ],
            }
        ]
    }
    scores = {"0-0-0": {"rating": "strong", "note": ""}}
    html = _render_bullet_analysis(profile, scores)
    assert "All 1 bullets look strong" in html


def test_render_bullet_analysis_shows_weak_bullets():
    from jobpilot.routes.profile import _render_bullet_analysis

    profile = {
        "experience": [
            {
                "company": "Acme",
                "positions": [
                    {
                        "title": "SWE",
                        "dates": "2023-present",
                        "achievements": ["Helped the team's roadmap ship on time"],
                    }
                ],
            }
        ]
    }
    scores = {"0-0-0": {"rating": "weak_passive_verb", "note": "Avoid 'helped'"}}
    html = _render_bullet_analysis(profile, scores)
    assert "Improve" in html
    # Apostrophe in bullet text must not break the hx-vals attribute (double-quoted)
    assert "'" not in html.split('hx-vals="')[1].split('"')[0]


def test_improve_bullet_endpoint_exists():
    import jobpilot.routes.profile as profile_mod

    assert hasattr(profile_mod, "improve_bullet"), (
        "improve_bullet endpoint not yet defined"
    )


def test_rewrite_bullet_endpoint_exists():
    import jobpilot.routes.profile as profile_mod

    assert hasattr(profile_mod, "rewrite_bullet_route"), (
        "rewrite_bullet_route not yet defined"
    )
