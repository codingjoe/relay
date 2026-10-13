from email.message import EmailMessage

from services.email.message.preview.images import collect_inline_images, filter_images

DATA_URL = "data:image/png;base64,aGVsbG8="


def test_collect_inline_images__maps_a_content_id_to_a_data_url():
    message = EmailMessage()
    message.set_content('<img src="cid:logo@relay">', subtype="html")
    message.add_related(b"hello", maintype="image", subtype="png", cid="<logo@relay>")

    assert collect_inline_images(message) == {"logo@relay": DATA_URL}


def test_collect_inline_images__skips_a_message_without_a_carried_image():
    message = EmailMessage()
    message.set_content("<p>x</p>", subtype="html")

    assert collect_inline_images(message) == {}


def test_collect_inline_images__skips_a_carried_part_without_a_payload():
    message = EmailMessage()
    message.set_content('<img src="cid:logo@relay">', subtype="html")
    message.add_related(b"", maintype="image", subtype="png", cid="<logo@relay>")

    assert collect_inline_images(message) == {}


def test_filter_images__resolves_a_cid_reference():
    rendered = filter_images(
        '<img src="cid:logo@relay">', {"logo@relay": DATA_URL}, block_data_images=False
    )

    assert rendered == f'<img src="{DATA_URL}">'


def test_filter_images__resolves_the_longest_content_id_first():
    images = {"logo": "data:image/png;base64,SHORT", "logo@relay": DATA_URL}

    rendered = filter_images(
        '<img src="cid:logo@relay">', images, block_data_images=False
    )

    assert rendered == f'<img src="{DATA_URL}">'


def test_filter_images__drops_a_data_image_a_client_never_shows():
    rendered = filter_images(
        f'<img src="{DATA_URL}" alt="logo">', {}, block_data_images=True
    )

    assert rendered == '<img alt="logo">'


def test_filter_images__keeps_a_data_image_a_client_shows():
    html_text = f'<img src="{DATA_URL}">'

    assert filter_images(html_text, {}, block_data_images=False) == html_text


def test_filter_images__drops_the_data_image_before_resolving_a_cid_reference():
    data_image = "data:image/gif;base64,c2VuZGVy"

    rendered = filter_images(
        f'<img src="{data_image}"><img src="cid:logo@relay">',
        {"logo@relay": DATA_URL},
        block_data_images=True,
    )

    assert rendered == f'<img><img src="{DATA_URL}">'
