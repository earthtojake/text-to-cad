"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

type CopyButtonProps = {
  text: string;
  label?: string;
  /** The page's main action: the brand colour. Every Copy button is the same size. */
  prominent?: boolean;
};

type CopyStatus = "idle" | "copied" | "error";

export function CopyButton({
  text,
  label = "Copy command",
  prominent = false,
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
      variant={isError ? "destructive" : prominent ? "default" : "secondary"}
      size="lg"
      className="m-2 min-w-20 self-center px-4"
      onClick={copyText}
      aria-label={buttonLabel}
      aria-live="polite"
    >
      {isCopied ? "Copied" : isError ? "Failed" : "Copy"}
    </Button>
  );
}
