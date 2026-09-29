"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

type CopyButtonProps = {
  text: string;
  label?: string;
  compact?: boolean;
};

type CopyStatus = "idle" | "copied" | "error";

export function CopyButton({
  text,
  label = "Copy command",
  compact = false,
}: CopyButtonProps) {
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

  return (
    <Button
      type="button"
      variant={isError ? "destructive" : "secondary"}
      size="sm"
      className={`m-2 min-w-[4.25rem] self-center ${compact ? "px-2.5" : "px-3"}`}
      onClick={copyText}
      aria-label={buttonLabel}
      aria-live="polite"
    >
      {isCopied ? "Copied" : isError ? "Failed" : "Copy"}
    </Button>
  );
}
