from django.http import QueryDict

from services.email.message.preview import (
    CLIENTS,
    MessagePreview,
    PreviewClient,
    PreviewTheme,
)


def test_from_query__defaults_to_the_most_common_client():
    preview = MessagePreview.from_query(QueryDict(""))

    assert preview.theme is PreviewTheme.LIGHT
    assert preview.client is PreviewClient.GMAIL


def test_from_query__reads_a_known_mode():
    preview = MessagePreview.from_query(QueryDict("theme=dark&client=gmail"))

    assert preview.theme is PreviewTheme.DARK
    assert preview.client is PreviewClient.GMAIL


def test_from_query__ignores_an_unknown_mode():
    preview = MessagePreview.from_query(QueryDict("theme=blue&client=netscape"))

    assert preview.theme is PreviewTheme.LIGHT
    assert preview.client is PreviewClient.GMAIL


def test_clients__every_client_has_a_profile():
    assert set(CLIENTS) == set(PreviewClient)


def test_block_images__follows_the_client():
    assert MessagePreview(client=PreviewClient.OUTLOOK).block_images is True
    assert MessagePreview(client=PreviewClient.GMAIL).block_images is False
    assert MessagePreview(client=PreviewClient.APPLE_MAIL).block_images is False


def test_render__gmail_drops_what_it_never_applies():
    rendered = MessagePreview(client=PreviewClient.GMAIL).render(
        "<style>.x { position: absolute; display: flex }</style>"
    )

    assert "position" not in rendered
    assert "display: flex" in rendered


def test_render__outlook_drops_the_word_engine_gaps():
    rendered = MessagePreview(client=PreviewClient.OUTLOOK).render(
        "<style>"
        ".x { display: flex; border-radius: 4px; color: rgba(0, 0, 0, .5) }"
        ".y { color: red }"
        " * { margin: 0 }"
        "@media (max-width: 600px) { .y { color: blue } }"
        "</style>"
    )

    assert "display: flex" not in rendered
    assert "border-radius" not in rendered
    assert "rgba(" not in rendered
    assert "* {" not in rendered
    assert "@media" not in rendered
    assert ".y {color: red}" in rendered


def test_render__apple_mail_keeps_what_it_applies():
    rendered = MessagePreview(client=PreviewClient.APPLE_MAIL).render(
        "<style>.x { display: flex; border-radius: 4px } a:visited { color: red }</style>"
    )

    assert "display: flex" in rendered
    assert "border-radius: 4px" in rendered
    assert ":visited" not in rendered


def test_render__filters_a_style_attribute():
    rendered = MessagePreview(client=PreviewClient.GMAIL).render(
        '<p style="position: absolute; color: red">x</p>'
    )

    assert 'style="color: red"' in rendered


def test_render__resolves_the_light_theme_against_the_reader():
    body = "<style>@media (prefers-color-scheme: dark) { .x { color: #eee } }</style>"
    rendered = MessagePreview().render(body)

    assert "color-scheme:light!important" in rendered
    assert "color: #eee" not in rendered


def test_render__applies_the_dark_styles_of_the_message():
    body = "<style>@media (prefers-color-scheme: dark) { .x { color: #eee } }</style>"
    rendered = MessagePreview(
        theme=PreviewTheme.DARK, client=PreviewClient.APPLE_MAIL
    ).render(body)

    assert "color-scheme:dark!important" in rendered
    assert "color: #eee" in rendered


def test_render__applies_the_dark_styles_a_client_reads_no_media():
    body = "<style>@media (prefers-color-scheme: dark) { .x { color: #eee } }</style>"
    rendered = MessagePreview(
        theme=PreviewTheme.DARK, client=PreviewClient.OUTLOOK
    ).render(body)

    assert "color-scheme:dark!important" in rendered
    assert "color: #eee" in rendered


def test_render__inverts_the_frame_for_a_client_that_inverts():
    rendered = MessagePreview(
        theme=PreviewTheme.DARK, client=PreviewClient.GMAIL
    ).render("<p>x</p>")

    assert "color-scheme:light!important" in rendered
    assert "html{filter:invert(1) hue-rotate(180deg)!important}" in rendered
    assert "img,video,svg{filter:invert(1) hue-rotate(180deg)!important}" in rendered


def test_render__keeps_a_client_that_applies_the_dark_styles():
    rendered = MessagePreview(
        theme=PreviewTheme.DARK, client=PreviewClient.APPLE_MAIL
    ).render("<p>x</p>")

    assert "color-scheme:dark!important" in rendered
    assert "html{filter:" not in rendered


def test_render__adds_the_preview_stylesheet_to_the_head():
    rendered = MessagePreview().render("<html><head></head><body>x</body></html>")

    assert (
        '<head><style id="relay-preview">html{color-scheme:light!important}</style>'
        in rendered
    )


def test_render__adds_the_preview_stylesheet_without_a_head():
    rendered = MessagePreview().render("<p>x</p>")

    assert rendered == (
        '<p>x</p><style id="relay-preview">html{color-scheme:light!important}</style>'
    )
