# Fork status — 2026-11-01

Base: upstream v2.0.3, b68071f0bf2b2b427b8e5c94d2f6d46f78de53a2.
Branch: codex/deezer-flac24-metadata. Remote: tfgdngfxgfb/onthespot.

Implemented strict FLAC_24/FLAC negotiation, bounded fresh FLAC retry, streaming
stripe decryption, partial-file cleanup/cancellation, verified native FLAC output,
preserved source resolution/checksum, contributor lists, label/genre/ISRC/native
tags, correct disc-relative numbering, public-API pagination and string queue IDs.
Added independent CMD setup/start and project-local runtime/config/cache. The GUI
shows measured audio quality in item details. Cover is external only for Deezer.

Additional concrete fixes: HTTPS Deezer login, no shared-ARL scraping, no ARL as
account display name, secret redaction in public config exports, queue-model pause
compatibility, and frontend type errors in settings/diagnostics/update controls.

## Validation

- Python 3.12.16, uv-locked installation: successful.
- 18 new offline Deezer tests: passing, including actual FFmpeg-generated
  16/44.1, 24/96, 24/192 and 24/384 FLAC; striped encryption across misaligned
  chunks; invalid/lossy source blocking; fresh FLAC retry; cancellation; metadata
  readback; real adapter/finalization; external cover; and recording identity.
- Full backend suite compared in separate processes with an exported, unmodified
  v2.0.3 baseline: baseline 99 tests, 12 failure entries and 13 errors, one skip.
  The initial fork run had the identical failure/error IDs plus 18 passing new
  tests. Secret redaction subsequently fixes two of the existing failures.
- Existing upstream failures concern config coercion/healing, old async event
  tests, Spotify lifecycle, stale API/deployment contracts and version assertions.
  They must be reconciled before claiming a fully green release.
- Production frontend build succeeds. Frontend typecheck is rechecked after
  fixing the seven pre-existing TypeScript errors. See final verification below.
- Ruff passes for the new modules/tests. Eight existing lint findings remain
  in legacy sections of touched source files (broad catches and an old loop).

No authenticated Deezer download was performed in this fork. Configure a personal
account here, then verify actual delivered quality against a known release before
using it for large jobs. Keep this test separate from Streamrip's historical live
24/96 result. Do not describe the generated 24/192 fixture as a live Deezer result.

## Next work

1. Run an authenticated small Deezer album and inspect all artist/ISRC/publisher/
   genre tags and measured source/final resolution.
2. Reconcile the upstream failing test contracts and review the inherited npm
   audit findings before a packaged release.
3. Consider missing-track reports and worklist features as separately specified
   ports; these are not automatically shared with Streamrip or Qobuz-DL GUI.

## Final verification

Backend: 117 tests, 10 failure entries, 13 errors, 1 skip. No new failing test IDs compared with the unmodified baseline; two pre-existing secret-redaction failures fixed.
Startup smoke: compiled React root and asset, profiles, download queue, version and OpenAPI all return HTTP 200 from an isolated local process; that test process was stopped.

Remaining baseline failure/error IDs:

- `test_deployment_contract.DeploymentContractTests.test_image_builds_ui_and_serves_it_from_fastapi`
- `test_main_smoke.ApiSmokeTests.test_core_read_endpoints_respond (route='/library')`
- `test_main_smoke.ApiSmokeTests.test_core_read_endpoints_respond (route='/statistics')`
- `test_main_smoke.ApiSmokeTests.test_openapi_identifies_onthespot`
- `test_otsconfig.ConfigHealingTests.test_alpha2_profile_bitrates_are_healed_to_numbers`
- `test_otsconfig.ConfigHealingTests.test_corrupt_config_file_is_healed_on_load`
- `test_otsconfig.ConfigHealingTests.test_healing_leaves_credentials_alone`
- `test_otsconfig.ConfigPathTests.test_cache_override_is_honoured`
- `test_otsconfig.ConfigPathTests.test_nonexistent_config_override_is_honoured`
- `test_ui_api_contract.UiApiContractTests.test_every_frontend_api_path_exists_in_fastapi`
- `test_main_smoke.ApiSmokeTests.test_spotify_playback_mirror_endpoint_controls_worker`
- `test_otsconfig.ConfigCoercionTests.test_boolean_keys_accept_text_and_real_booleans`
- `test_otsconfig.ConfigCoercionTests.test_keys_outside_the_template_pass_through`
- `test_otsconfig.ConfigCoercionTests.test_list_key_takes_json_text_that_holds_a_list`
- `test_otsconfig.ConfigCoercionTests.test_numeric_text_becomes_a_whole_number`
- `test_otsconfig.ConfigCoercionTests.test_text_key_keeps_a_value_that_reads_as_a_boolean`
- `test_otsconfig.ConfigCoercionTests.test_values_of_the_wrong_type_are_rejected`
- `test_otsconfig.ConfigPathTests.test_config_saves_inside_configured_app_data`
- `test_runtimedata.WebsocketEventTests.test_event_is_broadcast_to_every_subscriber`
- `test_runtimedata.WebsocketEventTests.test_unsubscribe_does_not_drain_other_connections`
- `test_runtimedata.WebsocketEventTests.test_worker_thread_can_publish_safely`
- `test_spotify_connect_lifecycle.SpotifyConnectLifecycleTests.test_http_runner_close_is_idempotent`
- `test_spotify_connect_lifecycle.SpotifyConnectLifecycleTests.test_http_runner_close_stops_thread_and_releases_port`

Frontend typecheck (`npm.cmd run lint`) and production build: successful.
Targeted cache regression: 4 tests pass after fixing request/cache-commit locking.
The startup smoke process was stopped; use start.cmd for the normal local app.
