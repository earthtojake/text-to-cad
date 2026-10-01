import { useRef } from "react";

/**
 * Focus back to what had it, for a Radix dialog or sheet with no trigger.
 *
 * Radix hands a closing Dialog's focus to its `Trigger`; one opened by a
 * chord, a menu or a row's own handler has none, and the focus it had fell to
 * the page, where no key reaches anything. Spread onto the content:
 * `onOpenAutoFocus` notes what had focus before the dialog takes it, and
 * `onCloseAutoFocus` gives it back — only while nothing else has taken focus
 * (an action in the dialog that opened another view hands it to that), and
 * only to an element still in the document.
 */
export function useReturnFocus() {
  const opener = useRef<HTMLElement | null>(null);
  return {
    onOpenAutoFocus: () => {
      const active = document.activeElement;
      opener.current = active instanceof HTMLElement && active !== document.body ? active : null;
    },
    onCloseAutoFocus: (event: Event) => {
      event.preventDefault();
      const previous = opener.current;
      opener.current = null;
      const free = !document.activeElement || document.activeElement === document.body;
      if (free && previous?.isConnected) previous.focus();
    },
  };
}
