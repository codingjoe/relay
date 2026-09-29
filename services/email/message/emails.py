"""The shell relay's own messages wear."""

import mimetypes
import pathlib
from email.message import Message, MIMEPart

from django.contrib.staticfiles import finders
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


class RelayEmail(TemplateEmail):
    """
    A relay message, with the images its templates ask for travelling inside.

    A reader whose client blocks remote content still sees the brand, because
    the image is a part of the message rather than a fetch to allow. Django
    attaches that part after the body, which is the order a client needs to
    resolve a `cid:` reference.
    """

    inline_images: list[tuple[str, str]]
    """The images the rendered body asked to carry, as (static name, address)."""

    def render_html(self, **context) -> str:
        # The tag reads the email back out of the context to register itself.
        context["email"] = self
        self.inline_images = []
        return super().render_html(**context)

    def message(self, **kwargs) -> Message:
        # The body has to exist before its addresses can be swapped, and the
        # parts have to be in place before the MIME tree is built.
        self.render()
        self.embed_inline_images()
        return super().message(**kwargs)

    def embed_inline_images(self) -> None:
        """
        Attach the images the body asked for and point the body at their parts.

        Attaching empties the list, so a second call adds nothing. A preview
        never reaches this method: it serves the body without the MIME context
        that a `cid:` reference needs, so it keeps the address.
        """
        references = {
            address: f"cid:{name.rpartition('/')[2]}"
            for name, address in self.inline_images
        }
        for name, _ in self.inline_images:
            self.attach(static_image_part(name))
        self.inline_images = []
        self.alternatives = [
            self.reference_inline_images(alternative, references)
            for alternative in self.alternatives
        ]

    def reference_inline_images(
        self, alternative: EmailAlternative, references: dict[str, str]
    ) -> EmailAlternative:
        """Swap each address one alternative names for the part that answers it."""
        content = alternative.content
        for address, reference in references.items():
            content = content.replace(address, reference)
        return alternative._replace(content=content)
