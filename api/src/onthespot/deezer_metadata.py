"""Deezer catalogue normalization and native, multi-value FLAC tags.

Field names follow the user's local OneTagger mapping. This implementation is
independent; no OneTagger or Streamrip source is incorporated.
"""

import re

from mutagen.flac import FLAC


def unique_names(values):
    result, seen = [], set()
    for value in values:
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result


def performers(data):
    primary = (data.get("artist") or {}).get("name")
    names = [
        person.get("name")
        for person in data.get("contributors") or []
        if str(person.get("role") or "").strip().casefold()
        in {"", "main", "featured", "featuring", "performer", "primary"}
    ]
    names = unique_names(names)
    if primary and primary.strip().casefold() not in {
        name.casefold() for name in names
    }:
        names.insert(0, primary)
    return unique_names(names)


def normalize_metadata(track, album, tracks, separator="; "):
    artists, album_artists = performers(track), performers(album)
    genres = unique_names(
        genre.get("name") for genre in (album.get("genres") or {}).get("data", [])
    )
    disc = int(track.get("disk_number") or 1)
    disc_tracks = [
        entry for entry in tracks if int(entry.get("disk_number") or 1) == disc
    ]
    position = track.get("track_position")
    if not position:
        position = next(
            (
                n
                for n, entry in enumerate(disc_tracks, 1)
                if str(entry.get("id")) == str(track.get("id"))
            ),
            None,
        )
    isrc = re.sub(r"[\s-]", "", str(track.get("isrc") or "")).upper()
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", isrc):
        isrc = ""
    date = str(track.get("release_date") or album.get("release_date") or "")
    return {
        "title": track.get("title") or "",
        "isrc": isrc,
        "item_url": track.get("link") or "",
        "length": str(int(track.get("duration") or 0) * 1000),
        "track_number": position,
        "total_tracks": len(disc_tracks),
        "disc_number": disc,
        "total_discs": max([int(t.get("disk_number") or 1) for t in tracks] or [disc]),
        "release_year": date[:4],
        "release_date": date,
        "explicit": track.get("explicit_lyrics"),
        "bpm": track.get("bpm"),
        "artists": separator.join(artists),
        "artist_names": artists,
        "album_artists": separator.join(album_artists),
        "album_artist_names": album_artists,
        "genre": separator.join(genres),
        "genre_names": genres,
        "label": album.get("label") or "",
        "upc": str(album.get("upc") or ""),
        "image_url": album.get("cover_xl")
        or (track.get("album") or {}).get("cover_xl"),
        "album_name": album.get("title")
        or (track.get("album") or {}).get("title")
        or "",
        "album_type": album.get("record_type"),
        "is_playable": track.get("readable", True),
        "item_id": str(track.get("id") or ""),
    }


def write_deezer_tags(path, metadata, enabled=lambda key: True):
    """Write separate values without splitting punctuation in artist names."""
    audio = FLAC(path)
    for setting, field, values in (
        ("artist", "ARTIST", metadata.get("artist_names", [])),
        ("albumartist", "ALBUMARTIST", metadata.get("album_artist_names", [])),
        ("genre", "GENRE", metadata.get("genre_names", [])),
        ("label", "PUBLISHER", [metadata.get("label")]),
        ("isrc", "ISRC", [metadata.get("isrc")]),
    ):
        if enabled("embed_" + setting):
            audio[field] = unique_names(values)
    if enabled("embed_label"):
        audio.pop("LABEL", None)
    for field, key in (("BARCODE", "upc"), ("DATE", "release_date")):
        value = metadata.get(key)
        if value and (field != "DATE" or enabled("embed_year")):
            audio[field] = [str(value)]
    for field, key, total in (
        ("TRACKNUMBER", "track_number", "total_tracks"),
        ("DISCNUMBER", "disc_number", "total_discs"),
    ):
        if enabled(
            "embed_tracknumber" if field == "TRACKNUMBER" else "embed_discnumber"
        ):
            if metadata.get(key):
                audio[field] = [str(metadata[key])]
            if metadata.get(total):
                audio["TRACKTOTAL" if field == "TRACKNUMBER" else "DISCTOTAL"] = [
                    str(metadata[total])
                ]
    for field in ("COMMENT", "DESCRIPTION"):
        if field in audio:
            audio[field] = [
                value
                for value in audio[field]
                if not re.fullmatch(r"\s*\d{12,14}_\d+_\d+\s*", value)
            ]
    audio.clear_pictures()
    audio.save()
