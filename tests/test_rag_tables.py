"""Table-aware context: rows keep their column names, and numbers in a question map to table rows."""

import math

import pytest

from app.services.rag.pipeline import build_rag_prompt
from app.services.rag.tables import conflict_answer, parse_range, parse_tables, quantities, table_lookup

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


def test_short_subject_words_do_not_match_other_words_and_subjects_never_share_a_boundary():
    advances = " ".join("""| Avans | Onaylayan |
|---|---|
| 3.000 TL'ye kadar yurt içi avans | Yönetici |
| 3.000 TL'yi aşan yurt içi avans | Yönetici ve Finans |
| 10.000 TL'ye kadar yurt dışı avans | Direktör |
| 10.000 TL'yi aşan yurt dışı avans | Direktör ve CFO |""".split())
    # "için" is not "içi": only the "yurt dışı" rows apply.
    [line] = table_lookup("On beş bin liralık yurt dışı avansı için kimin onayı gerekir?", [advances])
    assert "Direktör ve CFO" in line and "boundary" not in line and "Finans" not in line
    # A question naming both subjects gets one line per subject, not a "boundary".
    lines = table_lookup("15.000 TL'lik yurt içi ve yurt dışı avans", [advances])
    assert len(lines) == 2 and not any("boundary" in line for line in lines)


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


def test_lookup_names_the_source_file_from_the_index_never_text_from_the_chunk():
    old = " ".join("""# ESKİ — Ulaşım Kuralları (yürürlükten kalktı)
> Bu sürüm yürürlükten kalkmıştır. Onay süresi 3 iş günüdür.
## 1. Ulaşım aracı
| Mesafe | Ulaşım |
|---|---|
| 0–300 km | Şirket aracı |
| 300 km üzeri | Uçak |""".split())
    [line] = table_lookup("400 kilometrelik yolculuk", [old], ["ESKI-ulasim-v1.md"])
    assert line.startswith('- 400 kilometrelik: in document "ESKI-ulasim-v1.md", this value falls in the row')
    assert "iş günüdür" not in line and "Ulaşım aracı" not in line
    # Without index metadata no title is reconstructed from the text.
    [line] = table_lookup("400 kilometrelik yolculuk", [old])
    assert line.startswith("- 400 kilometrelik: in a table,") and "ESKİ" not in line


# --- Unresolved conflicts: a fixed answer instead of a model answer ---------------------------

def _flat(markdown: str) -> str:
    return " ".join(markdown.split())


LEAVE = _flat("""# İzin Politikası
## Yıllık izin
| Kıdem | Yıllık izin |
|---|---|
| 0–5 yıl | 16 iş günü |
| 5–15 yıl | 21 iş günü |
| 15 yıl ve üzeri | 27 iş günü |""")
EXPENSES = _flat("""# Masraf Prosedürü
| Masraf tutarı | Onaylayan |
|---|---|
| 1.000 TL'ye kadar | Yönetici |
| 1.000 TL üzeri | Finans |""")
TRAVEL_OLD = _flat("""# ESKİ — Ulaşım Kuralları (yürürlükten kalktı)
| Mesafe | Ulaşım |
|---|---|
| 0–300 km | Şirket aracı |
| 300 km üzeri | Uçak |""")
TRAVEL_NEW = _flat("""# Ulaşım Kuralları
| Mesafe | Ulaşım |
|---|---|
| 0–500 km | Şirket aracı veya tren |
| 500 km üzeri | Uçak |""")


def test_a_shared_boundary_gets_a_fixed_turkish_answer_built_from_the_table():
    answer = conflict_answer("Kıdemim tam 5 yıl, kaç gün iznim var?", [LEAVE], sources=["izin-politikasi.md"])
    assert answer.startswith("Belge bu soruya kesin bir yanıt vermiyor: 5 yıl, izin-politikasi.md belgesindeki tabloda")
    assert "“0–5 yıl” satırında Yıllık izin: 16 iş günü" in answer and "“5–15 yıl” satırında Yıllık izin: 21 iş günü" in answer
    assert answer.endswith("Lütfen belge sahibine doğrulatın.")
    english = conflict_answer("Exactly 5 yıl of service", [LEAVE], language="en")
    assert english.startswith("The document does not settle this: 5 yıl is exactly on the boundary")


def test_ordinary_values_and_boundaries_with_the_same_value_are_not_conflicts():
    assert conflict_answer("Kıdemim 3 yıl, kaç gün iznim var?", [LEAVE]) is None
    assert conflict_answer("Kıdemim 20 yıl", [LEAVE]) is None
    same_value = _flat("| Ağırlık | Ücret |\n|---|---|\n| 0–2 kg | 40 TL |\n| 2–5 kg | 40 TL |\n| 5 kg üzeri | 90 TL |")
    assert conflict_answer("Tam 2 kiloluk paket", [same_value]) is None


