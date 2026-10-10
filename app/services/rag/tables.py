"""Numbers in a question matched to rows of Markdown tables in the retrieved context.

The chunker joins words with single spaces, so stored chunks hold Markdown tables on one line
("| Tutar | Onaylayan | |---|---| | 25.000 TL'ye kadar | Takım yöneticisi | | ..."). Asked "who
approves 40.000 TL", a small model then often answers from a neighbouring row. ``table_lookup``
parses those tables (one-line or multi-line) and, when the question contains a quantity with a unit
(``3 yıl``, ``40.000 TL``, ``kırk bin lira``, ``7 kg``) and a table column holds ranges in that unit,
names the row that contains the value, or says the value sits on a boundary shared by two rows. The
prompt carries these lines after the context. Deterministic; no extra model call, no data change.

Measured on the fictional demo pack (gemma3:4b, 5 runs each): 3 years -> 16 days went from 1/5 to
5/5 and 40.000 TL -> department director + purchasing from 3/5 to 5/5. Rewriting the tables row by
row without the lookup did not help (0/5 and 0/5), so the context text itself is left unchanged.

When every row that contains a number from the question is part of an unresolved conflict, the
model is not asked at all: ``conflict_answer`` returns a fixed Turkish (or English) answer built from
the table rows. Conflicts are a value exactly on a boundary shared by rows of one table, or tables
with the same columns in different documents giving different rows (e.g. an obsolete and a current
version: without version metadata the system does not pick one). If another table answers the same
number without conflict, the model answers with the lookup lines instead. When a number matches
tables of several documents, only tables whose title, section or columns share a word with the
question count (all of them if none does), so an unrelated table in the same unit does not interfere.

Supported: well-formed Markdown pipe tables (a header and a separator row; a table with a row or
header of the wrong width is ignored entirely); range cells written as
"A–B unit", "A unit'ye kadar", "A unit üzeri" / "A unit'yi aşan" (exclusive), "A unit ve üzeri",
"A unit altında" / "A unit'den az", "A unit ve altı", "en fazla A unit", optionally followed by a
subject ("5.000 TL'yi aşan eğitim" applies only when the question names every subject word); units
TL, yıl, ay, hafta, gün, saat, dakika, kg, km, with years converted when a table counts months. Other
tables (PDF layouts, merged cells), calculations and numbers without a unit are left to the model.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_SEPARATOR = re.compile(r"\|(?:[ \t]*:?-{3,}:?[ \t]*\|)+")
# Turkish grouping ("40.000", "1.250,5"), English grouping ("40,000": a comma followed by groups of
# exactly three digits is read as thousands, never as a three-decimal fraction), or a plain number
# with an optional Turkish decimal comma ("1,5").
_NUMBER = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d{1,3}(?:,\d{3})+(?!\d)|\d+(?:,\d+)?"
_TOKEN = re.compile(rf"{_NUMBER}|[^\W\d_]+(?:['’][^\W\d_]+)?|₺")

_UNITS = (  # longest first: "kilometre" before "kilo"
    ("kilometre", "km"), ("kilogram", "kg"), ("dakika", "dakika"), ("hafta", "hafta"), ("lira", "TL"),
    ("kilo", "kg"), ("sene", "yıl"), ("saat", "saat"), ("yıl", "yıl"), ("gün", "gün"), ("km", "km"),
    ("kg", "kg"), ("tl", "TL"), ("dk", "dakika"), ("₺", "TL"),
)
# Turkish case and derivational suffixes after a unit ("yıldır", "liralık", "saate", "kilosu",
# "yılında"), so "yıldız", "güncel", "gündem" or "aynı" are not units.
_SUFFIXES = re.compile(r"(?:l[ıiuü]k|[dt][ıiuü]r|n?[dt][ae]n?|y?[ae]|y?[ıiuü]|n?[ıiuü]n|s[ıiuü]|l[ae]r|ç[ıiuü]k|[ğk][ıiuü])*")
_CONVERSIONS = {("yıl", "ay"): 12.0}

_ONES = {"sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9}
_TENS = {"on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80, "doksan": 90}
_SCALES = {"bin": 1_000, "milyon": 1_000_000}


def _lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def _unit(token: str) -> str | None:
    base = re.split(r"['’]", token, maxsplit=1)[0]
    for stem, unit in (*_UNITS, ("ay", "ay")):
        if base.startswith(stem) and _SUFFIXES.fullmatch(base[len(stem):]):
            return unit
    return None


def _number(token: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", token):
        return float(token.replace(",", ""))  # "40,000" in an English question: forty thousand
    return float(token.replace(".", "").replace(",", "."))


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str
    text: str
    number_span: tuple[int, int] = (0, 0)  # character offsets of the number in the question
    unit_span: tuple[int, int] = (0, 0)


def quantities(text: str) -> list[Quantity]:
    """Numbers directly followed by a unit, in digits ("40.000 TL'lik", "1,5 kilo") or words ("kırk
    bin liralık", "on beş iş günü")."""
    lowered = _lower(text)
    tokens = [(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(lowered)]
    found: list[Quantity] = []
    i = 0
    while i < len(tokens):
        start = i
        value: float | None = None
        if re.fullmatch(_NUMBER, tokens[i][0]):
            value = _number(tokens[i][0])
            i += 1
            if i < len(tokens) and tokens[i][0] in _SCALES:
                value *= _SCALES[tokens[i][0]]
                i += 1
        elif tokens[i][0] in _ONES or tokens[i][0] in _TENS or tokens[i][0] in _SCALES or tokens[i][0] == "yüz":
            total, current, seen = 0.0, 0.0, False
            while i < len(tokens):
                word = tokens[i][0]
                if word in _ONES or word in _TENS:
                    current += _ONES.get(word, 0) + _TENS.get(word, 0)
                elif word == "yüz":
                    current = (current or 1) * 100
                elif word in _SCALES:
                    total += (current or 1) * _SCALES[word]
                    current = 0
                elif word == "buçuk" and seen:
                    current += 0.5
                else:
                    break
                seen = True
                i += 1
            value = total + current
        if value is None:
            i += 1
            continue
        number_end = i
        if i + 1 < len(tokens) and tokens[i][0] == "iş" and _unit(tokens[i + 1][0]) == "gün":
            i += 1  # "15 iş günü": business days, counted as days
        unit = _unit(tokens[i][0]) if i < len(tokens) else None
        if unit == "yıl" and value.is_integer() and 1900 <= value <= 2100:
            unit = None  # a calendar year ("2026 yılında"), not a duration
        if unit:
            found.append(Quantity(
                value, unit, " ".join(token for token, _, _ in tokens[start:i + 1]),
                (tokens[start][1], tokens[number_end - 1][2]), (tokens[i][1], tokens[i][2]),
            ))
            i += 1
    return found


def _digits(value: float) -> str:
    if value.is_integer():
        return f"{int(value):,}".replace(",", ".")
    return f"{value:.2f}".rstrip("0").replace(".", ",")


def normalize_quantities(text: str) -> str:
    """For retrieval only: a quantity spoken in words written in digits, as documents write it
    ("üç yıl" -> "3 yıl", "kırk bin liralık" -> "40.000 TL'lik", "on beş iş günü" -> "15 iş
    günü"). Only numbers followed by a unit are touched; the user's question itself is kept as is."""
    if len(_lower(text)) != len(text):
        return text  # offsets would not line up
    out, cursor = [], 0
    for quantity in quantities(text):
        (number_start, number_end), (unit_start, unit_end) = quantity.number_span, quantity.unit_span
        number = text[number_start:number_end]
        if not re.fullmatch(_NUMBER, number.strip()):
            out += [text[cursor:number_start], _digits(quantity.value)]
            cursor = number_end
        unit_word = _lower(text[unit_start:unit_end])
        if unit_word.startswith("lira"):
            out += [text[cursor:unit_start], "TL'lik" if unit_word[4:] in ("lık", "lik") else "TL"]
            cursor = unit_end
    out.append(text[cursor:])
    return "".join(out)


@dataclass(frozen=True)
class Range:
    low: float
    high: float
    low_inclusive: bool
    high_inclusive: bool
    unit: str

    def contains(self, value: float) -> bool:
        above = value > self.low or (self.low_inclusive and value == self.low)
        below = value < self.high or (self.high_inclusive and value == self.high)
        return above and below


_RANGE_NUMBER = rf"({_NUMBER})(?:\s*(bin|milyon))?"
_BETWEEN = re.compile(rf"{_RANGE_NUMBER}\s*([^\W\d_]+(?:['’][^\W\d_]+)?|₺)?\s*(?:–|—|-|ile)\s*{_RANGE_NUMBER}\s*([^\W\d_]+(?:['’][^\W\d_]+)?|₺)")
_SINGLE = re.compile(rf"(en fazla\s+|en az\s+)?{_RANGE_NUMBER}\s*([^\W\d_]+(?:['’][^\W\d_]+)?|₺)\s*(.*)$")


_RELATION_WORDS = {
    "ve", "veya", "ile", "kadar", "üzeri", "üstü", "üzerinde", "üzerindeki", "aşan", "fazla", "daha", "az",
    "altında", "altındaki", "altı", "en", "tam", "arası", "arasında", "bin", "milyon",
}


def _qualifier(cell: str) -> list[str]:
    """Words that narrow a range cell to a subject ("5.000 TL'yi aşan eğitim" -> ["eğitim"])."""
    words = re.findall(r"[^\W\d_]+", _lower(cell))
    return [word for word in words if len(word) >= 3 and word not in _RELATION_WORDS and not _unit(word)]


def _named(term: str, word: str) -> bool:
    """`word` is `term` with Turkish suffixes ("avansı", "eğitime"); long terms also tolerate a changed
    last letter ("kitap" -> "kitabı"), short ones must match exactly ("içi" is not "için")."""
    if word.startswith(term) and _SUFFIXES.fullmatch(word[len(term):]):
        return True
    return len(term) >= 6 and word[:5] == term[:5]


def _applies(cell: str, question_words: set[str]) -> bool:
    """A row narrowed to a subject ("... aşan eğitim") applies only when the question names every
    subject word: "yurt içi avans" does not apply to a question about "yurt dışı avans"."""
    return all(any(_named(term, word) for word in question_words) for term in _qualifier(cell))


def _scaled(number: str, scale: str | None) -> float:
    return _number(number) * (_SCALES[scale] if scale else 1)


def parse_range(cell: str) -> Range | None:
    """A range written in a table cell, or None for plain values ("16 iş günü", "75 TL")."""
    text = _lower(cell.strip())
    between = _BETWEEN.search(text)
    if between:
        first_unit = _unit(between.group(3)) if between.group(3) else None
        unit = _unit(between.group(6))
        if unit and first_unit in (None, unit):
            low, high = _scaled(between.group(1), between.group(2)), _scaled(between.group(4), between.group(5))
            if low < high:
                return Range(low, high, True, True, unit)
        return None
    single = _SINGLE.search(text)
    if not single:
        return None
    prefix, value, unit, rest = single.group(1), _scaled(single.group(2), single.group(3)), _unit(single.group(4)), single.group(5)
    if not unit:
        return None
    if prefix and "fazla" in prefix:
        return Range(-math.inf, value, False, True, unit)
    if prefix:
        return Range(value, math.inf, True, False, unit)
    if re.search(r"\b(?:kadar|ve altı|veya altı|ve daha az)\b", rest):
        return Range(-math.inf, value, False, True, unit)
    if re.search(r"\b(?:ve|veya) (?:üzeri|üstü|daha fazla)\b", rest):
        return Range(value, math.inf, True, False, unit)
    if re.search(r"\b(?:üzeri|üstü|üzerinde\w*|aşan|fazla)\b", rest):
        return Range(value, math.inf, False, False, unit)
    if re.search(r"\b(?:altında\w*|az)\b", rest):
        return Range(-math.inf, value, False, False, unit)
    return None


@dataclass
class Table:
    start: int
    end: int
    headers: list[str]
    rows: list[list[str]]

    def describe_row(self, row: list[str]) -> str:
        return "; ".join(f"{header}: {cell}" for header, cell in zip(self.headers, row))


def _row(text: str, position: int, columns: int) -> tuple[list[str], int] | None:
    """Reads "| a | b |" starting at the opening pipe; a row never spans a line break."""
    cells: list[str] = []
    cursor = position + 1
    for _ in range(columns):
        pipe = text.find("|", cursor)
        if pipe == -1 or "\n" in text[cursor:pipe]:
            return None
        cells.append(text[cursor:pipe].strip())
        cursor = pipe + 1
    return cells, cursor


_EXTRA_CELL = re.compile(r"\s*[^|\n#]{1,80}\|\s*(?:\||$)")  # after the last row: one more cell
_EXTRA_HEADER_CELL = re.compile(r"\|[^|\n#]{1,80}$")  # before the header: one more cell


def parse_tables(text: str) -> list[Table]:
    """Well-formed Markdown pipe tables only: a header and every row with exactly the separator's
    number of cells. A table with a short, long or broken row is not returned at all."""
    tables: list[Table] = []
    for separator in _SEPARATOR.finditer(text):
        if tables and separator.start() < tables[-1].end:
            continue
        columns = separator.group().count("|") - 1
        before = text[: separator.start()].rstrip(" \t")
        if before.endswith("\n"):
            before = before[:-1].rstrip(" \t")
        # The header is the `columns` cells right before the separator, on one line.
        pipes, cursor = 0, len(before) - 1
        while cursor >= 0 and before[cursor] != "\n":
            if before[cursor] == "|":
                pipes += 1
                if pipes == columns + 1:
                    break
            cursor -= 1
        if pipes != columns + 1 or not before.endswith("|") or _EXTRA_HEADER_CELL.search(before, 0, cursor):
            continue  # no header, or a header with more cells than the separator
        header_start = cursor
        header = _row(before, header_start, columns)
        if not header:
            continue
        rows: list[list[str]] = []
        position = separator.end()
        well_formed = True
        while True:
            next_pipe = position
            while next_pipe < len(text) and text[next_pipe] in " \t\r\n":
                next_pipe += 1
            if next_pipe >= len(text) or text[next_pipe] != "|":
                break
            row = _row(text, next_pipe, columns)
            if not row:
                well_formed = False  # a row with fewer cells
                break
            rows.append(row[0])
            position = row[1]
        if _EXTRA_CELL.match(text, position):
            well_formed = False  # the last row had more cells than the header
        if rows and well_formed:
            tables.append(Table(header_start, position, header[0], rows))
    return tables


def _clean(text: str) -> str:
    return " ".join(re.sub(r"[#*>_`|]", " ", text).split())


def _location(text: str, table: Table) -> tuple[str | None, str | None]:
    """The title the chunk starts with and the nearest heading above the table, read from the
    flattened text. Used only to tell which tables a question is about, never shown: a heading
    run together with the next paragraph is not a citable title."""
    title = re.match(r"\s*#\s+([^#>|*]{3,120}?)\s*(?=[#>|*-]|$)", text)
    title_end = title.end() if title and title.end() <= table.start else -1
    heading = text.rfind("#", max(0, table.start - 300), table.start)
    section = " ".join(_clean(text[heading: table.start]).split()[:12]) if heading != -1 and heading >= title_end else None
    return (_clean(title.group(1)) if title_end != -1 else None), section


# Question words too generic to tell tables apart.
_GENERIC_WORDS = {
    "kadar", "için", "hangi", "nedir", "nasıl", "neler", "olan", "olarak", "bana", "benim", "bunu", "şirket",
    "şirketin", "gerekir", "gerekiyor", "olur", "olacak", "yapılır", "miyim", "mıyım", "misin", "mısın", "kimin",
    "kimler", "ediyor", "ediyorum", "tutar", "tutarı", "toplam", "miktar", "miktarı",
}


def _topic_words(text: str) -> set[str]:
    words = re.findall(r"[^\W\d_]+", _lower(text))
    return {
        word for word in words
        if len(word) >= 4 and word not in _GENERIC_WORDS and word not in _ONES and word not in _TENS and not _unit(word)
    }


def _related(question_words: set[str], table_words: set[str]) -> bool:
    """A shared word, suffix-tolerant (first five letters): "aracım" ~ "Aracı", "taşınıyorum" ~ "Taşınma"."""
    return any(q[:5] == w[:5] for q in question_words for w in table_words)


@dataclass
class TableMatch:
    """Rows of one table that contain a quantity from the question (two or more: a shared boundary)."""

    quantity: Quantity
    value: float  # in the table's unit
    unit: str
    source: str | None  # the document's file name from the index (shown); None without metadata
    table: Table
    column: int
    rows: list[list[str]]
    related: bool  # the table's title, section or columns share a word with the question

    def where(self) -> str:
        return f'document "{self.source}"' if self.source else "a table"

    def shown(self) -> str:
        converted = self.quantity.unit != self.unit
        return self.quantity.text + (f" (= {self.value:g} {self.unit})" if converted else "")

    def outputs(self, row: list[str]) -> tuple[tuple[str, str], ...]:
        return tuple((header, cell) for index, (header, cell) in enumerate(zip(self.table.headers, row)) if index != self.column)


def table_matches(question: str, chunks: list[str], sources: list[str] | None = None) -> list[TableMatch]:
    """`sources`: the file name of each chunk (index metadata), shown to say where a row comes from."""
    asked = quantities(question)
    if not asked:
        return []
    question_words = set(re.findall(r"[^\W\d_]+", _lower(question)))
    question_topic = _topic_words(question)
    found: list[TableMatch] = []
    for index, chunk in enumerate(chunks):
        source = sources[index] if sources and index < len(sources) else None
        for table in parse_tables(chunk):
            title, section = _location(chunk, table)
            related = _related(question_topic, _topic_words(" ".join([source or "", title or "", section or "", *table.headers])))
            for column in range(len(table.headers)):
                ranges = [(row, parse_range(row[column])) for row in table.rows]
                units = {parsed.unit for _, parsed in ranges if parsed}
                if sum(1 for _, parsed in ranges if parsed) < 2 or len(units) != 1:
                    continue
                unit = units.pop()
                ranges = [(row, parsed if parsed and _applies(row[column], question_words) else None) for row, parsed in ranges]
                for quantity in asked:
                    factor = 1.0 if quantity.unit == unit else _CONVERSIONS.get((quantity.unit, unit))
                    if factor is None:
                        continue
                    value = quantity.value * factor
                    # Only rows about the same subject can share a boundary.
                    by_subject: dict[tuple[str, ...], list[list[str]]] = {}
                    for row, parsed in ranges:
                        if parsed and parsed.contains(value):
                            by_subject.setdefault(tuple(_qualifier(row[column])), []).append(row)
                    for rows in by_subject.values():
                        found.append(TableMatch(quantity, value, unit, source, table, column, rows, related))
    # Retrieval often brings unrelated tables in the same unit (a 15.000 km service table next to a
    # 300 km relocation table). When some tables share a word with the question, only those count.
    relevant: list[TableMatch] = []
    for quantity in dict.fromkeys(match.quantity for match in found):
        same = [match for match in found if match.quantity == quantity]
        relevant += [match for match in same if match.related] or same
    return relevant


def _conflicts(matches: list[TableMatch]) -> list[list[TableMatch]]:
    """Groups of matches that contradict each other with no rule saying which applies:
    - one table where the value is on a boundary of rows with different values;
    - tables with the same columns in different documents (e.g. an old and a current version)
      giving different values. Without version metadata the system cannot pick one."""
    groups: list[list[TableMatch]] = []
    singles: dict[tuple, list[TableMatch]] = {}
    for match in matches:
        if len(match.rows) > 1:
            if len({match.outputs(row) for row in match.rows}) > 1:
                groups.append([match])
        else:
            key = (match.quantity, tuple(_lower(header) for header in match.table.headers), match.column)
            singles.setdefault(key, []).append(match)
    for same_columns in singles.values():
        if len({m.source for m in same_columns}) > 1 and len({m.outputs(m.rows[0]) for m in same_columns}) > 1:
            groups.append(same_columns)
    return groups


def table_lookup(question: str, chunks: list[str], sources: list[str] | None = None) -> list[str]:
    """Prompt lines: the row that contains each quantity from the question, or the conflict."""
    matches = table_matches(question, chunks, sources)
    lines: list[str] = []
    in_conflict = set()
    for group in _conflicts(matches):
        in_conflict.update(id(match) for match in group)
        if len(group) == 1:
            match = group[0]
            rows = " / ".join(f'"{match.table.describe_row(row)}"' for row in match.rows)
            lines.append(
                f"- {match.shown()}: in {match.where()}, this exact value is on the boundary of the rows {rows}. "
                "The document does not say which of them applies; do not choose one."
            )
        else:
            rows = "; ".join(f'{match.where()}: "{match.table.describe_row(match.rows[0])}"' for match in group)
            lines.append(
                f"- {group[0].shown()}: tables with the same columns in different documents give different rows: {rows}. "
                "The system cannot verify which document is current; do not present either as the answer."
            )
    for match in matches:
        if id(match) not in in_conflict:
            lines.append(f"- {match.shown()}: in {match.where()}, this value falls in the row \"{match.table.describe_row(match.rows[0])}\".")
    return lines


def _number_text(value: float, unit: str) -> str:
    if value.is_integer():
        number = f"{int(value):,}".replace(",", ".")
    else:
        number = f"{value:.2f}".rstrip("0").replace(".", ",")
    return f"{number} {unit}"


def _row_text(match: TableMatch, row: list[str], english: bool) -> str:
    outputs = ", ".join(f"{header}: {cell}" for header, cell in match.outputs(row))
    return f"“{row[match.column]}” row: {outputs}" if english else f"“{row[match.column]}” satırında {outputs}"


def conflict_answer(question: str, chunks: list[str], language: str = "tr", sources: list[str] | None = None) -> str | None:
    """A fixed answer, built from the tables, when every table row that contains a number from the
    question is part of an unresolved conflict (a shared boundary, or documents that disagree).
    The model is not asked: a small model picks one of the rows with confidence. None otherwise,
    including when another table gives a single, unambiguous row for the same number."""
    matches = table_matches(question, chunks, sources)
    groups = _conflicts(matches)
    english = language == "en"
    for quantity in dict.fromkeys(match.quantity for match in matches):
        relevant = [match for match in matches if match.quantity == quantity]
        conflicting = [group for group in groups if group[0].quantity == quantity]
        if sum(len(group) for group in conflicting) != len(relevant):
            continue  # some table answers this number without conflict: leave it to the model
        sentences = []
        for group in conflicting:
            first = group[0]
            value = _number_text(first.value, first.unit)
            if len(group) == 1:
                rows = "; ".join(_row_text(first, row, english) for row in first.rows)
                if english:
                    where = f"the table in {first.source}" if first.source else "the table"
                    sentences.append(f"The document does not settle this: {value} is exactly on the boundary between rows of {where}. {rows}. The document does not say which row includes the boundary value.")
                else:
                    where = f"{first.source} belgesindeki tabloda" if first.source else "getirilen belgedeki tabloda"
                    sentences.append(f"Belge bu soruya kesin bir yanıt vermiyor: {value}, {where} iki satırın tam sınırında. {rows}. Belge, sınır değerin hangi satıra dahil olduğunu belirtmiyor.")
            else:
                if english:
                    rows = "; ".join(f"in {match.source or 'one document'}, {_row_text(match, match.rows[0], True)}" for match in group)
                    sentences.append(f"The retrieved documents disagree for {value}: {rows}. The system cannot verify which document is current.")
                else:
                    rows = "; ".join(f"{match.source or 'bir belgede'}{' içinde' if match.source else ''} {_row_text(match, match.rows[0], False)}" for match in group)
                    sentences.append(f"Getirilen belgeler {value} için farklı bilgi veriyor: {rows}. Sistem hangi belgenin güncel olduğunu doğrulayamıyor.")
        sentences.append("Please confirm with the document owner." if english else "Lütfen belge sahibine doğrulatın.")
        return " ".join(sentences)
    return None
