"""
Resolve the images a message body refers to.

A body refers to the files it carries by `cid:` address, which a browser
cannot resolve on its own. The addresses are answered here, and an image a
client never renders is dropped.
"""

import base64
import re

DATA_IMAGE_SOURCE = re.compile(
    r"\s+\bsrc\s*=\s*(?P<quote>[\"'])data:[^\"']*(?P=quote)", re.IGNORECASE
)


def collect_inline_images(parsed_email) -> dict[str, str]:
    """Return the data URL of every part a body can reference by Content-ID."""
    images = {}
    for part in parsed_email.walk():
        payload = part.get_payload(decode=True)
        content_id = str(part.get("Content-ID") or "").strip().strip("<>")
        if content_id and payload:
            images[content_id] = (
                f"data:{part.get_content_type()};base64,"
                f"{base64.b64encode(payload).decode()}"
            )
    return images


def filter_images(
    html_text: str, images: dict[str, str], block_data_images: bool
) -> str:
    """Return the body with the inline images in place and the dropped ones gone."""
    if block_data_images:
        html_text = DATA_IMAGE_SOURCE.sub("", html_text)
    # One content ID can be a prefix of another, so the longest goes first.
    for content_id in sorted(images, key=len, reverse=True):
        html_text = html_text.replace(f"cid:{content_id}", images[content_id])
    return html_text
