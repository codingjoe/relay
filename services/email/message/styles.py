"""
CSS rewriting for the HTML body preview.

A message body is mail from the outside, so its styles arrive as text. The
engine walks that text instead of parsing it into a full object model, and it
keeps everything it does not have to change, so a modern construct it does
not understand passes through untouched. A preview must not misrepresent a
message, so every rewrite only removes what the caller names: the
declarations, at-rules, media conditions, and selectors of one client
profile, or the color scheme one theme asks for.
"""

import dataclasses
import re

AT_RULE_NAME = re.compile(r"@([\w-]+)")
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
SPACE_OR_COMMENT = re.compile(r"(?:\s+|/\*.*?\*/)+")
IMPORTANT = re.compile(r"!\s*important\s*$", re.IGNORECASE)
COLOR_SCHEME_TERM = re.compile(
    r"\(\s*prefers-color-scheme\s*:\s*([\w-]+)\s*\)", re.IGNORECASE
)
MEDIA_AND = re.compile(r"\band\b", re.IGNORECASE)
MEDIA_PREFIX = re.compile(r"^(\s*@media\b\s*)", re.IGNORECASE)
# At-rules whose block holds declarations rather than nested rules.
DECLARATION_AT_RULES = frozenset({"@font-face", "@page", "@property", "@viewport"})


@dataclasses.dataclass(frozen=True)
class Restrictions:
    """
    The CSS features one emulated email client never applies.

    `properties` names the declarations the client drops, `values` matches
    declaration values it cannot read (a gradient, a `rem` length), and
    `at_rules`, `media_terms`, and `selectors` name the rules and conditions
    it ignores. `custom_properties` drops `--name` definitions, so no
    `var()` call that depends on one can resolve. `reads_media` marks a
    client that ignores `@media` rules entirely.
    """

    properties: frozenset[str] = frozenset()
    values: tuple[str, ...] = ()
    at_rules: frozenset[str] = frozenset()
    media_terms: tuple[str, ...] = ()
    selectors: tuple[str, ...] = ()
    custom_properties: bool = False
    reads_media: bool = True


def filter_styles(
    css_text: str, restrictions: Restrictions, scheme: str | None = None
) -> str:
    """Return a stylesheet without the parts the restrictions and the scheme drop."""
    return rewrite_sheet(css_text, restrictions, scheme)


def filter_declarations(text: str, restrictions: Restrictions) -> str:
    """Return a declaration list without the declarations a client drops."""
    return rewrite_declarations(text, restrictions)


def rewrite_sheet(
    css_text: str, restrictions: Restrictions, scheme: str | None = None
) -> str:
    """Walk a stylesheet and keep every rule the restrictions allow."""
    kept = []
    position = 0
    while position < len(css_text):
        start = skip_space_and_comments(css_text, position)
        kept.append(css_text[position:start])
        if start >= len(css_text):
            break
        stop = find_stop(css_text, start, {";", "{", "}"})
        prelude = css_text[start:stop]
        if stop >= len(css_text):
            kept.append(prelude)
            break
        match css_text[stop]:
            case ";":
                kept.append(rewrite_statement(prelude, restrictions))
                position = stop + 1
            case "}":
                # A stray close brace, from malformed nesting; keep it.
                kept.append(f"{prelude}}}")
                position = stop + 1
            case _:
                end = find_block_end(css_text, stop)
                kept.append(
                    rewrite_block(
                        prelude, css_text[stop + 1 : end], restrictions, scheme
                    )
                )
                position = end + 1
    return "".join(kept)


def rewrite_statement(prelude: str, restrictions: Restrictions) -> str:
    """Return a semicolon-terminated statement, or an empty string to drop it."""
    return "" if at_rule_name(prelude) in restrictions.at_rules else f"{prelude};"


def rewrite_block(
    prelude: str, body: str, restrictions: Restrictions, scheme: str | None = None
) -> str:
    """Return one rule or at-rule block, or an empty string to drop it."""
    name = at_rule_name(prelude)
    match name:
        case "" if any(
            re.search(pattern, prelude, re.IGNORECASE)
            for pattern in restrictions.selectors
        ):
            return ""
        case "":
            declarations = rewrite_declarations(body, restrictions)
            # A rule whose every declaration fell away carries nothing.
            return f"{prelude}{{{declarations}}}" if declarations.strip() else ""
        case _ if name in restrictions.at_rules:
            return ""
        case "@media":
            return rewrite_media(prelude, body, restrictions, scheme)
        case _ if name in DECLARATION_AT_RULES:
            return f"{prelude}{{{rewrite_declarations(body, restrictions)}}}"
        case _:
            return f"{prelude}{{{rewrite_sheet(body, restrictions, scheme)}}}"


