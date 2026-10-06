from .. import styles

RESTRICTIONS = styles.Restrictions(
    properties=frozenset({"hyphenate-limit-chars", "inline-size", "text-justify"}),
    selectors=(r"::?(?:target|visited)\b",),
)
