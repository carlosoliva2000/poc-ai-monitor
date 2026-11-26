"""Comprobaciones de lo que escribe el LLM, antes de publicarlo (deterministas, con pruebas).

Lo aprendido en la rúbrica de los textos: cifras u horas que no estaban en la entrada, ids y
nombres internos, una causa que el incidente no dice, mezclar «ahora» con la apertura, idioma y
longitud. `check_text` devuelve los motivos en inglés (se le pasan al modelo en el reintento);
una lista vacía es que el texto pasa. Cada motivo empieza por un código corto (`number:`, `id:`…)
para contarlos por tipo.
"""

import re
from dataclasses import dataclass

from poc_contracts.enums import IncidentKind

from ..outbox import format_t
from .facts import PromptInput

REPLACEMENTS = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", "​": "",
    "‘": "'", "’": "'", "“": '"', "”": '"',
}  # fmt: skip
NUMBER_RE = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?")
TIME_RE = re.compile(r"\bT\+(\d{2}):(\d{2})\b")
ID_RE = re.compile(
    r"\b(?:gps|rad|met|lnk|bat|gns|apl|mis|det|ai|chk|act|ops|inc|inv|cmd|sim|plr|inj|tcl)-\d+\b"
    r"|\b[A-Z]{2}-\d{2}\b"
)
INTERNAL_RE = re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b|\b[a-z]+(?:_[a-z0-9]+)+\b")
CJK_RE = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
SPANISH = {"el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una", "es", "se", "por",
           "con", "para", "esta", "este", "como", "pero", "su", "al", "lo"}  # fmt: skip
UNITS = ("m", "s", "%", "db", "dbm", "ms", "mps", "m/s", "sigmas", "periods", "km")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
NOW_STRICT = re.compile(r"\b(?:now|currently|right now)\b", re.I)
NOW_LOOSE = re.compile(r"\b(?:now|currently|right now|is|are)\b", re.I)

# Frases con las que un texto nombra una causa; un acierto solo vale si el incidente dice esa causa
# o si la misma frase está en la entrada.
CAUSE_LEXICON: dict[str, tuple[IncidentKind | None, list[str]]] = {
    "spoofing": (IncidentKind.GPS_SPOOFING, [r"spoof\w*", r"(?:fake|false) (?:gps )?signal"]),
    "hijack": (
        IncidentKind.HIJACK,
        [r"hijack\w*", r"someone else", r"taken over", r"another controller"],
    ),  # fmt: skip
    "wind": (
        IncidentKind.WIND,
        [
            r"(?:caused|pushed|blown) by (?:the )?wind",
            r"due to (?:the )?wind",
            r"because of (?:the )?wind",
            r"wind (?:is |was )?(?:pushing|pushed|blowing)",
            r"wind (?:is|was) the (?:\w+ )?cause",
            r"the (?:\w+ )?cause (?:is|was) (?:the )?wind",
        ],
    ),  # fmt: skip
    "dead reckoning": (IncidentKind.DEAD_RECKONING, [r"dead[- ]reckoning"]),
    "jamming": (None, [r"jamm\w*"]),
}

# Límites de longitud por papel: (frases, palabras).
LIMITS = {
    "report_piece": (3, 70),
    "explain": (3, 60),
    "hypothesis": (2, 40),
    "chat": (8, 180),
    "report": (60, 600),
}


@dataclass(frozen=True)
class Verdict:
    text: str  # el texto normalizado, el que se publicaría
    reasons: list[str]

    @property
    def ok(self) -> bool:
        return not self.reasons


MULTILINE_ROLES = frozenset({"chat", "report"})  # conservan los saltos de línea (listas, párrafos)


def normalize(text: str, keep_lines: bool = False) -> str:
    """Sin U+2011 ni espacios raros ni comillas tipográficas; una sola línea (o una por línea
    escrita, en los papeles de chat e informe)."""
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    if not keep_lines:
        return " ".join(text.split())
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def kinds_named(text: str) -> set[IncidentKind]:
    """Las causas que nombra un texto (p. ej. la pregunta del operador), según el léxico."""
    return {
        kind
        for kind, patterns in CAUSE_LEXICON.values()
        if kind is not None and any(re.search(p, text, re.I) for p in patterns)
    }


def _numbers(text: str) -> list[tuple[float, int, str]]:
    """Cifras del texto (valor absoluto, decimales, lo que sigue), sin las horas T+mm:ss."""
    clean = TIME_RE.sub(" ", text)
    out = []
    for m in NUMBER_RE.finditer(clean):
        raw = m.group(0).lstrip("+-")
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        after = clean[m.end() : m.end() + 12].strip().lower().split(" ")[0]
        out.append((float(raw), decimals, after))
    return out


