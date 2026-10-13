from email import message_from_bytes

from services.email.message.preview.images import collect_inline_images, filter_images

INLINE_BODY = (
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/related; boundary="b"\r\n\r\n'
    b"--b\r\nContent-Type: text/html\r\n\r\n"
    b'<img src="cid:logo@relay">\r\n'
    b"--b\r\nContent-Type: image/png\r\nContent-ID: <logo@relay>\r\n"
    b"Content-Transfer-Encoding: base64\r\n\r\n"
    b"aGVsbG8=\r\n"
    b"--b--\r\n"
)

DATA_URL = "data:image/png;base64,aGVsbG8="


def test_collect_inline_images__maps_a_content_id_to_a_data_url():
    assert collect_inline_images(message_from_bytes(INLINE_BODY)) == {
        "logo@relay": DATA_URL
    }


def test_collect_inline_images__skips_a_message_without_a_carried_image():
    parsed = message_from_bytes(b"Content-Type: text/html\r\n\r\n<p>x</p>")

    assert collect_inline_images(parsed) == {}


def test_filter_images__answers_a_cid_reference():
    rendered = filter_images('<img src="cid:logo@relay">', {"logo@relay": DATA_URL}, False)

    assert rendered == f'<img src="{DATA_URL}">'


def test_filter_images__answers_the_longest_content_id_first():
    images = {"logo": "data:image/png;base64,SHORT", "logo@relay": DATA_URL}

    rendered = filter_images('<img src="cid:logo@relay">', images, False)

    assert rendered == f'<img src="{DATA_URL}">'


def test_filter_images__drops_a_data_image_a_client_never_shows():
    rendered = filter_images(f'<img src="{DATA_URL}" alt="logo">', {}, True)

    assert rendered == '<img alt="logo">'


def test_filter_images__keeps_a_data_image_a_client_shows():
    html_text = f'<img src="{DATA_URL}">'

    assert filter_images(html_text, {}, False) == html_text


def test_filter_images__drops_the_sender_image_before_answering_a_cid_one():
    sender_url = "data:image/gif;base64,c2VuZGVy"

    rendered = filter_images(
        f'<img src="{sender_url}"><img src="cid:logo@relay">',
        {"logo@relay": DATA_URL},
        True,
    )

    assert rendered == f'<img><img src="{DATA_URL}">'
