"""The shell relay's own messages wear."""

import mimetypes
import pathlib
from email.message import Message, MIMEPart

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.mail import EmailAlternative
from django_letter import TemplateEmail


class MissingStaticImageError(ValueError):
    """The named static image does not exist."""

    def __init__(self, name):
        super().__init__(f"Missing static image: {name}")


def static_image_content(name: str) -> bytes:
    """
    Return the bytes of one static image.

    The finder reads the file where the project keeps it, which is all a
    server in development has; `collectstatic` copies the same file for a
    deployment.
    """
    path = finders.find(name)
    if not path:
        raise MissingStaticImageError(name)
    return pathlib.Path(path).read_bytes()


def static_image_part(name: str) -> MIMEPart:
    """Build the inline part of one static image, answering to its file name."""
    filename = name.rpartition("/")[2]
    mimetype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    maintype, _, subtype = mimetype.partition("/")
    part = MIMEPart()
    part.set_content(
        static_image_content(name),
        maintype=maintype,
        subtype=subtype,
        cid=f"<{filename}>",
        disposition="inline",
        filename=filename,
    )
    return part


def static_image_address(email: TemplateEmail, name: str) -> str:
    """Return the address the rendered body gives one static image."""
    url = staticfiles_storage.url(name)
    return f"{email.get_base_url().rstrip('/')}/{url.lstrip('/')}"


class RelayEmail(TemplateEmail):
    """
    A relay message, with its artwork travelling inside the message.

    A reader whose client blocks remote content still sees the brand, because
    the image is a part of the message rather than a fetch to allow. Django
    attaches that part after the body, which is the order a client needs to
    resolve a `cid:` reference.
    """

    inline_images: tuple[str, ...] = ("img/word-brand.svg",)
    """Static names, as `{% static %}` states them, carried in the message."""

    def message(self, **kwargs) -> Message:
        # The body has to exist before its addresses can be swapped, and the
        # parts have to be in place before the MIME tree is built.
        self.render()
        self.embed_inline_images()
        return super().message(**kwargs)

    def embed_inline_images(self) -> None:
        """
        Attach each configured image and point the body at its part.

        Only an image the body still names is attached, so a second call adds
        nothing, and a body that no longer uses the artwork carries no part.
        A preview never reaches this method: it serves the body without the
        MIME context that a `cid:` reference needs, so it keeps the address.
        """
        named = [
            name
            for name in self.inline_images
            if any(
                static_image_address(self, name) in alternative.content
                for alternative in self.alternatives
            )
        ]
        for name in named:
            self.attach(static_image_part(name))
        self.alternatives = [
            self.reference_inline_images(alternative)
            for alternative in self.alternatives
        ]

    def reference_inline_images(
        self, alternative: EmailAlternative
    ) -> EmailAlternative:
        """Swap each address one alternative names for the part that answers it."""
        content = alternative.content
        for name in self.inline_images:
            filename = name.rpartition("/")[2]
            content = content.replace(
                static_image_address(self, name), f"cid:{filename}"
            )
        return alternative._replace(content=content)