def _allowed(
    entries: list[tuple[float, int, str]], pool: list[float]
) -> list[tuple[float, int, str]]:
    """Las cifras de `entries` que no están en `pool` (con la tolerancia de su redondeo)."""
    bad = []
    for value, decimals, after in entries:
        tolerance = 0.5 * 10**-decimals + 1e-9
        if any(abs(value - known) <= tolerance for known in pool):
            continue
        if decimals == 0 and value <= 3 and after.strip(".,;:)") not in UNITS:
            continue  # «two sources»: un entero pequeño suelto
        bad.append((value, decimals, after))
    return bad


def _pool(text: str) -> list[float]:
    return [v for v, _, _ in _numbers(text)]


def check_text(
    text: str, inp: PromptInput, role: str, extra_kinds: set[IncidentKind] | None = None,
    now_rule: str = "loose",
) -> Verdict:  # fmt: skip
    """Comprueba un texto del asistente contra su entrada. `extra_kinds`: las causas de una
    hipótesis, que el texto puede nombrar."""
    text = normalize(text, keep_lines=role in MULTILINE_ROLES)
    reasons: list[str] = []
    if not text:
        return Verdict(text, ["empty: the text is empty"])

    # 1. ids y nombres internos
    for m in ID_RE.findall(text):
        reasons.append(f"id: do not write ids such as {m}; they go in the fields")
    for m in INTERNAL_RE.findall(text):
        reasons.append(f"internal: do not write code names such as {m}")

    # 2. cifras: todas tienen que estar en la entrada
    known = _pool(inp.current) + _pool(inp.opening) + _pool(inp.text)
    for value, _, _ in _allowed(_numbers(text), known):
        reasons.append(f"number: {value:g} is not in the facts you were given")

    # 3. horas: las de la entrada
    allowed_times = {format_t(t) for t in inp.times}
    for mm, ss in TIME_RE.findall(text):
        if f"T+{mm}:{ss}" not in allowed_times and f"T+{mm}:{ss}" not in inp.text:
            reasons.append(f"time: T+{mm}:{ss} is not one of the times you were given")

    # 4. «ahora» frente a la apertura
    current_pool = _pool(inp.current)
    only_opening = [
        v for v in _pool(inp.opening) if not any(abs(v - c) < 1e-9 for c in current_pool)
    ]
    if only_opening:
        pattern = NOW_STRICT if now_rule == "strict" else NOW_LOOSE
        for sentence in SENTENCE_RE.split(text):
            for value, _, _ in _numbers(sentence):
                if any(abs(value - v) <= 0.05 for v in only_opening) and pattern.search(sentence):
                    code = "now" if NOW_STRICT.search(sentence) else "is"
                    reasons.append(
                        f"now:{code}: {value:g} is from the opening, not from now; say 'at opening'"
                    )

    # 5. causas que el incidente no dice
    allowed = inp.allowed_kinds | (extra_kinds or set())
    lowered_input = inp.text.lower()
    lowered_checks = inp.checks_text.lower()
    for group, (kind, patterns) in CAUSE_LEXICON.items():
        for pattern in patterns:
            for m in re.finditer(pattern, text, re.I):
                hit = m.group(0).lower()
                # una causa con tipo solo vale si el incidente (o su contexto) la dice, aunque la
                # frase aparezca en la entrada: las evidencias pueden traer una causa contraria
                # (p. ej. «spoofed position» en un secuestro); sin tipo (interferencia), si está
                if kind in allowed or hit in lowered_checks:
                    continue
                if kind is None and hit in lowered_input:
                    continue
                reasons.append(f"cause: do not name {group} as a cause; the monitor did not say so")

    # 6. idioma
    if CJK_RE.search(text):
        reasons.append("language: write in English only")
    words = re.findall(r"[a-záéíóúñ']+", text.lower())
    if len(words) >= 4 and sum(w in SPANISH for w in words) / len(words) > 0.2:
        reasons.append("language: write in English only")

    # 7. longitud
    max_sentences, max_words = LIMITS[role]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s]
    if len(sentences) > max_sentences:
        reasons.append(f"length: at most {max_sentences} sentences")
    if len(text.split()) > max_words:
        reasons.append(f"length: at most {max_words} words")
    return Verdict(text, list(dict.fromkeys(reasons)))
