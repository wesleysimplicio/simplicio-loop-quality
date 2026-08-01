# Required simplicio-loop capabilities

The extension remains fail-closed until the Loop provides all of these public contracts. The
provider is discovered only through the `simplicio.loop_extension` package entry point. Its
doctor evaluates the committed N-1/N/current fixtures and accepts only versions listed in
`supported_versions`, using the native handshake from the exact Loop runtime. Metadata/module
version divergence, unknown future versions, missing stage-agent bindings, Hub IPC,
ProcessSpec/Result, ledger, invalidation, run-outcome, runtime fingerprint, stage composition or
exclusive Oracle authority block before any task file or command is created. Strict mode never
falls back to a local runner.

1. Completion Oracle is the only path to `phase=done`.
2. A required quality-provider hook runs after implementation and before watcher/delivery/oracle.
3. External stage graphs/role overlays compose without copying the canonical graph.
4. Stage agents submit every command through Hub IPC and `ProcessSpec`.
5. Independent stages in a wave may run concurrently only within Hub-provided slots.
6. Any source mutation invalidates quality, watcher, delivery and completion receipts.
7. `run` exposes a versioned terminal outcome and returns success only for Oracle-authorized
   completion.
8. The Hub owns hermetic service/environment provisioning and cleanup for quality agents.
9. A versioned handshake proves the exact inspected and executed runtime plus provider capability.

Temporary adapters must not create a parallel scheduler or claim completion authority.
