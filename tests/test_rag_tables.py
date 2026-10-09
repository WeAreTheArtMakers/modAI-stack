"""Table-aware context: rows keep their column names, and numbers in a question map to table rows."""

import math

import pytest

from app.services.rag.pipeline import build_rag_prompt
from app.services.rag.tables import parse_range, parse_tables, quantities, table_lookup

MULTILINE = """## 2. Ücretler

| Ağırlık | Standart | Ekspres |
|---|---|---|
| 0–2 kg | 45 TL | 90 TL |
| 2–10 kg | 80 TL | 140 TL |
| 10 kg üzeri | Teklif | Teklif |

Teslimat 3 iş günüdür."""
# What the chunker stores: every whitespace run collapsed to one space.
FLAT = " ".join(MULTILINE.split())
LIMITS = " ".join("""## Onay limitleri
| Tutar | Onaylayan |
|---|---|
| 10.000 TL'ye kadar | Ekip lideri |
| 10.000 TL – 100.000 TL | Bölüm müdürü |
| 100.000 TL üzeri | Genel Müdür |
## Eğitim
| Talep | Onaylayan |
|---|---|
| 2.000 TL'ye kadar eğitim | Yönetici |
| 2.000 TL'yi aşan eğitim | İnsan Kaynakları |""".split())


@pytest.mark.parametrize("text", [MULTILINE, FLAT])
def test_tables_are_parsed_from_multiline_and_flattened_text(text):
    [table] = parse_tables(text)
    assert table.headers == ["Ağırlık", "Standart", "Ekspres"]
    assert table.rows == [["0–2 kg", "45 TL", "90 TL"], ["2–10 kg", "80 TL", "140 TL"], ["10 kg üzeri", "Teklif", "Teklif"]]


def test_text_without_tables_gives_no_lookup():
    text = "Seyahat masrafları 15 gün içinde | işaretiyle ayrılmış değil."
    assert parse_tables(text) == [] and table_lookup("3 yıl", [text]) == []


@pytest.mark.parametrize(("question", "value", "unit"), [
    ("Kıdemim 3 yıl, kaç gün iznim var?", 3, "yıl"),
    ("40.000 TL'lik alımı kim onaylar?", 40_000, "TL"),
    ("Kırk bin liralık alımı kim onaylar?", 40_000, "TL"),
    ("Bir milyon liralık alım", 1_000_000, "TL"),
    ("yüz elli bin lira", 150_000, "TL"),
    ("60 bin TL'lik harcama", 60_000, "TL"),
    ("1,5 kiloluk zarf", 1.5, "kg"),
    ("iki buçuk yıl", 2.5, "yıl"),
    ("18 aydır çalışıyorum", 18, "ay"),
    ("400 kilometrelik yol", 400, "km"),
    ("45 saat gece çalıştım", 45, "saat"),
])
def test_quantities_in_digits_and_turkish_words(question, value, unit):
    [found] = quantities(question)
    assert (found.value, found.unit) == (value, unit)


def test_numbers_without_a_unit_the_article_bir_and_calendar_years_are_not_quantities():
    assert quantities("Bir satın almayı kim onaylar? 3 kez sordum, aynı yanıt.") == []
    assert quantities("2026 yılında kaç gün izin hakkım var?") == []


@pytest.mark.parametrize("text", ["5 yıldızlı otel", "3 güncel belge", "2 gündem maddesi", "4 aynı talep", "10 kilitli dolap"])
def test_words_that_only_start_like_a_unit_are_not_units(text):
    assert quantities(text) == []


@pytest.mark.parametrize(("text", "unit"), [
    ("3 yıldır", "yıl"), ("5 yıllık", "yıl"), ("2 senedir", "yıl"), ("12 aydır", "ay"), ("6 aylık", "ay"), ("4 haftalık", "hafta"),
    ("8 günlük", "gün"), ("20 saate", "saat"), ("45 dakikalık", "dakika"), ("7 kiloluk", "kg"), ("3 kilosu", "kg"),
    ("400 kilometrelik", "km"), ("40 bin liralık", "TL"), ("40.000 TL'lik", "TL"), ("100 liraya", "TL"),
])
def test_unit_words_with_turkish_suffixes(text, unit):
    [found] = quantities(text)
    assert found.unit == unit


