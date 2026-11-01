# OnTheSpot 2.0.3 FLAC fork

Repository: https://github.com/tfgdngfxgfb/onthespot

This project starts at upstream `v2.0.3` / `b68071f0bf2b2b427b8e5c94d2f6d46f78de53a2`.
Development branch: `codex/deezer-flac24-metadata`. It retains the 2.0.3
FastAPI/React interface and upstream license. It does not replace either sibling
Streamrip & GUI or Qobux-DL GUI.

## Run on Windows

From CMD in this directory:

```bat
setup.cmd
start.cmd
```

Open http://127.0.0.1:6767. Stop with Ctrl+C. `start.cmd` uses the project's
`api/.venv`, `.local/config` and `.local/cache`; downloads default to `downloads/`.
No PowerShell execution-policy change is required. Accounts are configured in
this application's Accounts page. No account has been imported from another
project. Configuration and its encrypted credential store remain gitignored.

Setup requires uv, Python 3.12 (downloaded by uv), FFmpeg and Node.js 22 LTS.
The initial local installation also has a checksum-verified portable Node under
`.local/node`; setup.cmd uses it when present. The API's dependency lock pins
librespot to the same commit as the original 2.0.3 lock. Python 3.12 is the
validated runtime for this fork; Streamrip's Python policy is independent.

## Deezer behavior

- Request FULL FLAC_24 then FLAC, irrespective of nominal profile bitrate or
  FILESIZE_FLAC. Failure or a mislabeled lossy source causes one fresh FLAC-only
  request. If FLAC cannot be obtained, the job is unavailable/failed with an
  explicit reason; no MP3 is saved or converted to FLAC.
- Deezer output is always native FLAC, including when an old MP3 profile is
  selected. Other services retain their format profiles. New installations
  select the FLAC profile by default.
- Verify FLAC magic/STREAMINFO and fully decode the downloaded audio with
  FFmpeg. After processing compare bit depth, sample rate, channels, total
  samples and FLAC STREAMINFO PCM MD5 against the verified source. Matching
  source/output FLAC is copied, never resampled to the 44100-Hz config default.
- No upper resolution limit is imposed. FLAC_24 is a negotiation preference,
  not proof that the delivered file is 24-bit. Actual resolution is displayed
  in the queue item's details and recorded in the log without signed URLs.
- The original track ID must match source and metadata IDs. Alternate recording
  IDs are blocked instead of inheriting a different recording's ISRC.
- Track/album contributors provide separate artist values. Label and genre come
  from the album endpoint; ISRC comes from the exact track endpoint. Missing
  fields remain absent, rather than inferred or invented. Disc track numbers
  and totals are counted within each disc. Pagination follows the public API.
- Native tag writes use PUBLISHER rather than LABEL for FLAC, plus separate
  ARTIST, ALBUMARTIST and GENRE values. Band punctuation is preserved. UPC is
  BARCODE. Technical UPC_disc_track comments are removed. Cover is external.
- Deezer login and gateway requests use HTTPS. The fork does not scrape shared
  ARLs. Public configuration exports redact all credential-store secret fields.

An account, catalogue rights and the currently available Deezer source determine
the obtainable quality. Local generated-file tests do not prove that a particular
release/account will receive FLAC_24. A real authenticated download in this new
fork remains to be checked; no credential has been copied to do that test.

## Checks

```bat
api\.venv\Scripts\python.exe -m unittest discover -s api/tests -p test_deezer_lossless.py -v
api\.venv\Scripts\python.exe -m unittest discover -s api/tests -v
uvx ruff check api/src/onthespot/deezer_lossless.py api/src/onthespot/deezer_metadata.py api/tests/test_deezer_lossless.py
cd ui
npm.cmd run lint
npm.cmd run build
```

The full upstream suite currently contains known failures. See
`docs/FORK_STATUS.md` for the baseline comparison; do not claim full regression
success from the targeted tests alone. No automatic binary update installs are
offered by this source fork; use Git and rerun setup.cmd for reviewed updates.

The public API cache now keeps the response-cache write in the same per-host
critical section as dispatch, preventing simultaneous identical jobs from
spending multiple provider requests before the first result reaches the cache.
