from tickwell.matching import CatalogMatcher, normalize, parse_pot
from tickwell.matching.catalog import CatalogItem

ITEMS = [
    CatalogItem("LAV-HID-P19", "Lavandula angustifolia 'Hidcote'", "P19"),
    CatalogItem("LAV-MUN-P13", "Lavandula angustifolia 'Munstead'", "P13"),
    CatalogItem("HYD-ANN-C5", "Hydrangea arborescens 'Annabelle'", "C5"),
    CatalogItem("BUX-SEM-P15", "Buxus sempervirens", "P15"),
    CatalogItem("ACE-PAL-C7", "Acer palmatum 'Bloodgood'", "C7"),
    CatalogItem("PRU-LAU-C5", "Prunus laurocerasus 'Novita'", "C5"),
    CatalogItem("PRU-ROT-C10", "Prunus laurocerasus 'Rotundifolia'", "C10"),
]


def matcher():
    return CatalogMatcher(ITEMS, {"C1": {normalize("lavendel blauw 19"): "LAV-HID-P19", normalize("H-20931"): "HYD-ANN-C5"}})


def test_normalize():
    assert normalize("Fächerahorn  ROT!") == "facherahorn rot"


def test_parse_pot():
    assert parse_pot("Annabelle 5 liter") == "C5"
    assert parse_pot("Photinia Red Robin 3L") == "C3"
    assert parse_pot("lavender P19") == "P19"
    assert parse_pot("buxus 15") == "P15"
    assert parse_pot("Rozanne") is None


def test_alias_wins():
    m = matcher().match("240 lavendel blauw 19", "C1")
    assert (m.code, m.status, m.method) == ("LAV-HID-P19", "ok", "alias")
    assert matcher().match("H-20931 Hortensie Annabelle 5L", "C1").code == "HYD-ANN-C5"


def test_alias_belongs_to_one_customer():
    assert matcher().match("lavendel blauw 19", "OTHER").method != "alias"


def test_fuzzy_uses_pot_size():
    m = matcher().match("Annabelle 5 liter")
    assert (m.code, m.status) == ("HYD-ANN-C5", "ok")


def test_llm_code_must_exist():
    m = matcher().match("something", llm_code="NOPE-123")
    assert m.code is None and m.status == "unknown"


def test_llm_code_with_low_similarity_goes_to_review():
    m = matcher().match("Fächerahorn rot 7L", llm_code="ACE-PAL-C7")
    assert m.code == "ACE-PAL-C7" and m.status == "check"


def test_llm_alternatives_kept_for_ambiguous_items():
    m = matcher().match("laurier", llm_alternatives=["PRU-LAU-C5", "PRU-ROT-C10"])
    assert m.code is None and m.alternatives[:2] == ["PRU-LAU-C5", "PRU-ROT-C10"]
