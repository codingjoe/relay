"""Tests for the CSS rewriting of the body preview."""

from services.email.message import styles

RESTRICTIONS = styles.Restrictions(
    properties=frozenset({"position", "box-shadow"}),
    values=(r"^(?:inline-)?(?:flex|grid)$", r"[\d.]+rem\b"),
    at_rules=frozenset({"@font-face", "@import"}),
    media_terms=(r"\bhover\b",),
    selectors=(r"::?hover\b",),
    custom_properties=True,
)


def test_filter_declarations__drops_a_named_property():
    assert (
        styles.filter_declarations("color: red; position: absolute", RESTRICTIONS)
        == "color: red"
    )


def test_filter_declarations__keeps_important():
    assert (
        styles.filter_declarations("color: red !important", RESTRICTIONS)
        == "color: red !important"
    )


def test_filter_declarations__drops_a_value_pattern():
    assert styles.filter_declarations("display: flex", RESTRICTIONS) == ""
    assert styles.filter_declarations("font-size: 1rem", RESTRICTIONS) == ""


def test_filter_declarations__drops_a_custom_property():
    assert (
        styles.filter_declarations("--brand: #f00; color: var(--brand)", RESTRICTIONS)
        == "color: var(--brand)"
    )


def test_filter_declarations__drops_a_property_behind_a_comment():
    assert styles.filter_declarations("/* x */ position: absolute", RESTRICTIONS) == ""


def test_filter_declarations__keeps_a_semicolon_inside_a_group():
    text = 'background: url("pixel.gif;x")'
    assert styles.filter_declarations(text, RESTRICTIONS) == text


def test_filter_styles__drops_a_rule_with_an_unsupported_selector():
    assert styles.filter_styles("a:hover { color: red }", RESTRICTIONS) == ""


def test_filter_styles__keeps_the_declarations_it_reads():
    assert (
        styles.filter_styles(".x { position: absolute; color: red }", RESTRICTIONS)
        == ".x {color: red}"
    )


def test_filter_styles__drops_an_at_rule():
    assert styles.filter_styles("@font-face { font-family: X }", RESTRICTIONS) == ""
    assert styles.filter_styles("@import url(x.css);", RESTRICTIONS) == ""


def test_filter_styles__drops_a_media_query_with_an_unsupported_term():
    assert (
        styles.filter_styles(
            "@media screen and (hover: hover) { .x { color: red } }",
            RESTRICTIONS,
        )
        == ""
    )


def test_filter_styles__keeps_the_media_queries_the_client_reads():
    css = "@media (hover: hover), (max-width: 600px) { .x { color: red } }"
    assert (
        styles.filter_styles(css, styles.Restrictions(media_terms=(r"\bhover\b",)))
        == "@media (max-width: 600px){ .x {color: red} }"
    )


def test_filter_styles__drops_every_media_query_of_a_client_that_reads_none():
    assert (
        styles.filter_styles(
            "@media (max-width: 600px) { .x { color: red } }",
            styles.Restrictions(reads_media=False),
        )
        == ""
    )


def test_filter_styles__unwraps_a_media_query_the_forced_scheme_matches():
    css = "@media (prefers-color-scheme: dark) { .x { color: #eee } }"
    assert (
        styles.filter_styles(css, styles.Restrictions(), scheme="dark")
        == " .x {color: #eee} "
    )
    assert styles.filter_styles(css, styles.Restrictions(), scheme="light") == ""


def test_filter_styles__lets_the_scheme_outrun_a_client_that_reads_no_media():
    css = "@media (prefers-color-scheme: dark) { .x { color: #eee } }"
    assert (
        styles.filter_styles(css, styles.Restrictions(reads_media=False), scheme="dark")
        == " .x {color: #eee} "
    )


def test_filter_styles__keeps_the_conditions_a_forced_scheme_does_not_name():
    assert (
        styles.filter_styles(
            "@media screen and (prefers-color-scheme: dark) { .x { color: #eee } }",
            styles.Restrictions(),
            scheme="dark",
        )
        == "@media screen{ .x {color: #eee} }"
    )
    assert (
        styles.filter_styles(
            "@media (max-width: 600px) { .x { color: red } }",
            styles.Restrictions(),
            scheme="dark",
        )
        == "@media (max-width: 600px){ .x {color: red} }"
    )


def test_filter_styles__leaves_a_nested_rule_alone():
    text = ".x { color: red; position: absolute; &:hover { color: blue } }"
    assert (
        styles.filter_styles(
            text, styles.Restrictions(properties=frozenset({"position"}))
        )
        == text
    )


def test_filter_styles__keeps_a_string_it_does_not_read():
    assert (
        styles.filter_styles(
            '.x { content: "a;b{c}"; color: red }',
            styles.Restrictions(properties=frozenset({"color"})),
        )
        == '.x {content: "a;b{c}"}'
    )
