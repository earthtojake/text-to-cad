/** What the PDF plugin adds to the base app. Plain data: main, the renderer and the build read it. */
export default /** @type {const} */ ({
  id: "pdf",
  name: "PDF",
  description: "Page-aware PDF viewing and prompt capture.",
  fileTypes: [{ kind: "pdf", mime: "application/pdf", extensions: ["pdf"] }],
  skills: ["skills/pdf"],
  repoSkills: [],
  commands: { pdf_state: "pdf-state", read_pdf: "pdf-read", set_pdf_page: "pdf-page", capture_pdf: "pdf-capture" },
});
