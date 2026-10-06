"""
The preview modes of the HTML body view.

A message carries HTML the way a mail client receives it. The preview renders
that body close to how a client shows it: the selected client profile drops
what that client never applies, and stops the remote images for the clients
that hold them back until the reader asks for them. The preview leads with
Gmail, the client most messages are read in. The dark theme inverts the frame
where the client does that and applies the dark styles of the message
everywhere else, so the theme decides the color scheme of every combination.
The client profiles follow the support data on caniemail.com
(https://www.caniemail.com/api/data.json, checked September 2026), so a
preview never claims more than the published support table. One module
holds each client profile: `gmail.py`, `apple_mail.py`, and `outlook.py`.

The page drives the modes through the query of the frame, so the frame itself
stays sandboxed and runs no scripts.
"""

import dataclasses
import enum
import re

from django.http import QueryDict

from .. import styles
from . import apple_mail, gmail, outlook


class PreviewTheme(enum.StrEnum):
    """The color scheme the preview resolves the message to."""

    LIGHT = "light"
    DARK = "dark"


class PreviewClient(enum.StrEnum):
    """An email client whose rendering the preview emulates."""

    GMAIL = "gmail"
    APPLE_MAIL = "apple-mail"
    OUTLOOK = "outlook"


CLIENTS = {
    PreviewClient.GMAIL: gmail.RESTRICTIONS,
    PreviewClient.APPLE_MAIL: apple_mail.RESTRICTIONS,
    PreviewClient.OUTLOOK: outlook.RESTRICTIONS,
}

# Gmail renders a dark mode by inverting the message, so the dark theme asks
# for the light variant there. Every other client applies the dark styles the
# message itself carries.
INVERTING_CLIENTS = frozenset({PreviewClient.GMAIL})

# Outlook holds remote images back until the reader asks for them. Gmail shows
# them by default, loaded through its own image proxy, so the sender learns of
# the open but not the reader's address (Gmail Help, "View images in emails").
# Apple Mail loads them too. A preview loads them directly for both.
IMAGE_BLOCKING_CLIENTS = frozenset({PreviewClient.OUTLOOK})

LIGHT_STYLES = "html{color-scheme:light!important}"
DARK_STYLES = "html{color-scheme:dark!important}"
# The frame inverts every pixel of itself, so the media inside counter the
# inversion and keep their own colors, the way an inverted client does.
INVERT_STYLES = (
    f"{LIGHT_STYLES}html{{filter:invert(1) hue-rotate(180deg)!important}}"
    f"img,video,svg{{filter:invert(1) hue-rotate(180deg)!important}}"
)

STYLE_ELEMENT = re.compile(
    r"(<style\b[^>]*>)(.*?)(</style\s*>)", re.IGNORECASE | re.DOTALL
)
STYLE_ATTRIBUTE = re.compile(
    r"(\bstyle\s*=\s*)(?P<quote>[\"'])(?P<css>.*?)(?P=quote)", re.IGNORECASE | re.DOTALL
)
HEAD_END = re.compile(r"</head\s*>", re.IGNORECASE)
BODY_END = re.compile(r"</body\s*>", re.IGNORECASE)
PREVIEW_STYLE_ID = "relay-preview"


@dataclasses.dataclass(frozen=True)
class MessagePreview:
    """The preview mode one HTML body request asked for."""

    theme: PreviewTheme = PreviewTheme.LIGHT
    # Most messages are read in Gmail, so the preview leads with it.
    client: PreviewClient = PreviewClient.GMAIL

    @classmethod
    def from_query(cls, query: QueryDict) -> MessagePreview:
        """Return the preview mode of a request query, falling back on unknown values."""
        return cls(
            theme=next(
                (theme for theme in PreviewTheme if theme.value == query.get("theme")),
                PreviewTheme.LIGHT,
            ),
            client=next(
                (
                    client
                    for client in PreviewClient
                    if client.value == query.get("client")
                ),
                PreviewClient.GMAIL,
            ),
        )

    @property
    def restrictions(self) -> styles.Restrictions:
        """Return the CSS restrictions of the selected client."""
        return CLIENTS[self.client]

    @property
    def block_images(self) -> bool:
        """Return whether the selected client stops remote images by default."""
        return self.client in IMAGE_BLOCKING_CLIENTS

    @property
    def inverts(self) -> bool:
        """Return whether the dark theme inverts the frame."""
        return self.theme is PreviewTheme.DARK and self.client in INVERTING_CLIENTS

    @property
    def scheme(self) -> str:
        """Return the color scheme the media of the message resolve to."""
        return "dark" if self.dark_styles else "light"

    @property
    def dark_styles(self) -> bool:
        """Return whether the dark theme applies the dark styles of the message."""
        return self.theme is PreviewTheme.DARK and not self.inverts

    @property
    def preview_styles(self) -> str:
        """Return the stylesheet the preview adds to the body."""
        match self.inverts, self.dark_styles:
            case (True, _):
                return INVERT_STYLES
            case (_, True):
                return DARK_STYLES
            case _:
                return LIGHT_STYLES

    def render(self, html_text: str) -> str:
        """Return the body of a message with the preview mode applied."""
        return inject_preview_styles(
            filter_body_styles(html_text, self.restrictions, self.scheme),
            self.preview_styles,
        )


def filter_body_styles(
    html_text: str, restrictions: styles.Restrictions, scheme: str
) -> str:
    """Rewrite the styles a message carries: its style elements and attributes."""
    html_text = STYLE_ELEMENT.sub(
        lambda match: (
            f"{match.group(1)}"
            f"{styles.filter_styles(match.group(2), restrictions, scheme)}"
            f"{match.group(3)}"
        ),
        html_text,
    )
    return STYLE_ATTRIBUTE.sub(
        lambda match: (
            f"{match.group(1)}{match.group('quote')}"
            f"{styles.filter_declarations(match.group('css'), restrictions)}"
            f"{match.group('quote')}"
        ),
        html_text,
    )


def inject_preview_styles(html_text: str, css: str) -> str:
    """Add the preview stylesheet after the styles of the message itself."""
    style = f'<style id="{PREVIEW_STYLE_ID}">{css}</style>'
    match = HEAD_END.search(html_text) or BODY_END.search(html_text)
    return (
        f"{html_text}{style}"
        if not match
        else f"{html_text[: match.start()]}{style}{html_text[match.start() :]}"
    )
