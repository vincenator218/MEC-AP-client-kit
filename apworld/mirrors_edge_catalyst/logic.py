"""
Data-driven requirements: which items a location needs.

Nothing here is hardcoded per location. The rules come from `data/requirements.csv`,
which is meant to be filled in from the crowdsourced activity worksheet. A location
with no row needs nothing. See `data/requirements.csv` for the file format; in short:

    location,requires,source,notes
    Side Mission - Drone Works,"Wallrun & (Climb Up | Ledge Hang)",worksheet row 5,
    1316023,"Springboard, MAG Rope",,                 <- by location id; ',' means AND
    category:Billboard Hack,Climb Up,,                 <- default for a whole category
    GridLeak - Anchor 017,Double Wallrun,,             <- one leak; feeds the count checks

Expression grammar:

    expr   := and ('|' and)*
    and    := atom (('&' | ',') atom)*
    atom   := '(' expr ')' | ITEM [':' COUNT] | '"' ITEM '"' [':' COUNT] | 'nothing'

ITEM is an item name from data.ITEMS or an alias from `data/aliases.json`
(skill-tree names, "Double Wallrun" -> "Progressive Wallrun:2", ...). Quote a name
that contains a comma. Unknown names are an error, raised when the file is loaded,
so a typo cannot silently make a location free.
"""
from __future__ import annotations

import csv
import io
import json
import pkgutil
from dataclasses import dataclass
from typing import Callable, Iterable, Union

from .data import (GRIDLEAK_CATEGORY, GRIDLEAKS_BY_DISTRICT, ITEMS, KIT_LOCATION_ROWS,
                   LOCATIONS, LOCATIONS_BY_ID)

_PKG = __name__.rpartition(".")[0]


class RequirementError(ValueError):
    pass


# ------------------------------------------------------------------------ the AST
@dataclass(frozen=True)
class Has:
    item: str
    count: int = 1


@dataclass(frozen=True)
class All:
    parts: tuple["Expr", ...]


@dataclass(frozen=True)
class Any:
    parts: tuple["Expr", ...]


Expr = Union[Has, All, Any]
NOTHING = All(())


def items_in(expr: Expr) -> set[str]:
    if isinstance(expr, Has):
        return {expr.item}
    return set().union(*(items_in(p) for p in expr.parts)) if expr.parts else set()


def evaluate(expr: Expr, have: Callable[[str, int], bool]) -> bool:
    """Evaluate against any `have(item, count)`; the world passes CollectionState.has."""
    if isinstance(expr, Has):
        return have(expr.item, expr.count)
    if isinstance(expr, All):
        return all(evaluate(p, have) for p in expr.parts)
    return any(evaluate(p, have) for p in expr.parts)


def to_text(expr: Expr) -> str:
    if isinstance(expr, Has):
        return expr.item if expr.count == 1 else f"{expr.item}:{expr.count}"
    if not expr.parts:
        return "nothing"
    sep = " & " if isinstance(expr, All) else " | "
    return "(" + sep.join(to_text(p) for p in expr.parts) + ")"


# ------------------------------------------------------------------------- parser
def load_aliases() -> dict[str, str]:
    raw = pkgutil.get_data(_PKG, "data/aliases.json")
    data = json.loads(raw.decode("utf-8")) if raw else {}
    out = {i.flag.casefold(): name for name, i in ITEMS.items() if i.flag}
    out.update({k.casefold(): v for k, v in data.items() if not k.startswith("_")})
    for k, v in out.items():
        if v.partition(":")[0] not in ITEMS:
            raise RequirementError(f"alias {k!r} points at unknown item {v!r}")
    return out


def _tokens(text: str) -> list[str]:
    out, buf, i = [], "", 0
    while i < len(text):
        c = text[i]
        if c == '"':
            j = text.find('"', i + 1)
            if j < 0:
                raise RequirementError(f"unclosed quote in {text!r}")
            out.append("\0" + text[i + 1:j])          # \0 marks a quoted name
            i = j + 1
            continue
        if c in "()&|,":
            if buf.strip():
                out.append(buf.strip())
            buf = ""
            out.append(c)
        else:
            buf += c
        i += 1
    if buf.strip():
        out.append(buf.strip())
    return out


