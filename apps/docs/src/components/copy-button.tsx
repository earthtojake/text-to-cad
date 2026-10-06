"use client";

import { Check, Copy, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

type CopyButtonProps = {
  text: string;
  label?: string;
  /** A square icon button, the size of the app buttons beside it, instead of the word Copy. */
  icon?: boolean;
};

type CopyStatus = "idle" | "copied" | "error";

export function CopyButton({
  text,
  label = "Copy command",
  icon = false,
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

  if (icon) {
    const Icon = isCopied ? Check : isError ? X : Copy;
    return (
      <Button
        type="button"
        variant={isError ? "destructive" : "secondary"}
        size="icon-lg"
        onClick={copyText}
        aria-label={buttonLabel}
        title={buttonLabel}
        aria-live="polite"
      >
        <Icon className="size-4" aria-hidden="true" />
      </Button>
    );
  }

  return (
    <Button
      type="button"
      variant={isError ? "destructive" : "secondary"}
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
