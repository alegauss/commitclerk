"""What this repository's own history says a commit here should look like.

Pure counting over past commit records: no git (that is `gitio`), no network.
Every generator in this niche writes a *generic* well-formed message. This module
is how the tool writes one that belongs in **your** history instead: it measures
the types, scopes, body shape, language and trailers the repo actually uses, and
`prompt` injects the result as a short "house style" block.

Silence is the default when the evidence is thin. A fingerprint derived from four
commits would teach the model the repo's own first mistakes.
"""

from __future__ import annotations

import re
import unicodedata

# 200 is enough to see a convention and short enough that `git log` stays instant.
HISTORY_DEPTH = 200
# The whole block, header and footer included. Subtracted from the diff budget by
# the caller rather than added on top of it.
MAX_HOUSE_STYLE_CHARS = 600
# Below this a "convention" is an accident.
MIN_COMMITS = 5
# ASCII record separator: it cannot occur in a commit message, unlike a newline.
RECORD_SEP = "\x1e"

_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z0-9]{1,11})(?:\((?P<scope>[^()\n]{1,40})\))?!?:\s+\S"
)
_BULLET_RE = re.compile(r"^\s*([-*•])\s+\S")
_TRAILER_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z-]{1,30}):\s+\S")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Distinctive markers, not full stopword lists. Portuguese and Spanish share so
# much that a naive frequency count reliably picks the neighbour, so each set is
# weighted towards words that are rare or absent in the other four. Accents are
# folded before matching, which is why the entries are unaccented.
_LANGUAGE_WORDS = {
    "English": {
        "the", "and", "with", "for", "from", "when", "that", "this", "into",
        "add", "adds", "fix", "fixes", "remove", "update", "make", "use",
        "only", "also", "new", "support", "instead", "keep",
    },
    # "corrige", "para" and "ajusta" are spelled identically in Portuguese,
    # Spanish and (the first) French, so they appear in none of the three: a
    # marker shared by the languages it has to separate only produces a tie.
    "Portuguese": {
        "nao", "com", "dos", "das", "uma", "ao", "aos", "pelo", "pela",
        "adiciona", "atualiza", "melhora", "remocao", "arquivo",
        "mensagem", "versao", "tambem", "quando",
    },
    "Spanish": {
        "anade", "anadir", "elimina", "mejora", "los", "las", "del", "hacia",
        "archivo", "mensaje", "version", "tambien", "cuando", "actualiza", "una",
    },
    "French": {
        "ajoute", "supprime", "les", "des", "une", "pour", "avec",
        "dans", "fichier", "sur", "lors", "vers", "aussi", "nouvelle",
    },
    "German": {
        "und", "der", "die", "das", "fur", "mit", "von", "nicht", "ein", "eine",
        "auf", "hinzu", "behebt", "entfernt", "aktualisiert", "datei", "wenn",
    },
}


def split_records(text: str) -> list[str]:
    """Split the raw `git log` output into one record per commit."""
    return [record.strip("\n") for record in text.split(RECORD_SEP) if record.strip()]


def parse_commit(record: str) -> tuple[str, str]:
    """One record's subject line and its body."""
    subject, _, body = record.partition("\n")
    return subject.strip(), body.strip("\n")


def subject_type_scope(subject: str) -> tuple[str | None, str | None]:
    """The Conventional Commits type and scope of a subject, if it has them."""
    match = _CONVENTIONAL_RE.match(subject)
    if not match:
        return None, None
    scope = (match.group("scope") or "").strip().lower()
    return match.group("type").lower(), scope or None


def strip_prefix(subject: str) -> str:
    """A subject without its `type(scope):` prefix, for language scoring.

    `fix:` is English in every repository on earth, so leaving the prefix in makes
    every history look English.
    """
    match = _CONVENTIONAL_RE.match(subject)
    return subject[match.end() - 1:].strip() if match else subject


def body_shape(body: str) -> str:
    """Whether one commit body is "bullets", "prose" or "none"."""
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        return "none"
    if any(_BULLET_RE.match(line) for line in lines):
        return "bullets"
    return "prose"


def bullet_marker(body: str) -> str | None:
    """The character this body bullets with, or None if it is not bulleted."""
    for line in body.splitlines():
        match = _BULLET_RE.match(line)
        if match:
            return match.group(1)
    return None


