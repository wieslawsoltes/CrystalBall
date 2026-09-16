# Verification provenance

These are executed software/CAD checks, not physical qualification or production authorization.

| Evidence | Tested revision | Run |
|---|---|---|
| Byte-identical 63-file Rev A import | f430900c5269cbada520c0550a1a0a9df75eb3ed | 35095459001 |
| Rev B nominal geometry and native ECAD closure | ee7636b41c1c5ce633bbcd893e3255e46b586d81 | 35102824577 |
| WebGPU/browser: 12 checks, no reported browser errors | be296449f793c9a6d6da068ecc2f755bf9f3d23c | 35122015818 |
| KiCad 9.0.9, native CAM, 3 firmware profiles, units, Docker boot | e75e8cbf9ed599b46090f04b0eb5d466797816f7 | 35122549355 |

Run 35122549355 passed all six jobs: unit tests, KiCad, container and firmware default/public-voice/calibration. Run 35122015818 uses the actual production CSP and a software WebGPU adapter. OpenAI text, STT and TTS are mocked; no live API key was used. Hardware FPS, physical optics, Safari/iPhone behavior and production security are not established.

Earlier browser verification incorrectly allowed a failed process behind `tee` to leave a green job. The pipeline was corrected to use explicit Bash/pipefail, required report/screenshot outputs, and report generation on failure. Do not use run 35119366382 as browser-pass evidence. Later failures led to software-adapter selection and a bounded one-frame GPU submission queue; these checks now pass.

An earlier KiCad job unexpectedly ran KiCad 7 despite a PPA installation. The current job uses `kicad/kicad:9.0.9`, verifies the version and fails rather than silently relaxing CLI or DRC requirements.

`archived/2026-09-16-native/` contains outputs downloaded from run 35122549355. `preview/validated/` contains screenshots and the report from run 35122015818. Each keeps its own tested commit. Do not treat archived reports as evidence for changed design sources without review.

The handoff workflow re-runs Python/JavaScript tests when generating documentation. Source fingerprints and SHA-256 manifests bind the generated files and release records to their inputs. Blank first-article records are deliberately NOT TESTED.
