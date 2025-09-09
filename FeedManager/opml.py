from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TextIO, cast
from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings

import pytz
from defusedxml import ElementTree as SafeET
from defusedxml import minidom

from .models import OriginalFeed, Tag


@dataclass
class ImportResult:
    feeds_created: int
    feeds_updated: int
    tags_created: int
    feeds_seen: int


def _parse_opml_outline_for_import(
    node: SafeET.Element, folder_stack: list[str] | None = None
) -> list[tuple[str, str | None, list[str]]]:
    """
    Recursively walk an OPML outline node and return a list of (xmlUrl, title, tags).
    - folder_stack accumulates folder names (used as tags) from parent outlines.
    - Also honors the `category` attribute on feed outlines if present (comma-separated).
    """
    results: list[tuple[str, str | None, list[str]]] = []
    if folder_stack is None:
        folder_stack = []

    # A feed outline has an xmlUrl attribute. A folder outline has children `outline`.
    xml_url = node.attrib.get("xmlUrl")
    if xml_url:
        # Feed outline
        title = node.attrib.get("title") or node.attrib.get("text")
        tags: list[str] = list(folder_stack)
        # Parse category attribute if present (comma-separated values)
        category = node.attrib.get("category")
        if category:
            # Some OPMLs separate by comma and space, normalize by split(',') then strip
            for raw in category.split(","):
                name = raw.strip()
                if name and name not in tags:
                    tags.append(name)
        results.append((xml_url, title, tags))
        return results

    # Folder outline: recurse into children with updated folder stack
    label = node.attrib.get("title") or node.attrib.get("text")
    new_stack = folder_stack.copy()
    if label:
        new_stack.append(label)

    for child in node.findall("outline"):
        results.extend(_parse_opml_outline_for_import(child, new_stack))

    return results


def import_original_feeds_from_opml(file_obj: TextIO) -> ImportResult:
    """
    Import OriginalFeed items from an OPML file-like object, generating Tag records based
    on folder structure and category attributes.

    - De-duplicates by feed URL (xmlUrl).
    - Adds tags for each folder level encountered.
    - Adds tags for any `category` attribute on feed nodes.
    """
    tree = SafeET.parse(file_obj)
    root = tree.getroot()
    body = root.find("body")
    if body is None:
        return ImportResult(feeds_created=0, feeds_updated=0, tags_created=0, feeds_seen=0)

    outlines = body.findall("outline")
    items: list[tuple[str, str | None, list[str]]] = []
    for node in outlines:
        items.extend(_parse_opml_outline_for_import(node, []))

    feeds_created = 0
    feeds_updated = 0
    tags_created = 0
    tag_cache: dict[str, Tag] = {t.name: t for t in Tag.objects.all()}

    for url, title, tags in items:
        feed, created = OriginalFeed.objects.get_or_create(url=url)
        if created:
            feeds_created += 1
        else:
            feeds_updated += 1

        # Prefer to set title if created or title is empty and we have a candidate
        if title and (created or not feed.title or feed.title == feed.url):
            feed.title = title
            feed.save(update_fields=["title"])  # minimal UPDATE

        # Attach tags
        for tag_name in tags:
            if not tag_name:
                continue
            tag = tag_cache.get(tag_name)
            if tag is None:
                tag, _created = Tag.objects.get_or_create(name=tag_name)
                tag_cache[tag_name] = tag
                if _created:
                    tags_created += 1
            feed.tags.add(tag)

    return ImportResult(
        feeds_created=feeds_created,
        feeds_updated=feeds_updated,
        tags_created=tags_created,
        feeds_seen=len(items),
    )


def _append_feed_outline(parent: Element, feed: OriginalFeed) -> None:
    outline = SubElement(parent, "outline")
    text = feed.title or feed.url
    outline.set("text", text)
    outline.set("title", text)
    outline.set("type", "rss")
    outline.set("xmlUrl", feed.url)
    outline.set("htmlUrl", feed.url)
    # Also include categories for interoperability
    tag_names = list(feed.tags.values_list("name", flat=True))
    if tag_names:
        outline.set("category", ", ".join(sorted(tag_names)))


def export_original_feeds_as_opml(
    feeds: Iterable[OriginalFeed], *, group_by_tags: bool = False
) -> str:
    """
    Build an OPML string for the provided OriginalFeed iterable.
    - When group_by_tags=False: outputs a flat list of outlines (with category attribute set).
    - When group_by_tags=True: nests feeds under tag folders; feeds with multiple tags appear under each tag.
      Feeds with no tags are placed at the root.
    """
    opml = Element("opml")
    opml.set("version", "2.0")

    # Head
    head = SubElement(opml, "head")
    title = SubElement(head, "title")
    title.text = "RSSBrew Original Feeds Export"
    date_created = SubElement(head, "dateCreated")
    tz = pytz.timezone(getattr(settings, "TIME_ZONE", "UTC"))
    date_created.text = datetime.now(tz).strftime("%a, %d %b %Y %H:%M:%S %z")

    # Body
    body = SubElement(opml, "body")

    feeds_list = list(feeds)
    if not group_by_tags:
        for feed in feeds_list:
            _append_feed_outline(body, feed)
    else:
        # Build mapping tag -> list[feed]
        feeds_by_tag: dict[str, list[OriginalFeed]] = {}
        untagged: list[OriginalFeed] = []
        for feed in feeds_list:
            feed_tags = list(feed.tags.values_list("name", flat=True))
            if not feed_tags:
                untagged.append(feed)
            for t in feed_tags:
                feeds_by_tag.setdefault(t, []).append(feed)

        # Deterministic order
        for tag_name in sorted(feeds_by_tag.keys(), key=str.casefold):
            tag_outline = SubElement(body, "outline")
            tag_outline.set("text", tag_name)
            tag_outline.set("title", tag_name)
            for feed in feeds_by_tag[tag_name]:
                _append_feed_outline(tag_outline, feed)

        # Add untagged feeds at root at the end
        for feed in untagged:
            _append_feed_outline(body, feed)

    # Prettify
    return cast(str, minidom.parseString(tostring(opml, encoding="unicode")).toprettyxml(indent="  "))
