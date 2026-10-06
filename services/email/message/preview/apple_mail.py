"""
The CSS an Apple Mail preview drops, from the caniemail.com support data.

Apple Mail renders nearly everything, so only a few features do not apply:
hyphenate-limit-chars, inline-size, text-justify, and the rules whose selectors
use :target or :visited.
"""

from .. import styles

RESTRICTIONS = styles.Restrictions(
    # caniemail.com/features/css-hyphenate-limit-chars/, css-inline-size/, and
    # css-text-justify/ do not apply in Apple Mail.
    properties=frozenset({"hyphenate-limit-chars", "inline-size", "text-justify"}),
    # caniemail.com/features/css-pseudo-class-target/ and
    # css-pseudo-class-visited/ do not apply in Apple Mail.
    selectors=(r"::?(?:target|visited)\b",),
)
