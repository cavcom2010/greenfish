"""
Fetch reviewed food photography from Pixabay for menu items.

The safe workflow is:
    python manage.py fetch_menu_images --dry-run --output /tmp/greenfish-pixabay.csv
    # mark approved rows in the CSV
    python manage.py fetch_menu_images --apply-approved /tmp/greenfish-pixabay.csv
"""
from __future__ import annotations

import csv
import io
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from PIL import Image, ImageOps

from apps.menu.models import MenuItem


PIXABAY_API_URL = "https://pixabay.com/api/"
COMMAND_VERSION = "greenfish-pixabay-v1"
SEARCH_TIMEOUT_SECONDS = 15
DOWNLOAD_TIMEOUT_SECONDS = 25
REQUEST_DELAY_SECONDS = 0.7
CANDIDATES_PER_ITEM = 3
TARGET_MAX_SIZE = (1600, 1600)
TARGET_QUALITY = 86

CSV_FIELDS = [
    "approved",
    "item_id",
    "item_name",
    "category",
    "query",
    "pixabay_id",
    "page_url",
    "contributor",
    "preview_url",
    "image_url",
    "tags",
]

QUERY_OVERRIDES = {
    "sadza": "maize meal porridge plate",
    "rice": "rice beans plate",
    "beans": "rice beans plate",
    "beef": "beef stew plate",
    "chicken": "chicken stew plate",
    "stew": "meat stew bowl",
    "vegetables": "cooked greens vegetables plate",
    "muriwo": "cooked greens vegetables plate",
    "drink": "soft drink bottle",
}

SKIP_KEYWORDS = {
    "water",
    "sprite",
    "fanta",
    "coca-cola",
    "coke",
}


