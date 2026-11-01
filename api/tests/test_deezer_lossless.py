"""Offline protocol tests with real, generated FLAC audio and striped encryption."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from _support import TEST_ROOT  # noqa: F401 - isolated imports
from Cryptodome.Cipher import Blowfish
from mutagen.flac import FLAC, Picture

from onthespot.deezer_lossless import (
    LosslessUnavailable,
    download_lossless,
    inspect_flac,
)
from onthespot.deezer_metadata import normalize_metadata, write_deezer_tags
from onthespot.resources.exceptions import DownloadCancelled

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

FFMPEG = shutil.which("ffmpeg")
KEY = b"0123456789abcdef"
IV = bytes(range(8))


class Response:
    def __init__(self, payload=None, body=b"", cipher="BF_CBC_STRIPE", fmt="FLAC_24"):
        self.payload = (
            payload
            if payload is not None
            else {
                "data": [
                    {
                        "media": [
                            {
                                "type": "FULL",
                                "format": fmt,
                                "cipher": {"type": cipher},
                                "sources": [{"url": "https://cdn.example.test/audio"}],
                            }
                        ]
                    }
                ]
            }
        )
        self.body = body
        self.headers = {"content-length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload

    def iter_content(self, chunk_size):
        # Deliberately misalign HTTP chunks and cipher stripes.
        for index in range(0, len(self.body), 777):
            yield self.body[index : index + 777]


def encrypted(data):
    result = bytearray()
    for index, offset in enumerate(range(0, len(data), 2048)):
        block = data[offset : offset + 2048]
        if index % 3 == 0 and len(block) == 2048:
            block = Blowfish.new(KEY, Blowfish.MODE_CBC, IV).encrypt(block)
        result.extend(block)
    return bytes(result)


@unittest.skipUnless(FFMPEG, "FFmpeg required for real audio verification")
class LosslessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ots-deezer-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.destination = self.root / "download.flac"
        self.session = Mock()
        self.session.post.return_value = Response()
        self.loader = Mock(
            return_value={
                "SNG_ID": "123",
                "TRACK_TOKEN": "test-track-token",
                "FILESIZE_FLAC": 0,
            }
        )

    def fixture(self, rate=192000, bits=24):
        path = self.root / f"fixture-{bits}-{rate}.flac"
        subprocess.run(
            [
                FFMPEG,
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=997:sample_rate={rate}:duration=0.3",
                "-ac",
                "2",
                "-c:a",
                "flac",
                "-sample_fmt",
                "s16" if bits == 16 else "s32",
                "-y",
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        return path.read_bytes()

    def download(self, body, **kwargs):
        self.http_get = Mock(return_value=Response(body=encrypted(body)))
        return download_lossless(
            {"session": self.session, "license_token": "test-license"},
            "123",
            self.destination,
            self.loader,
            lambda block: Blowfish.new(KEY, Blowfish.MODE_CBC, IV).decrypt(block),
            kwargs.pop("cancel", lambda: None),
            lambda *_: None,
            validator=lambda path: inspect_flac(path, FFMPEG),
            http_get=self.http_get,
            **kwargs,
        )

    def offered(self):
        return [
            [f["format"] for f in call.kwargs["json"]["media"][0]["formats"]]
            for call in self.session.post.call_args_list
        ]

    def test_actual_hires_and_no_resolution_ceiling(self):
        for bits, rate in ((16, 44100), (24, 96000), (24, 192000), (24, 384000)):
            with self.subTest(bits=bits, rate=rate):
                data = self.fixture(rate, bits)
                quality = self.download(data)
                self.assertEqual((quality.bits, quality.rate), (bits, rate))
                self.assertEqual(self.destination.read_bytes(), data)
        self.assertTrue(
            all(formats == ["FLAC_24", "FLAC"] for formats in self.offered())
        )

    def test_cd_flac_fallback_is_allowed(self):
        self.session.post.return_value = Response(fmt="FLAC")
        self.assertEqual(self.download(self.fixture(44100, 16)).bits, 16)

    def test_lossy_response_retries_fresh_flac_without_mp3_offer(self):
        self.session.post.side_effect = [Response(fmt="MP3_320"), Response(fmt="FLAC")]
        self.assertEqual(self.download(self.fixture(44100, 16)).bits, 16)
        self.assertEqual(self.offered(), [["FLAC_24", "FLAC"], ["FLAC"]])
        self.assertEqual(self.loader.call_count, 2)

    def test_mislabeled_mp3_is_blocked_and_existing_output_survives(self):
        self.destination.write_bytes(b"existing verified output")
        with self.assertRaises(LosslessUnavailable):
            self.download(b"ID3" + bytes(10000))
        self.assertEqual(self.offered(), [["FLAC_24", "FLAC"], ["FLAC"]])
        self.assertEqual(self.destination.read_bytes(), b"existing verified output")
        self.assertFalse(self.destination.with_suffix(".flac.part").exists())

    def test_corrupt_audio_frames_are_rejected(self):
        data = self.fixture()
        with self.assertRaises(LosslessUnavailable):
            self.download(data[:-2000])
        self.assertFalse(self.destination.exists())

    def test_new_flac_transfer_after_invalid_hires(self):
        good = self.fixture(44100, 16)
        get = Mock(
            side_effect=[
                Response(body=encrypted(b"ID3" + bytes(10000))),
                Response(body=encrypted(good)),
            ]
        )
        result = download_lossless(
            {"session": self.session, "license_token": "test"},
            "123",
            self.destination,
            self.loader,
            lambda block: Blowfish.new(KEY, Blowfish.MODE_CBC, IV).decrypt(block),
            lambda: None,
            lambda *_: None,
            http_get=get,
        )
        self.assertEqual(result.bits, 16)
        self.assertEqual(self.offered(), [["FLAC_24", "FLAC"], ["FLAC"]])

    def test_replacement_recording_is_not_downloaded_with_original_isrc(self):
        self.loader.return_value["SNG_ID"] = "456"
        with self.assertRaises(LosslessUnavailable):
            self.download(self.fixture())
        self.session.post.assert_not_called()
        self.http_get.assert_not_called()

    def test_cancelled_transfer_leaves_no_partial_audio(self):
        counter = 0

        def cancel():
            nonlocal counter
            counter += 1
            if counter > 2:
                raise DownloadCancelled()

        with self.assertRaises(DownloadCancelled):
            self.download(self.fixture(), cancel=cancel)
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.destination.with_suffix(".flac.part").exists())

    def test_network_errors_do_not_expose_signed_url_or_credentials(self):
        self.session.post.side_effect = requests.ConnectionError(
            "secret signed URL or credential"
        )
        with self.assertRaises(RuntimeError) as raised:
            self.download(self.fixture())
        self.assertNotIn("secret", str(raised.exception))
        self.assertEqual(len(self.offered()), 2)

    def test_native_tag_values_and_audio_survive_finalize(self):
        self.destination.write_bytes(self.fixture())
        original = inspect_flac(self.destination)
        track = {
            "id": 123,
            "title": "Duet",
            "isrc": "us-abc-26-00001",
            "disk_number": 2,
            "track_position": 1,
            "artist": {"name": "Lead"},
            "contributors": [
                {"name": "Lead", "role": "Main"},
                {"name": "Guest", "role": "Featured"},
                {"name": "guest", "role": "Featured"},
                {"name": "Writer", "role": "Composer"},
                {"name": "Earth, Wind & Fire", "role": "Main"},
            ],
            "release_date": "2026-10-01",
        }
        album = {
            "artist": {"name": "Album Artist"},
            "title": "Album",
            "label": "Publisher",
            "upc": "00602557479614",
            "genres": {"data": [{"name": "Pop"}, {"name": "Soul"}]},
        }
        tracks = [
            {"id": 1, "disk_number": 1},
            {"id": 123, "disk_number": 2},
            {"id": 124, "disk_number": 2},
        ]
        metadata = normalize_metadata(track, album, tracks)
        audio = FLAC(self.destination)
        audio["COMMENT"] = ["00602557479614_2_1", "Keep user comment"]
        picture = Picture()
        picture.data = b"test picture"
        audio.add_picture(picture)
        audio.save()
        write_deezer_tags(self.destination, metadata)
        audio = FLAC(self.destination)
        self.assertEqual(audio["ARTIST"], ["Lead", "Guest", "Earth, Wind & Fire"])
        self.assertEqual(audio["ALBUMARTIST"], ["Album Artist"])
        self.assertEqual(audio["GENRE"], ["Pop", "Soul"])
        self.assertEqual(audio["PUBLISHER"], ["Publisher"])
        self.assertEqual(audio["ISRC"], ["USABC2600001"])
        self.assertEqual(audio["BARCODE"], ["00602557479614"])
        self.assertEqual(audio["DISCNUMBER"], ["2"])
        self.assertEqual(audio["TRACKNUMBER"], ["1"])
        self.assertEqual(audio["TRACKTOTAL"], ["2"])
        self.assertEqual(audio["DATE"], ["2026-10-01"])
        self.assertEqual(audio["COMMENT"], ["Keep user comment"])
        self.assertFalse(audio.pictures)
        self.assertEqual(inspect_flac(self.destination, FFMPEG), original)

    def queue_item(self):
        from onthespot.basemodels import QueueItem
        from onthespot.constants import ItemStatus

        return QueueItem(
            local_id=1,
            item_service="deezer",
            item_type="track",
            item_id="123",
            item_url="https://www.deezer.com/track/123",
            parent_category="track",
            item_status=ItemStatus.WAITING,
            download_profile={
                "id": "mp3-320",
                "name": "Legacy MP3",
                "format": "mp3",
                "bitrate": 320,
            },
        )

    def test_actual_finalization_preserves_24_192_despite_legacy_mp3_profile(self):
        from onthespot import downloader

        item = self.queue_item()
        downloader.DownloadWorker._get_target_format(item)
        self.assertEqual(item.target_format, "flac")
        source = self.root / "temporary.flac"
        source.write_bytes(self.fixture())
        original = inspect_flac(source)
        metadata = normalize_metadata(
            {
                "id": 123,
                "title": "Duet",
                "isrc": "USABC2600001",
                "artist": {"name": "Lead"},
                "contributors": [{"name": "Lead"}, {"name": "Guest"}],
                "track_position": 1,
            },
            {
                "title": "Album",
                "artist": {"name": "Lead"},
                "label": "Publisher",
                "genres": {"data": [{"name": "Pop"}]},
            },
            [{"id": 123}],
        )
        get = downloader.config.get
        overrides = {
            "_ffmpeg_bin_path": FFMPEG,
            "file_hertz": 44100,
            "save_album_cover": False,
            "embed_cover": False,
            "download_lyrics": False,
            "raw_media_download": False,
            "ffmpeg_args": [],
            "create_m3u_file": False,
        }
        with (
            patch.object(
                downloader.config,
                "get",
                side_effect=lambda key, default=None: overrides.get(
                    key, get(key, default)
                ),
            ),
            patch.object(downloader, "progress_hook"),
        ):
            _, final_path = downloader.DownloadWorker()._finalize_audio(
                item,
                metadata,
                "deezer",
                "track",
                "123",
                {},
                str(self.root / "final"),
                str(source),
                ".flac",
                "9216k",
            )
        self.assertEqual(inspect_flac(final_path, FFMPEG), original)
        self.assertEqual(FLAC(final_path)["ARTIST"], ["Lead", "Guest"])
        self.assertEqual(FLAC(final_path)["PUBLISHER"], ["Publisher"])
        self.assertEqual(item.source_quality, "FLAC 24-bit / 192000 Hz / 2 ch")
        self.assertFalse(source.exists())
        self.assertFalse((self.root / "final.mp3").exists())

    def test_download_adapter_works_with_real_queue_model(self):
        from onthespot import services_middleware

        body = self.fixture()
        token = {"session": self.session, "license_token": "test"}
        item = self.queue_item()
        with (
            patch.object(
                services_middleware, "get_song_info_from_deezer_website", self.loader
            ),
            patch(
                "onthespot.deezer_lossless.requests.get",
                return_value=Response(body=body, cipher="NONE"),
            ),
            patch.object(services_middleware, "progress_hook"),
        ):
            self.session.post.return_value = Response(cipher="NONE")
            extension, _ = services_middleware.download_deezer(
                item, "123", token, str(self.root / "adapter")
            )
        self.assertEqual(extension, ".flac")
        self.assertEqual((self.root / "adapter.flac").read_bytes(), body)

    def test_existing_mp3_does_not_satisfy_deezer_flac_job(self):
        from onthespot.downloader import DownloadWorker

        (self.root / "song.mp3").write_bytes(b"old MP3 stays untouched")
        self.assertFalse(
            DownloadWorker()._handle_existing_file(
                self.queue_item(),
                "deezer",
                "track",
                "123",
                {},
                {},
                str(self.root / "song"),
            )
        )

    def test_cover_is_only_saved_to_album_directory(self):
        from io import BytesIO

        from PIL import Image

        from onthespot import utils

        image = BytesIO()
        Image.new("RGB", (8, 8), "blue").save(image, format="PNG")
        self.destination.write_bytes(self.fixture())
        response = Mock(content=image.getvalue())
        get = utils.config.get
        overrides = {
            "save_album_cover": True,
            "embed_cover": True,
            "album_cover_format": "png",
        }
        with (
            patch.object(utils.requests, "get", return_value=response),
            patch.object(
                utils.config,
                "get",
                side_effect=lambda key, default=None: overrides.get(
                    key, get(key, default)
                ),
            ),
        ):
            utils.set_music_thumbnail(
                str(self.destination),
                {"image_url": "https://example.test/cover"},
                allow_embed=False,
            )
        self.assertTrue((self.root / "cover.png").is_file())
        self.assertFalse(FLAC(self.destination).pictures)


class MetadataTests(unittest.TestCase):
    def test_missing_contributors_keep_primary_without_splitting_band_name(self):
        metadata = normalize_metadata({"artist": {"name": "Simon & Garfunkel"}}, {}, [])
        self.assertEqual(metadata["artist_names"], ["Simon & Garfunkel"])
        self.assertEqual(metadata["isrc"], "")
        self.assertEqual(metadata["label"], "")
        self.assertEqual(metadata["genre_names"], [])

    def test_unusable_isrc_is_not_written_as_an_identifier(self):
        self.assertEqual(
            normalize_metadata({"isrc": "00602557479614_1_1"}, {}, [])["isrc"], ""
        )

    def test_deezer_pagination_and_ids_are_queue_compatible(self):
        from onthespot.api import deezer

        pages = [
            {
                "tracks": {
                    "data": [{"id": 123}],
                    "next": "https://api.deezer.com/album/1/tracks?index=1",
                }
            },
            {"data": [{"id": 124}]},
        ]
        with patch.object(deezer, "make_call", side_effect=pages):
            self.assertEqual(
                deezer.deezer_get_album_track_ids(None, "1"), ["123", "124"]
            )

    def test_metadata_cannot_silently_change_recording_identity(self):
        from onthespot.api import deezer
        from onthespot.resources.exceptions import TrackUnavailableError

        with (
            patch.object(deezer, "make_call", return_value={"id": 456}),
            self.assertRaises(TrackUnavailableError),
        ):
            deezer.deezer_get_track_metadata(None, "123", {})
