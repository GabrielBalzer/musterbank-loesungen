"""Small static accessibility scanner for the rendered pages and the style sheet."""
import re
from html.parser import HTMLParser

FOCUSABLE = {"a", "button", "input", "select", "textarea", "summary"}


class PageScan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.html_lang = None
        self.title = ""
        self.h1_count = 0
        self.fields = []
        self.label_for = set()
        self.label_depth = 0
        self.tables = []
        self.images_without_alt = 0
        self.mouse_only = []
        self.forms_without_submit = 0
        self._in_title = False
        self._form_has_submit = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.html_lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "label":
            self.label_depth += 1
            if a.get("for"):
                self.label_for.add(a["for"])
        elif tag in ("input", "select", "textarea"):
            kind = a.get("type", "text")
            if kind not in ("hidden", "submit", "button", "image", "reset"):
                self.fields.append((a.get("name"), a.get("id"), a.get("aria-label"), self.label_depth > 0))
            if tag == "input" and kind in ("submit", "image"):
                self._form_has_submit = True
        elif tag == "table":
            self.tables.append(False)
        elif tag == "th" and self.tables:
            self.tables[-1] = True
        elif tag == "img" and a.get("alt") is None:
            self.images_without_alt += 1
        elif tag == "form":
            self._form_has_submit = False
        elif tag == "button" and a.get("type", "submit") == "submit":
            self._form_has_submit = True
        if "onclick" in a and tag not in FOCUSABLE and not ("tabindex" in a and "role" in a):
            self.mouse_only.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "label":
            self.label_depth = max(0, self.label_depth - 1)
        elif tag == "form":
            if self._form_has_submit is False:
                self.forms_without_submit += 1
            self._form_has_submit = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    def unlabelled_fields(self):
        out = []
        for name, field_id, aria, wrapped in self.fields:
            if wrapped or aria or (field_id and field_id in self.label_for):
                continue
            out.append(name)
        return out


def scan(html):
    page = PageScan()
    page.feed(html)
    page.close()
    return page


def _hex_rgb(value):
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _luminance(rgb):
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(first, second):
    high, low = sorted((_luminance(_hex_rgb(first)), _luminance(_hex_rgb(second))), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _rules(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return re.findall(r"([^{}]+)\{([^{}]*)\}", css)


def _variables(css):
    return dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})", css))


def _resolve(value, variables):
    value = value.strip()
    match = re.match(r"var\((--[\w-]+)\)", value)
    if match:
        return variables.get(match.group(1))
    return value if re.fullmatch(r"#[0-9a-fA-F]{3,6}", value) else None


def low_contrast(css, minimum=4.5):
    """Text colours in the style sheet that are too light on their background (default white)."""
    variables = _variables(css)
    failures = []
    for selector, body in _rules(css):
        if "placeholder" in selector:
            continue
        color = re.search(r"(?:^|;|\s)color\s*:\s*([^;]+)", body)
        if not color:
            continue
        foreground = _resolve(color.group(1), variables)
        background = re.search(r"background(?:-color)?\s*:\s*([^;]+)", body)
        behind = (_resolve(background.group(1), variables) if background else None) or "#ffffff"
        if foreground and contrast(foreground, behind) < minimum:
            failures.append(selector.strip())
    return failures


def focus_removed(css):
    """True when the outline is switched off and no focus rule brings a visible replacement."""
    removed = False
    replaced = False
    for selector, body in _rules(css):
        if re.search(r"outline(?:-style)?\s*:\s*(none|0)\b", body):
            removed = True
        if ":focus" in selector and re.search(r"(outline|box-shadow|border)\s*:\s*(?!none|0\b)", body):
            replaced = True
    return removed and not replaced
