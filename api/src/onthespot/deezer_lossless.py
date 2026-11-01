"""Strict Deezer source negotiation; never offer or accept a lossy fallback.

No account data or media responses are logged. Resolution is read from FLAC
STREAMINFO, not inferred from a requested format or nominal profile bitrate.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import requests
from mutagen import MutagenError
from mutagen.flac import FLAC

from .resources.exceptions import DownloadCancelled, TrackUnavailableError


class LosslessUnavailable(TrackUnavailableError):
    """The exact requested recording could not be obtained as valid FLAC."""


@dataclass(frozen=True)
class FlacQuality:
    bits: int
    rate: int
    channels: int
    samples: int
    md5: int

    @property
    def description(self):
        return f"FLAC {self.bits}-bit / {self.rate} Hz / {self.channels} ch"


def inspect_flac(path, ffmpeg=None):
    """Read actual format, optionally decoding every frame to reject corruption."""
    try:
        with open(path, "rb") as stream:
            if stream.read(4) != b"fLaC":
                raise ValueError("The delivered audio is not native FLAC.")
        info = FLAC(path).info
        quality = FlacQuality(
            info.bits_per_sample,
            info.sample_rate,
            info.channels,
            info.total_samples,
            info.md5_signature,
        )
        if min(quality.bits, quality.rate, quality.channels, quality.samples) <= 0:
            raise ValueError("Invalid or empty FLAC audio.")
    except (OSError, MutagenError, ValueError):
        raise ValueError("Invalid FLAC source or incomplete audio header.") from None
    if ffmpeg:
        result = subprocess.run(
            [
                str(ffmpeg),
                "-v",
                "error",
                "-xerror",
                "-nostdin",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-f",
                "null",
                "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode:
            raise ValueError("FLAC audio failed full frame decoding.")
    return quality


def _media_source(payload):
    media = [
        entry
        for row in payload.get("data", [])
        for entry in row.get("media", [])
        if entry.get("type") == "FULL" and entry.get("format") in {"FLAC_24", "FLAC"}
    ]
    media.sort(key=lambda entry: entry.get("format") != "FLAC_24")
    for entry in media:
        cipher = entry.get("cipher", {})
        cipher = cipher.get("type") if isinstance(cipher, dict) else cipher
        if cipher not in {"BF_CBC_STRIPE", "NONE"}:
            continue
        for source in entry.get("sources", []):
            url = source.get("url", "")
            if urlsplit(url).scheme == "https" and urlsplit(url).hostname:
                return url, cipher
    raise LosslessUnavailable("Deezer did not offer a full-length FLAC source.")


def _write_stream(response, path, cipher, decrypt_block, check_cancelled, progress):
    size = int(response.headers.get("content-length", 0))
    received = 0
    pending = bytearray()
    block_index = 0
    with open(path, "wb") as output:
        for chunk in response.iter_content(chunk_size=65536):
            check_cancelled()
            if not chunk:
                continue
            received += len(chunk)
            pending.extend(chunk)
            while len(pending) >= 2048:
                block = bytes(pending[:2048])
                del pending[:2048]
                if cipher == "BF_CBC_STRIPE" and block_index % 3 == 0:
                    block = decrypt_block(block)
                output.write(block)
                block_index += 1
            progress(received, size)
        output.write(pending)
    check_cancelled()
    if size and received != size:
        raise ValueError("Incomplete Deezer transfer.")


def download_lossless(
    token,
    track_id,
    destination,
    song_loader,
    decrypt_block,
    check_cancelled,
    progress,
    validator=inspect_flac,
    http_get=None,
):
    """Try FLAC_24 then FLAC; retry once with fresh token and FLAC only.

    FILESIZE_FLAC is deliberately not a gate: it does not reliably describe
    current account-specific Hi-Res availability. Never follow another track ID
    while retaining the requested recording's ISRC and metadata.
    """
    http_get = http_get or requests.get
    destination = Path(destination)
    partial = destination.with_name(destination.name + ".part")
    transport_failed = False
    try:
        for formats in (("FLAC_24", "FLAC"), ("FLAC",)):
            check_cancelled()
            try:
                song = song_loader()
                if str(song.get("SNG_ID")) != str(track_id):
                    raise LosslessUnavailable(
                        "Deezer returned a different recording; download blocked."
                    )
                if not song.get("TRACK_TOKEN"):
                    raise LosslessUnavailable("Deezer did not provide a track token.")
                with token["session"].post(
                    "https://media.deezer.com/v1/get_url",
                    json={
                        "license_token": token["license_token"],
                        "media": [
                            {
                                "type": "FULL",
                                "formats": [
                                    {"cipher": "BF_CBC_STRIPE", "format": fmt}
                                    for fmt in formats
                                ],
                            }
                        ],
                        "track_tokens": [song["TRACK_TOKEN"]],
                    },
                    timeout=(10, 60),
                ) as response:
                    response.raise_for_status()
                    url, cipher = _media_source(response.json())
                # No ARL or account headers are sent to the media CDN.
                with http_get(url, stream=True, timeout=(10, 60)) as response:
                    response.raise_for_status()
                    _write_stream(
                        response,
                        partial,
                        cipher,
                        decrypt_block,
                        check_cancelled,
                        progress,
                    )
                quality = validator(partial)
                check_cancelled()
                os.replace(partial, destination)
                return quality
            except DownloadCancelled:
                raise
            except requests.RequestException:
                transport_failed = True
            except (
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
                TrackUnavailableError,
            ):
                pass
            finally:
                partial.unlink(missing_ok=True)
        if transport_failed:
            raise RuntimeError(
                "Deezer FLAC request failed after two attempts; check connection/account."
            )
        raise LosslessUnavailable(
            "FLAC unavailable or invalid after a fresh FLAC retry; MP3 fallback blocked."
        )
    finally:
        partial.unlink(missing_ok=True)
