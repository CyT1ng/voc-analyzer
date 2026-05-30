import pytest

from voc_analyzer import search


def test_build_covers_all_platforms_by_default():
    queries = search.build("Acme Buds", ["battery"])
    assert set(queries) == set(search.PLATFORMS)


def test_build_includes_product_and_keyword_queries():
    yt = search.build("Acme Buds", ["battery", "fit"])["youtube"]
    assert "Acme Buds" in yt
    assert "Acme Buds battery" in yt
    assert "Acme Buds fit" in yt


def test_build_without_keywords_uses_intent_modifiers():
    reddit = search.build("Acme Buds")["reddit"]
    assert any("review" in q for q in reddit)


def test_build_respects_platform_subset():
    queries = search.build("Acme Buds", platforms=("youtube",))
    assert set(queries) == {"youtube"}


def test_build_rejects_empty_product():
    with pytest.raises(ValueError):
        search.build("   ")