class Command(BaseCommand):
    help = "Create and apply reviewed Pixabay food image candidates for menu items."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Search Pixabay and write candidates without saving images.")
        parser.add_argument("--output", type=str, default="", help="CSV path for --dry-run candidates.")
        parser.add_argument("--apply-approved", type=str, default="", help="CSV path containing approved rows to import.")
        parser.add_argument("--limit", type=int, default=0, help="Maximum number of menu items to search.")
        parser.add_argument("--category", type=str, default="", help="Only search items in this category name/id.")
        parser.add_argument("--force", action="store_true", help="Include/replace items that already have images.")

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply_approved"]:
            raise CommandError("Use either --dry-run or --apply-approved, not both.")
        if not options["dry_run"] and not options["apply_approved"]:
            raise CommandError("Use --dry-run first, then --apply-approved after reviewing the CSV.")

        api_key = getattr(settings, "PIXABAY_API_KEY", "").strip()
        if not api_key and options["dry_run"]:
            raise CommandError("PIXABAY_API_KEY is not configured.")

        if options["apply_approved"]:
            self._apply_approved(Path(options["apply_approved"]), force=options["force"])
            return

        output_path = Path(options["output"]) if options["output"] else None
        if not output_path:
            raise CommandError("--dry-run requires --output <csv-path>.")
        self._write_candidates(
            api_key=api_key,
            output_path=output_path,
            limit=options["limit"],
            category=options["category"],
            force=options["force"],
        )

    def _write_candidates(self, *, api_key, output_path, limit, category, force):
        items = self._candidate_items(force=force, category=category, limit=limit)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for item in items:
                if self._should_skip_item(item):
                    self.stdout.write(f"Skipping low-yield item: {item.name}")
                    continue

                query = self._build_query(item)
                hits = self._search(api_key, query)
                for hit in hits[:CANDIDATES_PER_ITEM]:
                    writer.writerow(self._candidate_row(item, query, hit))
                    written += 1
                self.stdout.write(f"{item.name}: {len(hits[:CANDIDATES_PER_ITEM])} candidate(s)")
                time.sleep(REQUEST_DELAY_SECONDS)

        self.stdout.write(self.style.SUCCESS(f"Wrote {written} candidate row(s) to {output_path}"))

    def _apply_approved(self, csv_path, *, force):
        if not csv_path.exists():
            raise CommandError(f"Approved CSV does not exist: {csv_path}")

        processed = skipped = failed = 0
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if not self._is_approved(row):
                    skipped += 1
                    continue
                try:
                    item = MenuItem.objects.get(pk=row["item_id"])
                    if item.image and not force:
                        self.stdout.write(f"Skipping {item.name}: already has an image")
                        skipped += 1
                        continue
                    image_bytes = self._download_and_prepare(row["image_url"])
                    filename = f"{self._safe_stem(item)}-pixabay-{row.get('pixabay_id') or 'image'}.jpg"
                    item.image.save(filename, ContentFile(image_bytes), save=False)
                    item.image_source_metadata = self._metadata(row)
                    item.save()
                    processed += 1
                    self.stdout.write(self.style.SUCCESS(f"Saved image for {item.name}"))
                except Exception as exc:
                    failed += 1
                    self.stdout.write(self.style.ERROR(f"Failed row {row.get('item_id')}: {exc}"))

        self.stdout.write(self.style.SUCCESS(f"Done. Imported {processed}, skipped {skipped}, failed {failed}."))

    def _candidate_items(self, *, force, category, limit):
        qs = MenuItem.objects.select_related("category").order_by("category__sort_order", "sort_order", "name")
        if not force:
            qs = qs.filter(image="")
        if category:
            if category.isdigit():
                qs = qs.filter(category_id=int(category))
            else:
                qs = qs.filter(category__name__iexact=category)
        if limit:
            qs = qs[:limit]
        return list(qs)

    def _build_query(self, item):
        text = f"{item.name} {item.category.name if item.category else ''}".strip().lower()
        for keyword, query in QUERY_OVERRIDES.items():
            if keyword in text:
                return query
        return f"{item.name} food plate"

    def _should_skip_item(self, item):
        text = f"{item.name} {item.category.name if item.category else ''}".lower()
        return any(keyword in text for keyword in SKIP_KEYWORDS)

    def _search(self, api_key, query):
        response = requests.get(
            PIXABAY_API_URL,
            params={
                "key": api_key,
                "q": query,
                "image_type": "photo",
                "category": "food",
                "orientation": "horizontal",
                "safesearch": "true",
                "per_page": 10,
                "order": "popular",
            },
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json().get("hits", [])

    def _candidate_row(self, item, query, hit):
        image_url = hit.get("largeImageURL") or hit.get("webformatURL") or hit.get("previewURL") or ""
        return {
            "approved": "",
            "item_id": item.pk,
            "item_name": item.name,
            "category": item.category.name if item.category else "",
            "query": query,
            "pixabay_id": hit.get("id", ""),
            "page_url": hit.get("pageURL", ""),
            "contributor": hit.get("user", ""),
            "preview_url": hit.get("previewURL", ""),
            "image_url": image_url,
            "tags": hit.get("tags", ""),
        }

    def _download_and_prepare(self, image_url):
        if not image_url:
            raise ValueError("Missing image_url")
        response = requests.get(image_url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
        with Image.open(io.BytesIO(response.content)) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            elif image.mode == "L":
                image = image.convert("RGB")
            image.thumbnail(TARGET_MAX_SIZE, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=TARGET_QUALITY, optimize=True)
            return buffer.getvalue()

    def _metadata(self, row):
        return {
            "provider": "pixabay",
            "pixabay_id": str(row.get("pixabay_id", "")),
            "page_url": row.get("page_url", ""),
            "contributor": row.get("contributor", ""),
            "query": row.get("query", ""),
            "selected_image_url": row.get("image_url", ""),
            "tags": row.get("tags", ""),
            "imported_at": timezone.now().isoformat(),
            "command_version": COMMAND_VERSION,
        }

    def _is_approved(self, row):
        return str(row.get("approved", "")).strip().lower() in {"1", "y", "yes", "true", "approved"}

    def _safe_stem(self, item):
        return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in item.name.lower()).strip("-")
