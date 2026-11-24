from django import template
from django.utils.html import escapejs
from django.utils.safestring import mark_safe
from ..translations import tr

register = template.Library()


@register.simple_tag
def t(text):
    """Bilingual text: {% t "English text" %} -> Malayalam when ml is active."""
    return tr(text)


@register.simple_tag
def tjs(text):
    """Like {% t %} but safe inside JavaScript / JSON string literals."""
    return mark_safe(escapejs(tr(text)))


@register.filter
def dist_label(code):
    from ..models import KERALA_DISTRICTS
    return dict(KERALA_DISTRICTS).get(code, code)


@register.filter(name='tr')
def tr_filter(text):
    """{{ value|tr }} - translate a model choice label / status text."""
    return tr(str(text))
