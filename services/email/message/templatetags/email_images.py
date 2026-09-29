"""Template tags for the images a mail carries inside itself."""

from urllib.parse import urljoin

from django import template
from django.contrib.staticfiles.storage import staticfiles_storage

register = template.Library()


@register.simple_tag(takes_context=True)
def inline_image(context, name: str) -> str:
    """
    Return the address of one static image and have the mail carry it.

    The address is absolute, because the root-relative one `{% static %}`
    states would resolve against the preview's own path. It is also the exact
    string the shell leaves in the body, so `RelayEmail.message` swaps it for
    the part it attaches without reconstructing anything. A preview is served
    with that address, since it has no message to resolve a `cid:` against.
    """
    email = context["email"]
    address = urljoin(email.get_base_url(), staticfiles_storage.url(name))
    email.inline_images.append((name, address))
    return address
