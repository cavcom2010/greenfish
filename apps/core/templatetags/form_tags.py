"""Template helpers for the shared form-field partial."""
from django import template

register = template.Library()


@register.filter
def add_attr(field, spec):
    """Render a bound field with extra widget attributes.

    Usage: {{ field|add_attr:"autocomplete:email" }} or
           {{ field|add_attr:"inputmode:tel,placeholder:07123 456789" }}
    """
    attrs = {}
    for pair in spec.split(","):
        if ":" in pair:
            key, value = pair.split(":", 1)
            attrs[key.strip()] = value.strip()
    return field.as_widget(attrs=attrs)


@register.filter
def widget_type(field):
    """Return the widget input_type (e.g. 'checkbox', 'text') or '' for
    widgets without one (textarea, select)."""
    return getattr(field.field.widget, "input_type", "")
