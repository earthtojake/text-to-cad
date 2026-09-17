import { useState } from "react";
import { Copy } from "lucide-react";
import { copyTextToClipboard } from "@/ui/clipboard";
import { Button } from "../ui/button";
import { FileSheetButtonRow, FileSheetStatusText, FileSheetSubsection, FileSheetValueField } from "./FileSheet";

// The locator for one selected component, shown at the FOOT of the Components tab —
// not as a tab of its own. A reference is about the row the user just clicked, so it
// belongs under that row, and a tab that says "select something" the whole time it is
// not being used is a tab that should not exist.
//
// What it carries is what identifies the object to someone who is not looking at the
// screen: the link and the object's own name, and the reference string to paste. The
// visual id and the mesh URL were internal spellings (`base_link:v1`, a
// `/__cad/asset?file=...` URL) that identify nothing outside this process.
function ComponentReference({ component }) {
  const [status, setStatus] = useState("");
  const copy = async () => {
    try {
      await copyTextToClipboard(component.reference);
      setStatus("Reference copied.");
    } catch {
      setStatus("Could not copy the reference. Select and copy the text below.");
    }
  };
  return (
    <FileSheetSubsection title={component.name}>
      <FileSheetValueField label="Link" value={component.linkName} />
      <FileSheetValueField label="Object" value={component.meshObjectId} />
      <FileSheetButtonRow>
        <Button type="button" variant="outline" className="h-7" onClick={copy}>
          <Copy className="size-3.5" aria-hidden="true" /> Copy reference
        </Button>
      </FileSheetButtonRow>
      <FileSheetStatusText className="break-all select-text">{component.reference}</FileSheetStatusText>
      {status ? <div role="status"><FileSheetStatusText>{status}</FileSheetStatusText></div> : null}
    </FileSheetSubsection>
  );
}

export default function RobotComponentReference({ components, selectedIds }) {
  const selected = components.filter((component) => selectedIds.includes(component.id));
  if (!selected.length) return null;
  return selected.map((component) => <ComponentReference key={component.reference} component={component} />);
}
