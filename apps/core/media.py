"""
Shared media validation and image derivative helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from posixpath import splitext

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.deconstruct import deconstructible
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")

_MEGABYTE = 1024 * 1024


@deconstructible
class ProductionImageValidator:
    """Validate uploaded images for format, size, and dimensions."""

    def __init__(
        self,
        *,
        max_bytes,
        max_width=2400,
        max_height=2400,
        allowed_formats=ALLOWED_IMAGE_FORMATS,
    ):
        self.max_bytes = int(max_bytes)
        self.max_width = int(max_width)
        self.max_height = int(max_height)
        self.allowed_formats = tuple(allowed_formats)

    def __call__(self, value):
        if not value:
            return

        if getattr(value, "size", 0) > self.max_bytes:
            raise ValidationError(
                f"Image files must be {human_readable_bytes(self.max_bytes)} or smaller."
            )

        image_format, width, height = inspect_uploaded_image(value)

        if image_format not in self.allowed_formats:
            allowed = ", ".join(self.allowed_formats)
            raise ValidationError(f"Unsupported image format. Allowed formats: {allowed}.")

        if width > self.max_width or height > self.max_height:
            raise ValidationError(
                f"Images must be at most {self.max_width}x{self.max_height}px."
            )


@dataclass(frozen=True)
class ImageVariantSpec:
    width: int
    height: int
    format: str = "WEBP"
    quality: int = 82
    mode: str = "cover"

    @property
    def extension(self):
        return self.format.lower()


IMAGE_VARIANT_SPECS = {
    "card": ImageVariantSpec(width=640, height=640, format="WEBP", quality=82, mode="cover"),
    "detail": ImageVariantSpec(width=960, height=960, format="WEBP", quality=84, mode="cover"),
    "thumb": ImageVariantSpec(width=160, height=160, format="WEBP", quality=80, mode="cover"),
    "hero": ImageVariantSpec(width=1280, height=720, format="WEBP", quality=84, mode="cover"),
    "logo": ImageVariantSpec(width=512, height=512, format="WEBP", quality=84, mode="contain"),
    "favicon": ImageVariantSpec(width=192, height=192, format="PNG", quality=100, mode="contain"),
}

MENU_IMAGE_VALIDATORS = [ProductionImageValidator(max_bytes=5 * _MEGABYTE)]
LOGO_IMAGE_VALIDATORS = [ProductionImageValidator(max_bytes=1 * _MEGABYTE, max_width=1600, max_height=1600)]
FAVICON_IMAGE_VALIDATORS = [ProductionImageValidator(max_bytes=256 * 1024, max_width=512, max_height=512)]


def human_readable_bytes(num_bytes):
    if num_bytes >= _MEGABYTE:
        return f"{num_bytes / _MEGABYTE:.0f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} bytes"


def inspect_uploaded_image(value):
    if hasattr(value, "open"):
        value.open("rb")
    reset_uploaded_file(value)
    try:
        with Image.open(value) as image:
            image.load()
            return (image.format or "").upper(), image.size[0], image.size[1]
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("Upload a valid JPG, PNG, or WebP image.") from exc
    finally:
        reset_uploaded_file(value)


def reset_uploaded_file(value):
    try:
        value.seek(0)
    except Exception:
        file_obj = getattr(value, "file", None)
        if file_obj:
            try:
                file_obj.seek(0)
            except Exception:
                pass


def get_changed_image_names(instance, field_names):
    field_names = tuple(field_names)
    changed_fields = {}
    previous = None
    if instance.pk:
        previous = instance.__class__.objects.filter(pk=instance.pk).only(*field_names).first()

    for field_name in field_names:
        current_file = getattr(instance, field_name)
        current_name = current_file.name if current_file else ""
        previous_name = ""
        if previous:
            previous_file = getattr(previous, field_name)
            previous_name = previous_file.name if previous_file else ""

        if previous is None:
            if current_name:
                changed_fields[field_name] = previous_name
            continue

        if current_name != previous_name:
            changed_fields[field_name] = previous_name

    return changed_fields


def validate_changed_image_fields(instance, changed_fields):
    for field_name in changed_fields:
        value = getattr(instance, field_name)
        if not value:
            continue

        field = instance._meta.get_field(field_name)
        for validator in field.validators:
            validator(value)


def sync_instance_image_variants(instance, field_variants, changed_fields):
    for field_name, previous_name in changed_fields.items():
        variant_names = field_variants.get(field_name, ())
        field = instance._meta.get_field(field_name)
        storage = field.storage
        current_file = getattr(instance, field_name)
        current_name = current_file.name if current_file else ""

        if previous_name and previous_name != current_name:
            delete_variant_files(storage, previous_name, variant_names)

        if current_name:
            generate_image_variants(current_file, variant_names)


def generate_image_variants(image_field, variant_names):
    if not image_field or not image_field.name:
        return

    storage = image_field.storage
    source_name = image_field.name

    if not storage.exists(source_name):
        return

    with storage.open(source_name, "rb") as source_file:
        with Image.open(source_file) as source_image:
            normalized_image = ImageOps.exif_transpose(source_image)
            normalized_image.load()

            for variant_name in variant_names:
                spec = IMAGE_VARIANT_SPECS[variant_name]
                variant_path = build_variant_name(source_name, variant_name)
                rendered = render_variant(normalized_image, spec)

                buffer = BytesIO()
                save_kwargs = {"format": spec.format}
                if spec.format == "WEBP":
                    save_kwargs.update({"quality": spec.quality, "method": 6})
                elif spec.format == "PNG":
                    save_kwargs.update({"optimize": True})

                rendered.save(buffer, **save_kwargs)
                if storage.exists(variant_path):
                    storage.delete(variant_path)
                storage.save(variant_path, ContentFile(buffer.getvalue()))


def delete_variant_files(storage, source_name, variant_names):
    for variant_name in variant_names:
        variant_path = build_variant_name(source_name, variant_name)
        if storage.exists(variant_path):
            storage.delete(variant_path)


def build_variant_name(source_name, variant_name):
    spec = IMAGE_VARIANT_SPECS[variant_name]
    root, _ = splitext(source_name)
    return f"{root}__{variant_name}.{spec.extension}"


def render_variant(source_image, spec):
    working = source_image.copy()
    if spec.mode == "cover":
        variant = ImageOps.fit(working, (spec.width, spec.height), method=Image.Resampling.LANCZOS)
    elif spec.mode == "contain":
        contained = ImageOps.contain(working, (spec.width, spec.height), method=Image.Resampling.LANCZOS)
        background_mode = "RGBA" if image_has_alpha(contained) else "RGB"
        fill = (255, 255, 255, 0) if background_mode == "RGBA" else (255, 255, 255)
        variant = Image.new(background_mode, (spec.width, spec.height), fill)
        offset = ((spec.width - contained.width) // 2, (spec.height - contained.height) // 2)
        variant.paste(contained, offset, contained if image_has_alpha(contained) else None)
    else:
        raise ValueError(f"Unsupported variant mode: {spec.mode}")

    return convert_output_mode(variant, spec.format)


def image_has_alpha(image):
    return "A" in image.getbands() or (image.mode == "P" and "transparency" in image.info)


def convert_output_mode(image, output_format):
    if output_format == "PNG":
        if image_has_alpha(image):
            return image.convert("RGBA")
        return image.convert("RGB")

    if image_has_alpha(image):
        return image.convert("RGBA")
    return image.convert("RGB")


def get_image_variant_url(image_field, variant_name):
    if not image_field or not getattr(image_field, "name", ""):
        return ""

    cache = getattr(image_field, "_variant_url_cache", None)
    if cache is None:
        cache = {}
        setattr(image_field, "_variant_url_cache", cache)

    if variant_name in cache:
        return cache[variant_name]

    variant_path = build_variant_name(image_field.name, variant_name)
    if image_field.storage.exists(variant_path):
        cache[variant_name] = image_field.storage.url(variant_path)
    else:
        cache[variant_name] = image_field.url
    return cache[variant_name]