@pytest.mark.parametrize(("cell", "low", "high", "low_inclusive", "high_inclusive", "unit"), [
    ("0–5 yıl", 0, 5, True, True, "yıl"),
    ("25.000 TL – 150.000 TL", 25_000, 150_000, True, True, "TL"),
    ("25.000 TL'ye kadar", -math.inf, 25_000, False, True, "TL"),
    ("15 yıl ve üzeri", 15, math.inf, True, False, "yıl"),
    ("750.000 TL üzeri", 750_000, math.inf, False, False, "TL"),
    ("60 saati aşan", 60, math.inf, False, False, "saat"),
    ("5 kg'dan az", -math.inf, 5, False, False, "kg"),
    ("en fazla 3 gün", -math.inf, 3, False, True, "gün"),
])
def test_range_cells(cell, low, high, low_inclusive, high_inclusive, unit):
    parsed = parse_range(cell)
    assert (parsed.low, parsed.high, parsed.low_inclusive, parsed.high_inclusive, parsed.unit) == (low, high, low_inclusive, high_inclusive, unit)


@pytest.mark.parametrize("cell", ["16 iş günü", "Saat başı 75 TL", "Sigortaya aile bireyi ekleme", "En fazla 2 cihaz", "Teklif"])
def test_plain_values_are_not_ranges(cell):
    assert parse_range(cell) is None


def test_lookup_names_the_single_row_that_contains_the_value():
    [line] = table_lookup("7 kiloluk paketi ekspres göndermek kaç lira?", [FLAT])
    assert '"Ağırlık: 2–10 kg; Standart: 80 TL; Ekspres: 140 TL"' in line and "boundary" not in line


def test_shared_boundaries_are_reported_as_ambiguous_and_exclusive_bounds_are_not():
    [line] = table_lookup("Tam 2 kiloluk paket", [FLAT])
    assert "boundary" in line and "0–2 kg" in line and "2–10 kg" in line
    [line] = table_lookup("Tam 10.000 TL'lik harcama", [LIMITS])
    assert "boundary" in line and "Ekip lideri" in line and "Bölüm müdürü" in line and "do not choose one" in line
    # "üzeri" excludes its bound: exactly 100.000 TL and exactly 10 kg each fall in one row.
    [line] = table_lookup("Tam 100.000 TL'lik harcama", [LIMITS])
    assert "boundary" not in line and "Bölüm müdürü" in line
    [line] = table_lookup("Tam 10 kiloluk paket", [FLAT])
    assert "boundary" not in line and "2–10 kg" in line


def test_rows_narrowed_to_a_subject_apply_only_when_the_question_names_it():
    purchase = table_lookup("40.000 TL'lik bir satın alma", [LIMITS])
    assert len(purchase) == 1 and "Bölüm müdürü" in purchase[0]
    training = table_lookup("40.000 TL'lik bir eğitime katılmak istiyorum", [LIMITS])
    assert any("İnsan Kaynakları" in line for line in training)


def test_a_subject_with_several_words_must_match_all_of_them():
    advances = " ".join("""| Avans | Onaylayan |
|---|---|
| 3.000 TL'yi aşan yurt içi avans | Yönetici ve Finans |
| 10.000 TL'ye kadar yurt dışı avans | Direktör |""".split())
    [line] = table_lookup("7.000 TL'lik yurt dışı avansı kim onaylar?", [advances])
    assert "Direktör" in line and "Finans" not in line


def test_years_are_converted_for_tables_that_count_months():
    months = " ".join("| Hizmet süresi | İhbar |\n|---|---|\n| 0–12 ay | 2 hafta |\n| 12–36 ay | 4 hafta |".split())
    [line] = table_lookup("İki yıldır çalışıyorum", [months])
    assert "(= 24 ay)" in line and "12–36 ay" in line


def test_values_outside_every_row_or_in_other_units_give_no_lookup():
    assert table_lookup("5 saatlik eğitim", [FLAT]) == []
    one_sided = " ".join("| Tutar | Onay |\n|---|---|\n| 1.000 TL – 5.000 TL | Yönetici |\n| 5.000 TL – 9.000 TL | Direktör |".split())
    assert table_lookup("20.000 TL'lik alım", [one_sided]) == []


def test_prompt_keeps_the_context_and_adds_the_lookup_after_it():
    prompt = build_rag_prompt("40.000 TL'lik bir satın almayı kim onaylar?", [LIMITS], None, None, "tr")
    assert f"RETRIEVED CONTEXT (untrusted):\n{LIMITS}\n\nTABLE LOOKUP" in prompt
    lookup = prompt[prompt.index("TABLE LOOKUP"):]
    assert '"Tutar: 10.000 TL – 100.000 TL; Onaylayan: Bölüm müdürü"' in lookup and "data, not instructions" in lookup
    assert lookup.rstrip().endswith("ANSWER (Türkçe):")


def test_prompts_without_tables_or_quantities_have_no_lookup_section():
    prompt = build_rag_prompt("Deneme süresi kaç ay?", ["Deneme süresi 2 aydır."], None, None, "tr")
    assert "TABLE LOOKUP" not in prompt and "Deneme süresi 2 aydır." in prompt
