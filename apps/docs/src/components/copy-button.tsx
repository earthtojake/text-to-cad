"use client";

import { Check, Copy, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

type CopyButtonProps = {
  text: string;
  label?: string;
  /** Placement in the box it sits in; every Copy is the same plain icon button. */
  className?: string;
};

type CopyStatus = "idle" | "copied" | "error";

/** Copies `text`: a square icon button, the size of the app buttons beside the install message, that
 * shows a check once copied and a cross if the clipboard refused, its tooltip saying the same. */
export function CopyButton({ text, label = "Copy command", className }: CopyButtonProps) {
  const [status, setStatus] = useState<CopyStatus>("idle");

  useEffect(() => {
    if (status === "idle") {
      return;
    }

    const timeout = window.setTimeout(() => setStatus("idle"), 1600);
    return () => window.clearTimeout(timeout);
  }, [status]);

  const copyText = async () => {
    setStatus("copied");

    try {
      await window.navigator.clipboard.writeText(text);
    } catch {
      setStatus("error");
    }
  };

  const isCopied = status === "copied";
  const isError = status === "error";
  const buttonLabel = isCopied ? "Copied" : isError ? "Copy failed" : label;
  const Icon = isCopied ? Check : isError ? X : Copy;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant={isError ? "destructive" : "secondary"}
          size="icon-lg"
          className={className}
          onClick={copyText}
          aria-label={buttonLabel}
          aria-live="polite"
        >
          <Icon className="size-4" aria-hidden="true" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{isCopied ? "Copied" : isError ? "Copy failed" : "Copy"}</TooltipContent>
    </Tooltip>
  );
}
