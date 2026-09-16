# Live voice: durable lifecycle and cancellation

## Persistence and the ambiguous-create boundary

Live voice remains opt-in and requires a writable durable journal. Set `REALTIME_DATABASE=/var/lib/orb/voice.sqlite`. For existing environments without that variable, the gateway uses `BUDGET_DATABASE + '.realtime'`. Preserve the same file and mounted volume across upgrades. Do not change paths to make a cleanup warning disappear.

Before a provider POST, the supervisor commits a `RESERVED` record. After receiving a valid OpenAI call-resource Location header, it commits `ACTIVE` with the provider ID before reading the SDP response. Metadata only is stored: local handle, unit ID, provider ID, timestamps, state and cleanup status. SDP, audio, transcripts and credentials are not journaled. SQLite uses WAL and `synchronous=FULL`; the actual filesystem/storage must honor sync operations. A kernel-owned process lock rejects a second worker and releases on process exit.

After restart, every known unfinished call is sent to provider hangup before new voice admission. An interrupted reservation without a provider ID becomes `UNKNOWN`, never a retry of create. A server cannot atomically commit a local database and a remote API transaction: a crash between provider creation and receipt/persistence of its ID is fundamentally ambiguous without a provider-supported reconciliation contract. We do not assume undocumented idempotency or call-list APIs. Those records stay blocked until an operator investigates provider-side termination and records an explicit reconciliation.

Hangup attempts are serialized per call. Only HTTP 200/204 confirms cleanup. In particular, 404/410 are not automatically treated as proof of termination. Failed known cleanup stays on disk, blocks new voice admission and is retried by the running supervisor every five seconds with three bounded attempts per sweep. A storage fault latches admission closed. Text and push-to-talk do not depend on voice readiness. Authenticated capabilities include counts and reason flags, not provider call IDs.

A monotonic timer bounds the intended running voice interval; provider/network outages can prevent remote hangup. Neither this timer nor persistent request admission is an exact spending cap. Pending unresolved records are never age-deleted; closed/reconciled operational records older than seven days are pruned at startup.

## Offline operator workflow

Stop the gateway; the CLI deliberately takes the same exclusive worker lock. In the activated gateway Python environment:

```sh
PYTHONPATH=gateway python -m app.voice_admin --database /path/to/voice.sqlite inspect
```

Investigate the listed provider sessions externally. Save a nonempty report of the investigation. Reconcile one known local handle only after provider termination has been confirmed:

```sh
PYTHONPATH=gateway python -m app.voice_admin --database /path/to/voice.sqlite reconcile \
  --handle LOCAL_HANDLE_FROM_INSPECTION \
  --reviewer 'Named operator' \
  --report /path/to/termination-review.txt \
  --confirmed-provider-closed
```

The journal retains the reviewer, timestamp and report SHA-256, not its contents. This command records an operator attestation, not an independent provider observation or cryptographically authenticated release review. Keep the report under the organization's audit policy. Restart the gateway against the SAME journal. Do not delete SQLite/WAL/SHM/lock files as a recovery procedure.

## Browser cancellation ownership

Each `LiveVoice` attempt owns its media tracks, peer connection, data channel, text buffer, timer and a gateway-credential snapshot. Every awaited boundary checks that the attempt is still current. Late microphone permission, SDP response, remote-description completion and data-channel callbacks cannot reactivate an erased session. A late successful create is terminated using the original gateway credentials, even after the UI is paired elsewhere.

Local cancellation closes capture immediately. The bounded setup request may finish solely to acquire a cleanup handle; it cannot send user audio after tracks are closed. A page/process crash falls back to the durable server lifecycle. The client is still not a financial or optical-privacy security boundary.

## Verification scope

Fault-injection tests exercise persistent reservations, known/unknown restart paths, failed SDP download, malformed provider IDs, worker exclusion, disk failure, concurrent hangup/admission and missing provider confirmation. JavaScript lifecycle tests control each async boundary and assert no stale text or media restoration. Provider traffic is mocked. Actual OpenAI WebRTC connectivity, network failure behavior, Safari/iPhone media policy and physical hardware remain acceptance gates.

## Primary implementation references (accessed 2026-09-16)

- OpenAI Realtime create-call contract: https://developers.openai.com/api/reference/resources/realtime/subresources/calls/methods/create
- OpenAI Realtime hangup: https://developers.openai.com/api/reference/resources/realtime/subresources/calls/methods/hangup
- SQLite synchronous/WAL durability semantics: https://www.sqlite.org/pragma.html#pragma_synchronous
