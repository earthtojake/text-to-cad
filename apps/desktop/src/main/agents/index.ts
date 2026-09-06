/**
 * Agent registry, detection, installation and auth. **Filled by P1.**
 *
 * `registry.ts` is a data table of the 35 provider definitions lifted from
 * Emdash: id, name, icon, website, binary names, per-OS install commands, auth
 * methods, the ACP launch command, capabilities, and the hooks that install
 * Hardcore's plugin into that agent. `detect.ts` probes PATH against a
 * login-shell environment resolved once at boot. Nothing here spawns an agent
 * — that is `acp/`.
 */
export {};
