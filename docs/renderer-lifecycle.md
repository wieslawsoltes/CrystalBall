# Browser rendering and resource ownership

The browser keeps the existing crystal/glass WGSL and artistic design. This change is resource scheduling/input hardening, not a claim of measured hardware FPS or exact physical optics.

A surface is bounded by 1.2 million pixels, 1000 px height, DPR 1.5 and the adapter's texture limit. This prevents ultra-wide or high-DPI windows from allocating unbounded swap/depth surfaces. Dynamic resolution uses submission-completion latency with hysteresis, from quality 1.0 down to 0.5; it is not a GPU timestamp-query measurement. At most one frame is outstanding. Paused scenes and stationary CAD do not submit redundant GPU frames. Scene time excludes pauses and hidden-tab intervals and clamps large scheduler discontinuities.

Renderer initialization, device acquisition, queue completion and CAD upload carry a generation identity. Disposal invalidates that generation, aborts outstanding fetches and removes observers/listeners. A late acquired device is destroyed. Lost-device fallback releases GPU buffers/textures, replaces the formerly WebGPU-bound canvas, and installs input on the replacement. Concurrent CAD requests share one transaction. Bounded streaming reads and full structural validation precede allocation; partial allocation failures destroy every owned resource. Uploaded meshes retain only metadata, GPU buffers and reusable uniforms rather than the large source geometry arrays.

Pointer capture supports orbit and two-touch pinch zoom. Cancellation/lost capture stops the gesture. Wheel units are normalized, keyboard arrows orbit, +/- zoom, and Home resets. These controls apply only to the focused canvas, preserving normal form keyboard behavior. Ctrl/Alt/Meta modified keys are not intercepted. Motion pause state is reflected in the accessible button label.

The engineering viewer renders actual tessellation in opaque/transparent passes. Its simple material shading is not a physically refractive CAD optical solver; transparent meshes are not depth-sorted per triangle. Low-resolution adaptive beauty rendering is a tradeoff, not a substitute for physical-device performance qualification.

Validation includes network-free policy/input/lifetime tests plus an actual Chromium WebGPU fixture for concurrent upload, idle redraw suppression, keyboard control, deliberate device loss and idempotent disposal. The fixture uses shipped modules with the production CSP active. The separate integration suite covers text/audio through a mocked provider, and Pages tests exercise `/CrystalBall/` before public SHA-256 verification.

Browser GPU contract: https://www.w3.org/TR/webgpu/ (reviewed 2026-09-16).
