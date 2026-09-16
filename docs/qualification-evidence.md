# Signed release evidence and measured first articles

These tools close software integrity/authentication gaps. They do not close the product's physical, supplier, regulatory or production-security qualification gates. The repository contains no trusted reviewer, no physical measurement results and no manufacturing approval. Test keys and values are ephemeral/synthetic test fixtures only.

## Prepare a measured unit record

```sh
python factory/measurements.py template --serial orb-0001 --out factory/private/orb-0001-measurements.json
```

The generated record is `NOT_TESTED`; every value is null. The six checkpoints in `manufacturing/qualification-plan.json` are explicitly **DRAFT** and are not safety standards. Qualify the fixture, test method, instruments, operating conditions, viewing grid, numerical limits and uncertainty budget before marking a controlled plan approved. A single nominal contrast reading is not a viewing-volume privacy assessment.

Enter actual decimal values as strings, a strictly positive expanded uncertainty U, declared coverage factor k, instrument ID and its calibration validity interval, fixture ID/revision, UTC acquisition time, and an in-project relative path plus SHA-256 for the raw acquisition file. Unit conversion is deliberately not implicit. Mark the acquisition `MEASURED` only for real measurements, never to promote synthetic examples.

```sh
python factory/measurements.py evaluate --run factory/private/orb-0001-measurements.json --out factory/private/orb-0001-evaluation.json
```

The evaluator uses decimal arithmetic with bounded magnitudes/exponents. It returns PASS only when `[value-U,value+U]` lies entirely inside the declared specification interval, FAIL when disjoint, and INDETERMINATE for overlap. This is an explicit numerical guard-band decision rule, not a guarantee about a distribution or coverage probability. Any missing/duplicate reading, nonfinite value, zero uncertainty, invalid calibration interval, wrong unit, future/stale acquisition, changed plan/source fingerprint, altered attachment, draft plan or synthetic record blocks the run. Valid numerical results remain `WITHIN_DECLARED_LIMITS_REQUIRES_REVIEW`, not production approval.

## Enroll reviewers outside the source repository

Install the security extra in the controlled quality-station environment:

```sh
python -m pip install './gateway[security]'
python factory/evidence.py keygen --private-key factory/private/reviewer-a.private.pem --public-key factory/private/reviewer-a-public.json
python factory/evidence.py policy-template --out factory/private/reviewer-policy.json
```

Key generation prompts for an encryption passphrase, produces encrypted PKCS8 Ed25519 private material with restrictive POSIX permissions, and refuses replacement. Key files must be excluded from commits and distribution packages. Windows needs equivalent NTFS ACLs. Python memory copies, swap/core dumps and the operator workstation require separate security controls; encrypted files do not solve endpoint compromise. Public keys are not secret but must be authenticated during enrollment.

The policy template has **zero keys** and a two-reviewer threshold per requirement; it cannot approve anything. An authorized release authority must independently verify each reviewer's identity/public key, assign narrow requirement scopes, set UTC key validity dates and revocation state, and approve the policy through the organization's quality process. One enrolled key entry has the following shape:

```json
{
  "key_id": "SHA256_OF_RAW_PUBLIC_KEY",
  "public_key": "BASE64_OF_RAW_32_BYTE_PUBLIC_KEY",
  "reviewer": "Independently verified reviewer identity",
  "requirements": ["optical_readability_privacy"],
  "revoked": false,
  "not_before_utc": "2026-09-16T00:00:00Z",
  "expires_utc": "2026-12-16T00:00:00Z"
}
```

Those strings are placeholders, not an enrolled reviewer. Preserve the reviewed policy's exact-file SHA-256 in an independent trusted release configuration; reading a hash from beside an untrusted replacement policy is not pinning. A policy with no keys, missing requirement thresholds, duplicate key IDs or invalid scope/lifetime is rejected. Quorums count distinct enrolled reviewer identities, not how many keys one person owns.

## Bind and sign a review statement

Freeze the evaluated source checkout and regenerated manufacturing outputs before collecting approvals. Obtain both fingerprints:

```sh
python factory/release_gate.py --fingerprint
python factory/release_gate.py --materials-fingerprint
```

Create one review record per requirement with `requirement`, `status`, `reviewer`, `reviewed_utc`, `valid_until_utc`, `source_fingerprint`, `materials_fingerprint`, and `report` containing relative `path` and file `sha256`. A PASS must reflect the reviewer's actual assessment. Failed or unperformed reviews must not be rewritten as PASS. Include raw acquisition and calibration references in the reviewed report under the quality-system retention policy.

```sh
python factory/evidence.py sign --record factory/private/optics-review.json --private-key factory/private/reviewer-a.private.pem --out factory/private/optics-a.signed.json
python factory/evidence.py sign --record factory/private/optics-a.signed.json --private-key factory/private/reviewer-b.private.pem --out factory/private/optics-ab.signed.json
```

The second command adds a distinct reviewer's signature to the same immutable payload. Each signature is Ed25519 over a domain-separated restricted canonical JSON payload bound to product, revision and release-plan hash. This project encoding is explicitly **not RFC 8785/JCS**: it uses sorted keys, ASCII escapes, no floats, no duplicate keys. Decimal measurements belong in hash-bound attachments or string-valued fields. Do not swap encoding implementations without a versioned migration.

Assemble a JSON array containing exactly one completed signed envelope per requirement. Verify it against the independently pinned policy:

```sh
python factory/release_gate.py --evidence factory/private/release-envelopes.json --trust-policy factory/private/reviewer-policy.json --policy-sha256 INDEPENDENTLY_PINNED_64_HEX_DIGEST --output factory/private/signed-release-status.json
```

Invalid signatures, unauthorized/revoked/expired keys, insufficient quorums, duplicate requirements/signatures, plan/product/revision mismatch, stale source/manufacturing outputs, missing/altered reports or evidence expiry all block the check. Reports cannot be empty, exceed 64 MiB, escape the controlled root, or traverse symbolic links. Design fingerprints include build files, container configuration, factory tools and CI workflows; material fingerprints separately cover CAD, native CAM and generated manufacturing documents.

Without a pinned policy, the checker labels its result unauthenticated. Even `AUTHENTICATED_EVIDENCE_COMPLETE_REQUIRES_AUTHORIZED_SIGNOFF` is not authorization to manufacture: an authorized owner must complete the separate controlled release process. Signatures attest to who signed a statement; they do not make false data true, qualify instruments or confer certification.

References reviewed 2026-09-16: the cryptography Ed25519/PKCS8 serialization documentation, Python decimal documentation, and the project's explicit interval decision rule. No regulatory decision rule is claimed.