def test_no_fixed_answer_when_another_table_answers_the_number_without_conflict():
    # 1.000 TL: a boundary in the purchase table but one plain row in the expense table. Which table
    # the question means is left to the model, with both lookup lines.
    purchases = _flat("| Tutar | Onay |\n|---|---|\n| 1.000 TL'ye kadar | Ekip lideri |\n| 1.000 TL – 5.000 TL | Müdür |")
    assert conflict_answer("Tam 1.000 TL'lik harcama", [purchases, EXPENSES]) is None
    lines = table_lookup("Tam 1.000 TL'lik harcama", [purchases, EXPENSES])
    assert any("boundary" in line for line in lines) and any("Masraf tutarı: 1.000 TL'ye kadar" in line for line in lines)


def test_unrelated_tables_in_the_same_unit_do_not_count():
    service = _flat("""# Araç Bakım Aralıkları
| Araç kilometresi | Bakım paketi |
|---|---|
| 0–15.000 km | Temel kontrol |
| 15.000–60.000 km | Ara bakım |""")
    relocation = _flat("""# Taşınma Yardımı
| Taşınma mesafesi | Yardım |
|---|---|
| 50 km'ye kadar | Ödenmez |
| 50–300 km | 15.000 TL |
| 300 km üzeri | 30.000 TL |""")
    answer = conflict_answer("Aracım tam 15.000 kilometrede, hangi bakım yapılır?", [service, relocation])
    assert answer and "Temel kontrol" in answer and "Ara bakım" in answer and "Taşınma" not in answer
    answer = conflict_answer("Tam 50 km uzağa taşınıyorum, yardım alır mıyım?", [relocation, service])
    assert "Ödenmez" in answer and "15.000 TL" in answer and "Temel kontrol" not in answer
    [line] = table_lookup("40.000 kilometredeki aracın bakımı", [service, relocation])
    assert "Ara bakım" in line and "30.000 TL" not in line


def test_same_table_in_two_documents_with_different_values_is_not_resolved():
    names = ["ESKI-ulasim-v1.md", "ulasim-v2.md"]
    answer = conflict_answer("400 kilometrelik yolculukta uçakla gidebilir miyim?", [TRAVEL_OLD, TRAVEL_NEW], sources=names)
    assert answer.startswith("Getirilen belgeler 400 km için farklı bilgi veriyor:")
    assert "ESKI-ulasim-v1.md içinde “300 km üzeri” satırında Ulaşım: Uçak" in answer
    assert "ulasim-v2.md içinde “0–500 km” satırında Ulaşım: Şirket aracı veya tren" in answer
    assert "hangi belgenin güncel olduğunu doğrulayamıyor" in answer
    [line] = table_lookup("400 kilometrelik yolculuk", [TRAVEL_OLD, TRAVEL_NEW], names)
    assert "cannot verify which document is current" in line and "falls in the row" not in line
    # Where both versions agree (600 km: plane in both) there is nothing to resolve.
    assert conflict_answer("600 kilometrelik yolculuk", [TRAVEL_OLD, TRAVEL_NEW], sources=names) is None


@pytest.mark.parametrize("text", [
    _flat("| Tutar | Onay |\n|---|---|\n| 1.000 TL'ye kadar | Ekip lideri | fazla |\n| 1.000 TL – 5.000 TL | Müdür |"),
    "| Tutar | Onay |\n|---|---|\n| 1.000 TL'ye kadar |\n| 1.000 TL – 5.000 TL | Müdür |",
    _flat("| Not | Tutar | Onay |\n|---|---|\n| 1.000 TL'ye kadar | Ekip lideri |\n| 1.000 TL – 5.000 TL | Müdür |"),
])
def test_tables_with_rows_or_headers_of_the_wrong_width_are_not_parsed(text):
    assert parse_tables(text) == []
    assert table_lookup("Tam 1.000 TL'lik harcama", [text]) == [] and conflict_answer("Tam 1.000 TL'lik harcama", [text]) is None


