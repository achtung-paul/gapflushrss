# Cleans the HTML produced by the notes editor before it is stored.
#
# The notes field is the only place in this app where a user's markup is
# saved and rendered back as markup (frontend/src/components/
# RichTextEditor.jsx writes it, and the entry view renders it with
# dangerouslySetInnerHTML). Without this, a note containing
# <script>...</script> or <img onerror=...> would be stored verbatim and
# then executed in every other user's browser, in this app's own origin --
# textbook stored XSS.
#
# Sanitising here, on write, rather than at render time is deliberate: the
# value that reaches the database is then already safe for *every*
# consumer -- this page, the API, a future PDF/report export, anyone
# reading the table directly -- instead of only for the one component that
# happens to remember to clean it. Same reasoning as the log redaction in
# core/logging_config.py.

import nh3

# Exactly what Tiptap's StarterKit can emit, and nothing else. Anything
# outside this list has its tags stripped while its text is kept, so a
# pasted <div> or <script> loses the element but not the words inside it.
ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "s",
    "code",
    "pre",
    "blockquote",
    "ul",
    "ol",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "a",
}

# Only links carry an attribute. Notably absent: `style` (CSS can be an
# attack surface of its own) and `class` (would let notes reach into the
# app's own stylesheet).
ALLOWED_ATTRIBUTES = {"a": {"href"}}


def sanitize_notes(html: str | None) -> str:
    """Return `html` with everything outside the allowlist removed.

    nh3's own defaults are kept for the rest: it drops event handlers and
    <script>/<style> entirely, restricts URL schemes so `javascript:` in
    an href can't survive, and adds rel="noopener noreferrer" to links.
    Those defaults are safer than anything worth hand-rolling here.
    """
    if not html:
        return ""

    cleaned = nh3.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)

    # The editor emits "<p></p>" for an empty document. Collapse that (and
    # anything else that leaves no visible text) to "", so "no notes" has
    # a single representation rather than several near-identical ones.
    if not nh3.clean(cleaned, tags=set()).strip():
        return ""
    return cleaned
