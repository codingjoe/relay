"""Pygments lexers for email authentication syntax."""

from pygments.lexer import RegexLexer, bygroups
from pygments.token import Comment, Keyword, Name, Operator, Text, Whitespace


class DkimTagLexer(RegexLexer):
    """
    Lex a DKIM-Signature tag list, for example `v=1; a=ed25519-sha256;`.

    Tag names get the primary color, the base64 blobs of the b= and bh=
    tags are muted so a 400-character signature recedes behind its
    meaningful tags, and the covered-headers list gets the label color
    the email lexer uses for addresses.
    """

    name = "DKIM"
    aliases = ["dkim"]

    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r";", Operator),
            (
                r"(b|bh)(=)([A-Za-z0-9+/=]+)",
                bygroups(Name.Tag, Operator, Name.Variable),
            ),
            (r"(h)(=)([^;]+)", bygroups(Name.Tag, Operator, Name.Label)),
            (r"([a-zA-Z][a-zA-Z0-9]*)(=)", bygroups(Name.Tag, Operator)),
            (r"[^;]+", Text),
        ]
    }


class AuthenticationResultsLexer(RegexLexer):
    """
    Lex an Authentication-Results or ARC-Authentication-Results header.

    Method names read like header names, `pass` turns green and failures
    red, property values keep the email-lexer blue, and parenthesized
    annotations render as quiet comments.
    """

    name = "Authentication-Results"
    aliases = ["authres"]

    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r"(?i)(authentication-results)(:)", bygroups(Name.Tag, Operator)),
            (r";", Operator),
            (
                r"\(([^)]*)\)",
                bygroups(
                    Comment.Single,
                ),
            ),
            (r"(?i)(dkim|spf|dmarc|arc)(\s*=\s*)", bygroups(Name.Tag, Operator)),
            (r"(?i)(pass)(?=[\s;]|$)", Keyword.Constant),
            (r"(?i)(fail|softfail|reject|quarantine)(?=[\s;]|$)", Name.Exception),
            (r"(?i)(none|neutral|temperror|permerror|policy)(?=[\s;]|$)", Operator),
            (r"([a-z][\w-]*(?:\.[\w-]+)*)(\s*=\s*)", bygroups(Name.Variable, Operator)),
            (r"[^\s;]+", Name.Label),
        ]
    }
