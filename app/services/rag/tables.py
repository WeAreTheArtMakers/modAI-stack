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

Supported: Markdown pipe tables with a header and a separator row; range cells written as
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
_NUMBER = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"
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
    return float(token.replace(".", "").replace(",", "."))


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str
    text: str


def quantities(text: str) -> list[Quantity]:
    """Numbers directly followed by a unit, in digits ("40.000 TL'lik", "1,5 kilo") or words ("kırk bin liralık")."""
    tokens = _TOKEN.findall(_lower(text))
    found: list[Quantity] = []
    i = 0
    while i < len(tokens):
        start = i
        value: float | None = None
        if re.fullmatch(_NUMBER, tokens[i]):
            value = _number(tokens[i])
            i += 1
            if i < len(tokens) and tokens[i] in _SCALES:
                value *= _SCALES[tokens[i]]
                i += 1
        elif tokens[i] in _ONES or tokens[i] in _TENS or tokens[i] in _SCALES or tokens[i] == "yüz":
            total, current, seen = 0.0, 0.0, False
            while i < len(tokens):
                word = tokens[i]
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
        unit = _unit(tokens[i]) if i < len(tokens) else None
        if unit == "yıl" and value.is_integer() and 1900 <= value <= 2100:
            unit = None  # a calendar year ("2026 yılında"), not a duration
        if unit:
            found.append(Quantity(value, unit, " ".join(tokens[start:i + 1])))
            i += 1
    return found


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


def parse_tables(text: str) -> list[Table]:
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
        if pipes != columns + 1 or not before.endswith("|"):
            continue
        header_start = cursor
        header = _row(before, header_start, columns)
        if not header:
            continue
        rows: list[list[str]] = []
        position = separator.end()
        while True:
            next_pipe = position
            while next_pipe < len(text) and text[next_pipe] in " \t\r\n":
                next_pipe += 1
            if next_pipe >= len(text) or text[next_pipe] != "|":
                break
            row = _row(text, next_pipe, columns)
            if not row:
                break
            rows.append(row[0])
            position = row[1]
        if rows:
            tables.append(Table(header_start, position, header[0], rows))
    return tables


def _clean(text: str) -> str:
    return " ".join(re.sub(r"[#*>_`|]", " ", text).split())


def _location(text: str, table: Table) -> str:
    """Where a table sits, so tables can be told apart: the document title (when the chunk starts
    with one; it also carries labels such as "ESKİ ... (yürürlükten kalktı)") and the nearest heading
    above the table. Never the tail of the previous paragraph, which the model would repeat."""
    parts = []
    title = re.match(r"\s*#\s+([^#>|*]{3,120}?)\s*(?=[#>|*-]|$)", text)
    title_end = title.end() if title and title.end() <= table.start else -1
    if title_end != -1:
        parts.append(f'document "{_clean(title.group(1))}"')
    heading = text.rfind("#", max(0, table.start - 300), table.start)
    if heading != -1 and heading >= title_end:
        parts.append(f'section "{" ".join(_clean(text[heading: table.start]).split()[:12])}"')
    return ", ".join(parts) or "a table"


def table_lookup(question: str, chunks: list[str]) -> list[str]:
    """Rows whose range column contains a quantity from the question, one line per table."""
    asked = quantities(question)
    if not asked:
        return []
    question_words = set(re.findall(r"[^\W\d_]+", _lower(question)))
    lines: list[str] = []
    for chunk in chunks:
        for table in parse_tables(chunk):
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
                    shown = f"{quantity.text}" + (f" (= {value:g} {unit})" if factor != 1.0 else "")
                    where = _location(chunk, table)
                    # Only rows about the same subject can share a boundary.
                    by_subject: dict[tuple[str, ...], list[list[str]]] = {}
                    for row, parsed in ranges:
                        if parsed and parsed.contains(value):
                            by_subject.setdefault(tuple(_qualifier(row[column])), []).append(row)
                    for matches in by_subject.values():
                        if len(matches) == 1:
                            lines.append(f"- {shown}: in {where}, this value falls in the row \"{table.describe_row(matches[0])}\".")
                        else:
                            rows = " / ".join(f'"{table.describe_row(row)}"' for row in matches)
                            lines.append(
                                f"- {shown}: in {where}, this exact value is on the boundary of the rows {rows}. "
                                "The document does not say which of them applies; do not choose one."
                            )
    return lines