def rewrite_media(
    prelude: str, body: str, restrictions: Restrictions, scheme: str | None = None
) -> str:
    """
    Return the media block with the theme and the client applied to its queries.

    A query the theme resolves becomes unconditional or never applies, so the
    block loses its `@media` wrapper and no longer depends on what a client
    reads from one. Everything else follows the client profile.
    """
    prefix_match = MEDIA_PREFIX.match(prelude)
    prefix = prefix_match.group(1) if prefix_match else f"{prelude} "
    conditions = prelude[prefix_match.end() :] if prefix_match else ""
    queries = [
        resolve_media_query(query, restrictions, scheme)
        for query in split_top_level(conditions, ",")
        if query.strip()
    ]
    if "all" in queries:
        return rewrite_sheet(body, restrictions, scheme)
    remaining = [query for query in queries if query != "not all"]
    return (
        f"{prefix}{', '.join(remaining)}{{{rewrite_sheet(body, restrictions, scheme)}}}"
        if remaining
        else ""
    )


def resolve_media_query(
    query: str, restrictions: Restrictions, scheme: str | None
) -> str:
    """Return the conditions one media query still applies under, or never."""
    if scheme and COLOR_SCHEME_TERM.search(query):
        # The theme decides the color scheme, even where the client reads no
        # prefers-color-scheme query of its own.
        return force_color_scheme(query, scheme)
    if not restrictions.reads_media or any(
        re.search(pattern, query, re.IGNORECASE) for pattern in restrictions.media_terms
    ):
        return "not all"
    return query.strip()


def force_color_scheme(query: str, scheme: str) -> str:
    """
    Return the conditions one media query applies under with the scheme forced.

    A query is a conjunction, so the forced scheme drops the condition it
    satisfies, never applies to a query it contradicts, and keeps the rest.
    """
    terms = [term.strip() for term in MEDIA_AND.split(query) if term.strip()]
    matches = {term: COLOR_SCHEME_TERM.fullmatch(term) for term in terms}
    agrees = all(
        match is None or match.group(1).lower() == scheme for match in matches.values()
    )
    remaining = [term for term, match in matches.items() if match is None]
    if not agrees:
        return "not all"
    return " and ".join(remaining) if remaining else "all"


def rewrite_declarations(text: str, restrictions: Restrictions) -> str:
    """Return a declaration list without the declarations a client drops."""
    if find_stop(text, 0, "{") < len(text):
        # A nested rule sits between the declarations; leave the block alone.
        return text
    declarations = [
        rewrite_declaration(part, restrictions) for part in split_top_level(text, ";")
    ]
    return "; ".join(declaration for declaration in declarations if declaration)


def rewrite_declaration(text: str, restrictions: Restrictions) -> str:
    """Return one declaration without what the client cannot apply, or an empty string."""
    name, colon, value = text.partition(":")
    property_name = COMMENT.sub(" ", name).strip().lower()
    if not colon:
        return property_name
    if property_name in restrictions.properties:
        return ""
    if restrictions.custom_properties and property_name.startswith("--"):
        return ""
    important = IMPORTANT.search(value)
    core = (value[: important.start()] if important else value).strip()
    if any(re.search(pattern, core, re.IGNORECASE) for pattern in restrictions.values):
        return ""
    suffix = " !important" if important else ""
    return f"{property_name}: {core}{suffix}"


def at_rule_name(prelude: str) -> str:
    """Return the lowercase at-rule name of a prelude, or an empty string."""
    match = AT_RULE_NAME.match(prelude.strip())
    return f"@{match.group(1).lower()}" if match else ""


def skip_space_and_comments(text: str, index: int) -> int:
    """Return the index of the next token, past whitespace and comments."""
    while match := SPACE_OR_COMMENT.match(text, index):
        index = match.end()
    return index


def skip_string(text: str, index: int) -> int:
    """Return the index after the string that opens at index."""
    quote = text[index]
    index += 1
    while index < len(text):
        match text[index]:
            case "\\":
                index += 2
            case char if char == quote:
                return index + 1
            case _:
                index += 1
    return index


def find_stop(text: str, index: int, stops: set[str] | frozenset[str]) -> int:
    """Return the index of the first stop character outside strings, comments, and groups."""
    depth = 0
    while index < len(text):
        match text[index]:
            case "'" | '"':
                index = skip_string(text, index)
            case "/" if text.startswith("/*", index):
                end = text.find("*/", index + 2)
                index = len(text) if end == -1 else end + 2
            case "(" | "[":
                depth += 1
                index += 1
            case ")" | "]":
                depth = max(depth - 1, 0)
                index += 1
            case char if not depth and char in stops:
                return index
            case _:
                index += 1
    return len(text)


def find_block_end(text: str, index: int) -> int:
    """Return the index of the brace that closes the block opening at index."""
    depth = 0
    while index < len(text):
        match text[index]:
            case "'" | '"':
                index = skip_string(text, index)
            case "/" if text.startswith("/*", index):
                end = text.find("*/", index + 2)
                index = len(text) if end == -1 else end + 2
            case "{":
                depth += 1
                index += 1
            case "}":
                depth -= 1
                if not depth:
                    return index
                index += 1
            case _:
                index += 1
    return len(text)


def split_top_level(text: str, separator: str) -> list[str]:
    """Split text on a separator that sits outside strings, comments, and groups."""
    parts = []
    start = 0
    while (index := find_stop(text, start, {separator})) < len(text):
        parts.append(text[start:index])
        start = index + 1
    parts.append(text[start:])
    return parts
