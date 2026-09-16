import { useState } from "react";
import { Copy } from "lucide-react";
import { copyTextToClipboard } from "@/ui/clipboard";
import { Button } from "../ui/button";
import { FileSheetButtonRow, FileSheetStatusText, FileSheetSubsection, FileSheetValueField } from "./FileSheet";

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
      <FileSheetValueField label="Visual" value={component.visualId} />
      <FileSheetValueField label="Mesh" value={component.mesh} />
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

export default function RobotComponentReferenceSection({ components, selectedIds }) {
  const selected = components.filter((component) => selectedIds.includes(component.id));
  if (!selected.length) return <FileSheetStatusText>Select a component in the list or viewport to inspect its reference.</FileSheetStatusText>;
  return selected.map((component) => <ComponentReference key={component.reference} component={component} />);
}