def trailer_keys(body: str) -> set:
    """Trailer keys in a body's final paragraph: {"Refs"}, {"Co-authored-by"}, ...

    Only the last paragraph, and only when *every* line in it is a trailer —
    otherwise prose like "Note: this is temporary" is counted as a convention the
    repo does not have.
    """
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    if not paragraphs:
        return set()
    keys = set()
    for line in paragraphs[-1].splitlines():
        if not line.strip():
            continue
        match = _TRAILER_RE.match(line)
        if not match:
            return set()
        keys.add(match.group("key"))
    return keys


def _fold(text: str) -> str:
    """Lowercased and stripped of accents, so "não" and "nao" are one word."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _ranked(values) -> list:
    """(value, count) pairs, most frequent first, ties broken alphabetically."""
    counts: dict = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))


def dominant_language(subjects: list[str]) -> str | None:
    """The language these subjects are written in, or None when it is not clear.

    Deliberately abstains rather than guesses: telling the model a Portuguese repo
    writes Spanish is worse than saying nothing about language at all. The winner
    must both double the runner-up and be supported by a quarter of the subjects.
    """
    if not subjects:
        return None
    scores = {name: 0 for name in _LANGUAGE_WORDS}
    for subject in subjects:
        words = set(_WORD_RE.findall(_fold(strip_prefix(subject))))
        for name, markers in _LANGUAGE_WORDS.items():
            if words & markers:
                scores[name] += 1
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    (best, top), (_, runner_up) = ranked[0], ranked[1]
    if top < max(2, len(subjects) * 0.25) or top < runner_up * 2:
        return None
    return best


def known_scopes(records: list[str]) -> list[str]:
    """The scopes this repo's recent commits actually use, most frequent first.

    The same measurement the house-style block reports, handed to scope inference
    (`files.scope_note`) so observation and inference cannot contradict each other.
    An empty list is a finding, not a failure: this repo does not use scopes.
    """
    scopes = [
        scope
        for scope in (subject_type_scope(parse_commit(r)[0])[1] for r in records)
        if scope
    ]
    return [name for name, _ in _ranked(scopes)]


def _facts(commits: list) -> list[str]:
    """The house-style observations, most useful first."""
    subjects = [subject for subject, _ in commits]
    bodies = [body for _, body in commits]
    parsed = [subject_type_scope(s) for s in subjects]
    types = [t for t, _ in parsed if t]
    scopes = [s for _, s in parsed if s]

    lines = []
    share = round(100 * len(types) / len(subjects))
    if types:
        lines.append(
            f"- {share}% of subjects use a Conventional Commits prefix; types in use: "
            + ", ".join(f"{name} {n}" for name, n in _ranked(types)[:6])
            + "."
        )
    else:
        lines.append(
            "- Subjects do NOT use Conventional Commits prefixes; do not add one."
        )
    if scopes:
        lines.append(
            "- Scopes in use: "
            + ", ".join(f"{name} {n}" for name, n in _ranked(scopes)[:8])
            + "."
        )

    shapes = _ranked(body_shape(b) for b in bodies)
    dominant_shape, count = shapes[0]
    body_line = f"- Bodies are usually {dominant_shape} ({round(100 * count / len(bodies))}%)"
    if dominant_shape == "bullets":
        markers = _ranked(m for m in (bullet_marker(b) for b in bodies) if m)
        body_line += f", bulleted with '{markers[0][0]}'"
    lines.append(body_line + ".")

    language = dominant_language(subjects)
    if language:
        lines.append(f"- Subjects are written in {language}; write this message in it too.")

    lengths = sorted(len(s) for s in subjects)
    lines.append(f"- Median subject length: {lengths[len(lengths) // 2]} characters.")

    trailers = _ranked(k for body in bodies for k in trailer_keys(body))
    if trailers:
        lines.append(
            "- Trailers in use: " + ", ".join(name for name, _ in trailers[:4]) + "."
        )
    return lines


def house_style(records: list[str], *, limit: int = MAX_HOUSE_STYLE_CHARS) -> str:
    """A compact description of how this repo writes commits, or "" if unknowable."""
    commits = [parse_commit(r) for r in records]
    commits = [(subject, body) for subject, body in commits if subject]
    if len(commits) < MIN_COMMITS:
        return ""

    header = f"House style, measured from this repo's last {len(commits)} commits:"
    footer = (
        "Follow it over generic defaults; prefer a type and scope that already "
        "appear above, and introduce a new one only when none fits."
    )
    budget = limit - len(header) - len(footer) - 2
    kept: list[str] = []
    for line in _facts(commits):
        if len(line) + 1 > budget:
            break
        kept.append(line)
        budget -= len(line) + 1
    if not kept:
        return ""
    return "\n".join([header] + kept + [footer])
