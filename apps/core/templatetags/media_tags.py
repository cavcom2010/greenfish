from django import template

from apps.core.media import get_image_variant_url

register = template.Library()


@register.filter
def image_variant(image_field, variant_name):
    return get_image_variant_url(image_field, variant_name)
