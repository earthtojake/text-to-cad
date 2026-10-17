import assert from "node:assert/strict";
import test from "node:test";
import { ISSUE_URL_MAX, TEXT_TO_CAD_LINKS } from "../../../file-viewer/navigation/links.js";
import { alertIssueUrl } from "./reportIssue.js";

const ISSUES = TEXT_TO_CAD_LINKS.issues;
const read = (url) => new URL(url).searchParams;

test("Report Issue opens as \"Issue: \", labelled bug, saying what the card says: its title and failure, the file by name, the version and platform, then Details", () => {
  const alert = { title: "Couldn’t load the model", message: "“/work/parts/gear.step” could not be loaded.",
    reason: "EOFError\nwhile reading the mesh", details: "File: /work/parts/gear.step\nOperation: loading geometry\nEOFError" };
  const url = alertIssueUrl(ISSUES, alert, { file: "/work/parts/gear.step", version: "0.7.5", platform: "darwin" });
  assert.ok(url.startsWith(`${ISSUES}?`));
  const query = read(url);
  assert.deepEqual([...query.keys()], ["title", "labels", "body"]);
  // Only begun, for the person to finish: the card's own title is the first line of the quote.
  assert.equal(query.get("title"), "Issue: ");
  assert.equal(query.get("labels"), "bug");
  assert.equal(query.get("body"), [
    "**What were you doing?**", "", "", "",
    "**Error**", "", "> **Couldn’t load the model**", "> “gear.step” could not be loaded.", "> EOFError", "",
    "**Environment**", "", "- File: gear.step", "- CAD: 0.7.5", "- Platform: darwin", "",
    "**Details**", "", "```", "File: gear.step", "Operation: loading geometry", "EOFError", "```"
  ].join("\n"));
  // Whatever it holds travels intact: nothing in it ends or splits the address.
  const tricky = alertIssueUrl(ISSUES, { title: "A & B #1?", reason: "50% + naïve “quotes” 🙂", details: "a ``` b" }, {});
  assert.doesNotMatch(tricky.slice(ISSUES.length), /[\s#]/u);
  assert.ok(read(tricky).get("body").includes("> **A & B #1?**\n> 50% + naïve “quotes” 🙂\n"));
  assert.ok(read(tricky).get("body").endsWith("````\na ``` b\n````"), "a fence the log cannot close");
});

test("a long diagnostic is cut from its end to keep the address under the cap; the title, the label and the rest of the issue stay whole", () => {
  const details = `File: parts/gear.step\n${Array.from({ length: 4000 }, (_, line) => `step ${line}: “surface” failed`).join("\n")}`;
  const url = alertIssueUrl(ISSUES, { title: "Couldn’t prepare the model", details }, { file: "gear.step", version: "0.7.5" });
  assert.ok(url.length <= ISSUE_URL_MAX, `${url.length} characters`);
  assert.ok(url.length > ISSUE_URL_MAX - 200, "and as much of it as fits");
  assert.ok(url.startsWith(`${ISSUES}?title=Issue%3A+&labels=bug&body=`));
  const body = read(url).get("body");
  assert.match(body, /^\*\*What were you doing\?\*\*[\s\S]*- File: gear\.step\n- CAD: 0\.7\.5\n\n\*\*Details\*\*\n\n```\nFile: parts\/gear\.step\nstep 0: /u);
  assert.ok(body.endsWith("\n… (truncated)\n```"));
  // Characters that encode long, and pairs that must not be split, fit the same way.
  const emoji = alertIssueUrl(ISSUES, { title: "T", details: "🙂".repeat(5000) });
  assert.ok(emoji.length <= ISSUE_URL_MAX);
  assert.ok(!read(emoji).get("body").includes("�"), "never cut between a surrogate pair's halves");
  // A message too long even without its diagnostic cuts the body itself.
  const huge = alertIssueUrl(ISSUES, { title: "T", message: "m".repeat(20000), details: "d" });
  assert.ok(huge.length <= ISSUE_URL_MAX);
  assert.equal(read(huge).get("labels"), "bug");
  assert.match(read(huge).get("body"), /^\*\*What were you doing\?\*\*[\s\S]*m\n… \(truncated\)$/u);
});

test("no path of this machine goes into the issue: the file's is written as its name, a home directory as ~/", () => {
  const path = "/Users/jakefitzgerald/robots/text-to-cad/tmp/quick-edit-test/plate.step";
  // What a card says of a file the viewer's catalog lists by its absolute path: in its message and
  // failure, in Details as the file and as the request for it, and in what the failure itself names.
  const alert = { title: "Couldn’t prepare the model", message: `“${path}” could not be prepared for display.`,
    reason: `${path}: Part derivation failed for 03ff06ae62ca3a91`,
    details: [`File: ${path}`, "Operation: preparing display assets",
      `Request: POST http://127.0.0.1:4178/__cad/artifact?${new URLSearchParams({ file: path })}`,
      `${path}: Part derivation failed for 03ff06ae62ca3a91`,
      "  File \"/Users/jakefitzgerald/.venv/lib/python3.12/site-packages/cadgen/build.py\", line 9, in build",
      "  C:\\Users\\Ada Lovelace\\Desktop\\drawing.dxf, /home/ada/parts.step"].join("\n") };
  const query = read(alertIssueUrl(ISSUES, alert, { file: path, version: "0.7.5", platform: "darwin" }));
  assert.equal(query.get("title"), "Issue: ");
  assert.equal(query.get("body"), [
    "**What were you doing?**", "", "", "",
    "**Error**", "", "> **Couldn’t prepare the model**", "> “plate.step” could not be prepared for display.",
    "> plate.step: Part derivation failed for 03ff06ae62ca3a91", "",
    "**Environment**", "", "- File: plate.step", "- CAD: 0.7.5", "- Platform: darwin", "",
    "**Details**", "", "```", "File: plate.step", "Operation: preparing display assets",
    "Request: POST http://127.0.0.1:4178/__cad/artifact?file=plate.step",
    "plate.step: Part derivation failed for 03ff06ae62ca3a91",
    "  File \"~/.venv/lib/python3.12/site-packages/cadgen/build.py\", line 9, in build",
    "  ~/Desktop\\drawing.dxf, ~/parts.step", "```"
  ].join("\n"));
  // However it is written: with either slash, spaces and a drive and all, or encoded in a request's URL.
  const drive = "C:/Users/Jane Doe/models/my part.step";
  const written = [drive, "C:\\Users\\Jane Doe\\models\\my part.step", new URLSearchParams({ file: drive }).toString(), `file=${encodeURIComponent(drive)}`];
  const body = read(alertIssueUrl(ISSUES, { title: "T", details: written.join("\n") }, { file: drive })).get("body");
  assert.ok(body.endsWith("```\nmy part.step\nmy part.step\nfile=my part.step\nfile=my part.step\n```"), body);
});

test("a host with no tracker gets no address", () => {
  assert.equal(alertIssueUrl("", { title: "Broken" }), "");
  assert.equal(alertIssueUrl(undefined, { title: "Broken" }), "");
});
