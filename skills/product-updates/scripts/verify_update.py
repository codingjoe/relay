#!/usr/bin/env python3
"""Validate a relay product update in the Captain's log format."""

import re
import struct
import sys
from pathlib import Path

REQUIRED_KEYS = ("name", "description", "image", "author", "date")
EXPECTED_SIZE = (1280, 640)
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
STARDATE_RE = re.compile(r"^## Stardate (\d{4})\.(\d{3}): \S")
HEADLINE_RE = re.compile(r"^# Captain's log, stardate \d{4}\.\d{3}$", re.MULTILINE)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
SLUG_RE = re.compile(r"\d{4}-\d{2}")
# mdformat rewrites `---` as a long underscore run, so accept either form.
DIVIDER_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
BANNED = {"\u2014": "em dash", "\u2013": "en dash", ";": "semicolon"}


class NotAPngError(ValueError):
    """Signal a file that does not start with a PNG header."""


def report(message: str) -> None:
    """Write one line to standard output."""
    sys.stdout.write(f"{message}\n")


def png_size(path: Path) -> tuple[int, int]:
    """Return the pixel size of a PNG without an image library."""
    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise NotAPngError
    return struct.unpack(">II", header[16:24])


def prose_without_code(text: str) -> str:
    """Return text with fenced blocks and inline code removed."""
    fence = "`" * 3
    text = re.sub(f"{fence}.*?{fence}", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`]*`", "", text)


def parse_stardate(line: str) -> tuple[int, int] | None:
    """Return the year and day of year of a stardate heading, else `None`."""
    found = STARDATE_RE.match(line)
    return (int(found[1]), int(found[2])) if found else None


def code_mask(lines: list[str]) -> list[bool]:
    """Mark lines that are outside fenced code blocks."""
    mask = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            mask.append(False)
            in_fence = not in_fence
        else:
            mask.append(not in_fence)
    return mask


def read_frontmatter(
    lines: list[str],
) -> tuple[dict[str, str], list[str], list[str]]:
    """Return the metadata, the body lines, and any structure problems."""
    if not lines or lines[0].strip() != "---":
        return {}, lines, ["missing frontmatter"]
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return {}, lines, ["unterminated frontmatter"]
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()
    return metadata, lines[end + 1 :], []


def check_image(image_path: Path, label: str, problems: list[str]) -> None:
    """Record a missing image, a non-PNG file, or a wrong size."""
    if not image_path.is_file():
        problems.append(f"missing image: {label}")
        return
    try:
        size = png_size(image_path)
    except NotAPngError:
        problems.append(f"{label}: not a PNG file")
        return
    if size != EXPECTED_SIZE:
        width, height = size
        problems.append(f"{label} is {width}x{height}, expected 1280x640")


def check_frontmatter(
    metadata: dict[str, str],
    path: Path,
    problems: list[str],
) -> None:
    """Require the metadata keys and a PNG for the social image."""
    problems.extend(
        f"frontmatter is missing {key}"
        for key in REQUIRED_KEYS
        if not metadata.get(key)
    )
    date = metadata.get("date", "")
    if date and not DATE_RE.fullmatch(date):
        problems.append("frontmatter date must be YYYY-MM-DD")
    image = metadata.get("image", "")
    if image and not image.startswith("images/"):
        problems.append("frontmatter image must start with images/")
    elif image:
        check_image((path.parent / image).resolve(), image, problems)


def check_headline(body: str, problems: list[str]) -> None:
    """Require the stardate headline."""
    if not HEADLINE_RE.search(body):
        problems.append("missing the Captain's log headline")


def check_section_images(
    body_lines: list[str],
    mask: list[bool],
    heading_indexes: list[int],
    problems: list[str],
) -> None:
    """Require a screenshot above every heading."""
    non_empty = [
        (i, line.strip())
        for i, line in enumerate(body_lines)
        if mask[i] and line.strip()
    ]
    for index in heading_indexes:
        before = [line for line_index, line in non_empty if line_index < index]
        if not before or not IMAGE_RE.fullmatch(before[-1]):
            title = body_lines[index].removeprefix("## ")
            problems.append(f"section '{title}' does not start with an image")


def check_stardates(heading_lines: list[str], problems: list[str]) -> None:
    """Require ascending, unique stardates except on the supplemental log."""
    entries = [
        (line, parse_stardate(line))
        for line in heading_lines
        if not line.startswith("## Supplemental log")
    ]
    stardates = [stardate for _, stardate in entries if stardate]
    problems.extend(
        f"section heading is not a stardate: {line}"
        for line, stardate in entries
        if stardate is None
    )
    if stardates != sorted(stardates):
        problems.append("stardates are not in ascending order")
    if len(stardates) != len(set(stardates)):
        problems.append("stardates are not unique")


def check_images(path: Path, body: str, problems: list[str]) -> None:
    """Require alt text, a file, and the exact size for every image."""
    for alt, source in IMAGE_RE.findall(body):
        if not alt.strip():
            problems.append(f"image {source} has no alt text")
        check_image((path.parent / source).resolve(), source, problems)


def last_body_line(body_lines: list[str], mask: list[bool]) -> str:
    """Return the last line outside a fenced block."""
    return next(
        (
            body_lines[i].strip()
            for i in range(len(body_lines) - 1, -1, -1)
            if mask[i] and body_lines[i].strip()
        ),
        "",
    )


def check_dividers(
    body_lines: list[str],
    mask: list[bool],
    heading_indexes: list[int],
    problems: list[str],
) -> None:
    """Require one divider per gap and no divider at the end."""
    dividers = [
        i
        for i, line in enumerate(body_lines)
        if mask[i] and DIVIDER_RE.fullmatch(line.strip())
    ]
    expected = len(heading_indexes) - 1
    if len(dividers) != expected:
        problems.append(f"expected {expected} section dividers, found {len(dividers)}")
    last = last_body_line(body_lines, mask)
    if DIVIDER_RE.fullmatch(last):
        problems.append("the file ends with a divider")
    elif last != "Captain out.":
        problems.append("the file does not end with 'Captain out.'")


def check_prose(text: str, problems: list[str]) -> None:
    """Record banned punctuation in prose, ignoring code."""
    prose = prose_without_code(text)
    problems.extend(
        f"found a {name}" for character, name in BANNED.items() if character in prose
    )


def report_result(
    path: Path,
    sections: int,
    screenshots: int,
    problems: list[str],
) -> int:
    """Print every problem or the summary, and return the exit code."""
    if problems:
        for problem in problems:
            report(f"FAIL {problem}")
        return 1
    report(f"OK {path.name}: {sections} sections, {screenshots} screenshots")
    report("OK frontmatter, stardates, image-before-headline, 1280x640, dividers")
    report("OK no em dashes, no en dashes, no semicolons, closing line")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        report("usage: verify_update.py <path-to-update.md>")
        return 2

    path = Path(sys.argv[1])
    if not path.is_file():
        report(f"FAIL {path} not found")
        return 1

    text = path.read_text(encoding="utf-8")
    metadata, body_lines, problems = read_frontmatter(text.splitlines())
    check_frontmatter(metadata, path, problems)

    mask = code_mask(body_lines)
    body = "\n".join(line for i, line in enumerate(body_lines) if mask[i])
    check_headline(body, problems)

    heading_indexes = [
        i for i, line in enumerate(body_lines) if mask[i] and line.startswith("## ")
    ]
    if not heading_indexes:
        problems.append("no sections found")
    check_section_images(body_lines, mask, heading_indexes, problems)
    check_stardates([body_lines[i] for i in heading_indexes], problems)
    check_images(path, body, problems)
    check_dividers(body_lines, mask, heading_indexes, problems)
    check_prose(text, problems)

    if SLUG_RE.fullmatch(path.stem) is None:
        problems.append(f"file name '{path.name}' should look like YYYY-MM.md")

    return report_result(
        path,
        len(heading_indexes),
        len(IMAGE_RE.findall(body)),
        problems,
    )


if __name__ == "__main__":
    raise SystemExit(main())
