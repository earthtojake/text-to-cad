/** Step 1 of a plugin: say what it adds. Plain data — main, the page and the build all read it. */
export default /** @type {const} */ ({
  id: "csv",
  name: "CSV",
  description: "Shows .csv and .tsv files as a table, and lets the agent read their shape.",
  // The files it opens. An extension belongs to one plugin (or to the base app) only.
  fileTypes: [{ kind: "text", mime: "text/csv", extensions: ["csv", "tsv"] }],
  // Skills it hands to agents: app-owned folders under apps/desktop/skills, or repo skills by name.
  skills: [],
  repoSkills: [],
  // Agent tool name → the command the page answers (renderer.ts).
  commands: { csv_state: "csv-state" },
});
