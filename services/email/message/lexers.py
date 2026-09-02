"""Pygments lexers for email authentication syntax."""

from pygments.lexer import RegexLexer, bygroups
from pygments.token import Comment, Keyword, Name, Operator, Text, Whitespace


class DkimTagLexer(RegexLexer):
    """
    Tokenize a DKIM-Signature header value into its tags.

    Tag names and operators become `Name.Tag` and `Operator`, the base64
    payload of the b= and bh= tags becomes `Name.Variable`, and the
    covered-headers list of the h= tag becomes `Name.Label`.
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
    Tokenize an Authentication-Results or ARC-Authentication-Results header.

    Method names become `Name.Tag`, results map to `Keyword.Constant`
    for pass and `Name.Exception` for failures, property values become
    `Name.Label`, and parenthesized annotations become `Comment.Single`.
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
