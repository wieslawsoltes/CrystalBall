# Byte-identical Rev A baseline import

These seven consecutive binary pieces constitute an XZ-compressed tar of the supplied engineering source files, cached PCB routes, original reports, SHA-256 manifest, and STEP presentation records. This is a file-transfer container, not encrypted content. Combined archive SHA-256: `1949999319f49bb6eb79f5541bd68453d9aae72ab17f88fe3aad5c4ecf256c3f`.

`ci/import_reva.py` extracts only regular in-repository paths, runs the supplied deterministic PCB/schematic/CAD generators, restores the original STEP timestamp and presentation ordering, and verifies all 63 original files against their SHA-256 hashes. The workflow refuses to commit on any mismatch. Local reconstruction of the STEP was checked byte-for-byte: SHA-256 `f9fd1863567ffd259ce29d91b40138dd55b617014c063486c2b0213de5262db6`.

Reconstruction is only transport normalization. The original Rev A design and original validation limitations are unchanged; this is not a new production release. Subsequent engineering changes belong in separate commits.