class _Parser:
    def __init__(self, text: str, aliases: dict[str, str]):
        self.text = text
        self.toks = _tokens(text)
        self.pos = 0
        self.aliases = aliases

    def parse(self) -> Expr:
        if not self.toks:
            return NOTHING
        e = self._or()
        if self.pos != len(self.toks):
            raise RequirementError(f"unexpected {self.toks[self.pos]!r} in {self.text!r}")
        return e

    def _peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def _or(self) -> Expr:
        parts = [self._and()]
        while self._peek() == "|":
            self.pos += 1
            parts.append(self._and())
        return parts[0] if len(parts) == 1 else Any(tuple(parts))

    def _and(self) -> Expr:
        parts = [self._atom()]
        while self._peek() in ("&", ","):
            self.pos += 1
            parts.append(self._atom())
        return parts[0] if len(parts) == 1 else All(tuple(parts))

    def _atom(self) -> Expr:
        t = self._peek()
        if t is None:
            raise RequirementError(f"expression ends early: {self.text!r}")
        self.pos += 1
        if t == "(":
            e = self._or()
            if self._peek() != ")":
                raise RequirementError(f"missing ')' in {self.text!r}")
            self.pos += 1
            return e
        if t in ")&|,":
            raise RequirementError(f"unexpected {t!r} in {self.text!r}")
        return self._item(t)

    def _item(self, tok: str) -> Expr:
        quoted = tok.startswith("\0")
        tok = tok.lstrip("\0")
        count = 1
        if not quoted and ":" in tok:
            tok, _, n = tok.rpartition(":")
            tok = tok.strip()
            if not n.strip().isdigit():
                raise RequirementError(f"bad count in {self.text!r}")
            count = int(n)
        elif quoted:
            rest = self._peek()
            if rest is not None and rest.startswith(":") and rest[1:].strip().isdigit():
                count = int(rest[1:])
                self.pos += 1
        if tok.casefold() in ("nothing", "none", "nothing needed"):
            return NOTHING
        name = tok
        if name not in ITEMS:
            target = self.aliases.get(name.casefold())
            if target is None:
                raise RequirementError(f"unknown item {tok!r} in {self.text!r}")
            name, _, n = target.partition(":")
            if n:
                count = max(count, int(n))
        return Has(name, count)


def parse(text: str, aliases: dict[str, str] | None = None) -> Expr:
    return _Parser(text, load_aliases() if aliases is None else aliases).parse()


# ------------------------------------------------------------------- the table
_ANY_LOCATION = "*"


class Requirements:
    """Resolved requirements for every location, plus per-leak ones for the counts.

    Precedence, most specific first: a row naming the location (by name or id),
    then `category:<Category>`, then `*`, then nothing.
    """

    def __init__(self, rows: Iterable[dict], aliases: dict[str, str] | None = None):
        aliases = load_aliases() if aliases is None else aliases
        self.by_key: dict[str, Expr] = {}
        kit_by_id = {str(r["id"]): name for name, r in KIT_LOCATION_ROWS.items()}
        world_by_id = {str(i): l.name for i, l in LOCATIONS_BY_ID.items()}
        for line, row in enumerate(rows, start=2):
            key = (row.get("location") or "").strip()
            if not key or key.startswith("#"):
                continue
            if key.isdigit():
                key = kit_by_id.get(key) or world_by_id.get(key) or ""
                if not key:
                    raise RequirementError(f"line {line}: no location with id {row['location']}")
            elif not (key == _ANY_LOCATION or key.startswith("category:")
                      or key in LOCATIONS or key in KIT_LOCATION_ROWS):
                raise RequirementError(f"line {line}: unknown location {key!r}")
            try:
                self.by_key[key] = parse(row.get("requires") or "", aliases)
            except RequirementError as e:
                raise RequirementError(f"line {line}: {e}") from None

    def for_kit_row(self, name: str, category: str) -> Expr:
        return (self.by_key.get(name)
                or self.by_key.get(f"category:{category}")
                or self.by_key.get(_ANY_LOCATION)
                or NOTHING)

    def for_location(self, name: str) -> Expr:
        loc = LOCATIONS[name]
        if loc.parent and name not in self.by_key:
            return self.for_location(loc.parent)      # a dash's stars need what the dash needs
        return self.for_kit_row(name, loc.category)

    def gridleak_groups(self, district: str) -> list[tuple[Expr, int]]:
        """The district's leaks grouped by identical requirement: [(expr, how many)].

        A count check "N leaks in district D" is reachable when the leaks you can
        reach number at least N, so its rule just sums these groups.
        """
        groups: dict[Expr, int] = {}
        for r in GRIDLEAKS_BY_DISTRICT[district]:
            e = self.for_kit_row(r["name"], GRIDLEAK_CATEGORY)
            groups[e] = groups.get(e, 0) + 1
        return list(groups.items())


def load_requirements(text: str | None = None) -> Requirements:
    if text is None:
        raw = pkgutil.get_data(_PKG, "data/requirements.csv")
        text = raw.decode("utf-8-sig") if raw else ""
    return Requirements(csv.DictReader(io.StringIO(text)))
