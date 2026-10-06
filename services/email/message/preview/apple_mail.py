"""
The CSS an Apple Mail preview drops, from the caniemail.com support data.

Apple Mail renders nearly everything.
"""

from .. import styles

RESTRICTIONS = styles.Restrictions(
    properties=frozenset({"hyphenate-limit-chars", "inline-size", "text-justify"}),
    selectors=(r"::?(?:target|visited)\b",),
)
