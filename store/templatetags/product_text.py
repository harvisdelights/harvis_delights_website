"""Safe, small rich-text formatting for product descriptions."""

import re

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe


register = template.Library()

_BOLD_HEADING = re.compile(r"^\*\*(.+?)\*\*$")
_BOLD_TEXT = re.compile(r"\*\*(.+?)\*\*")


def _inline(text):
    """Escape all input first, then permit only Markdown bold markers."""
    escaped = conditional_escape(text)
    return _BOLD_TEXT.sub(r"<strong>\1</strong>", escaped)


@register.filter(is_safe=True)
def product_description(value):
    """Render paragraphs, bold section labels and ``-`` lists from admin text.

    Descriptions remain plain text in the database. Arbitrary HTML is never
    rendered, so text entered through Django admin cannot inject page markup.
    """
    if not value:
        return ""

    lines = [line.strip().rstrip("\\").rstrip() for line in str(value).splitlines()]
    output, paragraph, list_items = [], [], []

    def flush_paragraph():
        if paragraph:
            output.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list():
        if list_items:
            items = "".join(f"<li>{_inline(item)}</li>" for item in list_items)
            output.append(f"<ul>{items}</ul>")
            list_items.clear()

    for line in lines:
        if not line:
            flush_paragraph()
            flush_list()
            continue

        heading = _BOLD_HEADING.match(line)
        if heading:
            flush_paragraph()
            flush_list()
            output.append(f"<h3>{_inline(heading.group(1))}</h3>")
        elif line.startswith("- "):
            flush_paragraph()
            list_items.append(line[2:].strip())
        else:
            flush_list()
            paragraph.append(line)

    flush_paragraph()
    flush_list()
    return mark_safe("".join(output))
