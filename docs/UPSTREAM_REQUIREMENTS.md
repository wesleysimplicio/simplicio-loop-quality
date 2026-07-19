# Required simplicio-loop capabilities

The extension remains fail-closed until the Loop provides all of these public contracts:

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