@pytest.mark.asyncio
async def test_retrieval_context_carries_the_fixed_answer_only_for_live_authorized_chunks(monkeypatch):
    from types import SimpleNamespace

    from app.services.rag import pipeline

    class Hit:
        def __init__(self, document_id, text):
            self.payload = {"document_id": document_id, "filename": f"{document_id}.md", "chunk_index": 0, "text": text}
            self.score = 0.9

    hits = [Hit(1, LEAVE), Hit(2, TRAVEL_OLD)]

    class Embeddings:
        async def embed_text(self, _text):
            return [0.1]

    class Qdrant:
        async def search(self, **_kwargs):
            return hits

    class Db:
        def __init__(self, live):
            self.live = live

        async def scalars(self, _statement):
            return SimpleNamespace(all=lambda: self.live)

    monkeypatch.setattr(pipeline, "get_embedding_service", lambda: Embeddings())
    monkeypatch.setattr(pipeline, "qdrant_service", Qdrant())
    monkeypatch.setattr(pipeline, "get_settings", lambda: SimpleNamespace(rag_top_k=3))
    scope = {"organization_id": 1, "workspace_id": 2, "knowledge_base_ids": [3]}

    context = await pipeline.retrieve_rag_context("Kıdemim tam 5 yıl", db=Db([1, 2]), **scope)
    assert context.table_conflict_answer.startswith("Belge bu soruya kesin bir yanıt vermiyor")
    assert [source.document for source in context.sources] == ["1.md", "2.md"]
    # Document 1 deleted since indexing: its table no longer counts.
    context = await pipeline.retrieve_rag_context("Kıdemim tam 5 yıl", db=Db([2]), **scope)
    assert context.table_conflict_answer is None
    context = await pipeline.retrieve_rag_context("Kıdemim 3 yıl", db=Db([1, 2]), **scope)
    assert context.table_conflict_answer is None


def test_spoken_quantities_are_written_as_digits_for_retrieval_only():
    from app.services.rag.tables import normalize_quantities

    assert normalize_quantities("Kıdemim üç yıl, kaç gün yıllık iznim var?") == "Kıdemim 3 yıl, kaç gün yıllık iznim var?"
    assert normalize_quantities("Kırk bin liralık bir satın almayı kim onaylar?") == "40.000 TL'lik bir satın almayı kim onaylar?"
    assert normalize_quantities("On beş iş günü önce mi?") == "15 iş günü önce mi?"
    assert normalize_quantities("İki buçuk yıldır") == "2,5 yıldır"
    # Digits, numbers without a unit and the article "bir" stay as they are.
    for text in ("Kıdemim 3 yıl", "Bir satın almayı kim onaylar?", "Üç kez sordum", "2026 yılında"):
        assert normalize_quantities(text) == text


@pytest.mark.asyncio
async def test_retrieval_searches_the_spoken_and_the_digit_form_and_keeps_each_chunk_once(monkeypatch):
    from types import SimpleNamespace

    from app.services.rag import pipeline

    embedded, searched = [], []

    class Embeddings:
        async def embed_text(self, text):
            embedded.append(text)
            return [float(len(embedded))]

    def hit(point_id, score):
        return SimpleNamespace(id=point_id, score=score, payload={"document_id": point_id, "filename": f"{point_id}.md", "chunk_index": 0, "text": f"chunk {point_id}"})

    class Qdrant:
        async def search(self, *, vector, limit, **_kwargs):
            searched.append(limit)
            # The spoken form finds the leave policy (id 1) lower; the digit form finds it first.
            return [hit(2, 0.63), hit(3, 0.62), hit(1, 0.61)][:limit] if vector == [1.0] else [hit(1, 0.64), hit(2, 0.60), hit(4, 0.59)][:limit]

    class Db:
        async def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [1, 2, 3, 4])

    monkeypatch.setattr(pipeline, "get_embedding_service", lambda: Embeddings())
    monkeypatch.setattr(pipeline, "qdrant_service", Qdrant())
    monkeypatch.setattr(pipeline, "get_settings", lambda: SimpleNamespace(rag_top_k=3))
    context = await pipeline.retrieve_rag_context("Kıdemim üç yıl, kaç gün iznim var?", db=Db(), organization_id=1, workspace_id=2, knowledge_base_ids=[3])
    assert embedded == ["Kıdemim üç yıl, kaç gün iznim var?", "Kıdemim 3 yıl, kaç gün iznim var?"]
    assert [source.document for source in context.sources] == ["1.md", "2.md", "3.md"]  # best score per chunk, top 3
    assert "Kıdemim üç yıl" in context.prompt and "Kıdemim 3 yıl" not in context.prompt  # the question is unchanged

    embedded.clear(); searched.clear()
    await pipeline.retrieve_rag_context("Kıdemim 3 yıl", db=Db(), organization_id=1, workspace_id=2, knowledge_base_ids=[3])
    assert embedded == ["Kıdemim 3 yıl"] and searched == [3]  # nothing to normalize: one search
