# Golden fixtures for the v4 command contract

One folder per action in `engine/reel/contract/protocol.json`. They pin the schemas to what Premiere Pro 26.5.2 and
After Effects 26.5 (WhyNot Cut Bridge 3.1.0) really answered, so a schema that drifts from the hosts fails a test
(`tests/test_contract.py`: the Python validator; `adobe/premiere-uxp/test/contract.test.ts`: ajv, the plugin's own check).

## Files

| file | what it is |
| --- | --- |
| `request.json` | the v4 request (`{protocol, id, action, data, expires_at}`), `id` = the recorded queue job id |
| `result.json` | the v4 result (`{ok, action, id, readback | error, how}`) the engine adapter makes of the recorded answer |
| `cep-data.json` | the raw CEP queue data file the engine wrote (`{...data, action, job_id, submitted}`) |
| `cep-result.json` | the raw queue result file the panel wrote (`{ok, result: "<JSON string>", at}`) |
| `<variant>.request.json` etc. | a second case for the same action (see Variants) |
| `index.json` | per action: `recorded` (true = a real recorded run), `source` (queue job id, anonymised), `host_version` |

`result.json` is not hand-edited: `contract.cep.from_cep(action, <parsed cep-result>, id=request id)` must give exactly
that file, and `contract.cep.to_request(action, data_from_cep(cep-data), ...)` exactly `request.json` (tests check both).
`request.json` / `result.json` also validate with `contract.validate_request` / `validate_result` and with ajv.

## Where each recording comes from

Every recording is the most recent successful pair from a PODCAST-TEST project (the fictional test client), or an older
pair whose paths were rewritten to the PODCAST-TEST layout. The queue folders are `~/.whynot-cut/ppro-queue` (Premiere)
and `~/.whynot-cut/ae-queue` (After Effects); `index.json` names the job id of each.

| action | recorded | variants |
| --- | --- | --- |
| ping | yes (Premiere) | `aftereffects`: After Effects' ping, the form `motion_build.preconditions` reads |
| build_project | yes | `exists`: Premiere answered ok:true with a lone `error` ("project exists"); v4 makes it ok:false |
| export_frames | yes | `error`: a script error (`TypeError`, line 337); v4 ok:false with the line in the sentence |
| close_project_path | yes | `not_open`: `{closed: false, reason: "not open"}` is still ok:true |
| clip_components | yes | |
| ae_build_motion | yes | `failed_scenes`: scenes that failed on a font (ok:false, partial readback); `dirty`: After Effects refused because it holds unsaved changes (**not recorded**, written from `nh_ae_bridge.jsx`) |
| ae_readback | yes | |
| ae_fonts | yes | |
| ae_probe_text | yes | |
| status, probe, open_project, set_player_position, render_review, ae_render | **no** | written from the contract and the code's shapes (`recorded: false` in `index.json`); `render_review`, `set_player_position`, `open_project` and `status` are UXP-only, `ae_render` runs in the engine. Live re-recording is T6.9 |

The `dirty` variant is the golden for the refusal round trip: `{ok:false, reason:"dirty", project, project_path}` becomes
a v4 result with `ok: false` and the refusal in `readback`, because `motion_build.build` decides REFUSED or FAILED from
`readback.reason`.

## Anonymisation

Fixtures sit inside the plugin, where no real client name may appear (`test_no_real_client_name_in_the_product`). The
raw pairs are the recordings with these rewrites and nothing else:

* the engine machine's folder (`...\Editing Plugin\whynot-test\`) is shortened to `D:\whynot-test\`; the Windows user
  folder (`C:\Users\<name>`) becomes `C:\Users\editor`;
* client projects become the PODCAST-TEST layout (`D:\whynot-test\PODCAST-TEST\output\projects\EP02TEST_R02\...`),
  their sequence and clip names `EP02TEST_R02_RE_EDIT` and `EP02TEST.mp4`;
* the Arabic test folder `بودكاست-تجربة` and the Arabic text of the PODCAST-TEST reel stay as recorded.

## Trimming

A list longer than 5 items is cut to its first 5 (the shape is the same, the file smaller); each cut is listed here as
`_trimmed_from: N` (the number of items the recording had). Lists named `vertices`, `inTangents`, `outTangents`, `tokens`,
`shapes`, `elements`, `sfx`, `templates` and `props` are never cut: their items belong together. Request and result of
one pair are cut the same way (`graphics` and `placed` keep the same first five ids).

| files | list | `_trimmed_from` |
| --- | --- | --- |
| build_project/cep-data.json, request.json | `graphics` | 25 |
| build_project/cep-data.json, request.json | `track_names.video` | 9 |
| build_project/cep-data.json, request.json | `track_names.audio` | 8 |
| build_project/cep-result.json, result.json | `readback.placed` | 25 |
| build_project/cep-result.json, result.json | `readback.sharpened` | 8 |
| build_project/cep-result.json, result.json | `readback.renamed` | 9 |
| build_project/cep-result.json, result.json | `readback.tracks.video` | 9 |
| build_project/cep-result.json, result.json | `readback.tracks.audio` | 8 |
| export_frames/cep-data.json, request.json | `times` | 17 |
| export_frames/cep-result.json, result.json | `readback.frames` | 17 |
| export_frames/error.cep-data.json, error.request.json | `times` | 11 |
| ae_build_motion/cep-data.json, request.json (and dirty.request.json) | `job.plan.scenes` | 9 |
| ae_build_motion/cep-result.json, result.json | `readback.made` | 9 |
| ae_build_motion/failed_scenes.cep-data.json, failed_scenes.request.json | `job.plan.scenes` | 9 |
| ae_build_motion/failed_scenes.cep-result.json, failed_scenes.result.json | `readback.failed` | 7 |
| ae_readback/cep-data.json, request.json | `job.plan.scenes` | 9 |
| ae_readback/cep-result.json, result.json | `readback.scenes` | 9 |
| ae_readback/cep-result.json, result.json | `readback.scenes.0.layers` | 9 |
| ae_readback/cep-result.json, result.json | `readback.scenes.1.layers` | 7 |
| ae_readback/cep-result.json, result.json | `readback.scenes.2.layers` | 8 |
| ae_readback/cep-result.json, result.json | `readback.scenes.3.layers` | 10 |
| ae_readback/cep-result.json, result.json | `readback.scenes.4.layers` | 6 |
| ae_probe_text/cep-data.json, request.json | `job.comps` | 9 |
| ae_probe_text/cep-result.json, result.json | `readback.comps` | 9 |
| ae_probe_text/cep-result.json, result.json | `readback.om_templates` | 18 |

The recordings keep their own `at` / `submitted` times and job ids; `expires_at` of a recorded request is its
`submitted` time plus 15 minutes, in UTC.
