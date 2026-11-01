# OnTheSpot fork

This is a separate project based on upstream tag `v2.0.3`, commit
`b68071f0bf2b2b427b8e5c94d2f6d46f78de53a2`. Read `DEVELOPMENT.md` and
`docs/FORK_STATUS.md` before continuing. Preserve unrelated local changes.

- Own repository, environment, configuration, credentials, cache and downloads.
  Streamrip & GUI and Qobux-DL GUI are independent sibling projects; do not edit
  them or import their credentials as part of routine work here.
- Deezer: offer FLAC_24 followed by FLAC. Fresh FLAC retry once. Never negotiate,
  accept or transcode a lossy source into a supposedly lossless download.
- Keep delivered bit depth, rate and channels without a resolution ceiling.
  Validate actual FLAC and the final audio properties/checksum before success.
- Preserve all credited performing artists as separate ARTIST values; composers
  and producers do not become performers solely because of their credits.
- Native FLAC fields: ARTIST, ALBUMARTIST, ISRC, PUBLISHER, GENRE, BARCODE,
  TRACKNUMBER, TRACKTOTAL, DISCNUMBER, DISCTOTAL. Cover only in album directory.
- Local OneTagger fork is a behavior/field reference. Do not copy source across
  projects without examining license compatibility. Retain upstream licensing.
- Never publish ARL, credentials, tokens, account config or signed media URLs.
- Run the targeted Deezer tests plus relevant regression/build checks. Record
  actual failures honestly; upstream 2.0.3 has existing failing tests.
