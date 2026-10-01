import { createContext, useContext } from "react";

import {
  ContextMenuItem,
  ContextMenuSeparator,
} from "@renderer/components/ui/context-menu";
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@renderer/components/ui/dropdown-menu";

/**
 * One list of menu items, drawn by whichever of Radix's two menus is asking.
 *
 * A session's actions are reachable two ways — a `…` button and a
 * right-click — and Radix wants its own item component for each menu, which
 * would mean writing the list twice and letting the copies drift. A context
 * picks the component and the list is written once. A submenu's content is
 * still the dropdown's items, so a nested list needs no third case.
 */
export const MenuKind = createContext<"dropdown" | "context">("dropdown");

export function MenuItem({
  icon,
  label,
  onSelect,
  destructive,
}: {
  icon?: React.ReactNode;
  label: string;
  onSelect: () => void;
  destructive?: boolean;
}) {
  const kind = useContext(MenuKind);
  const variant = destructive ? "destructive" : "default";
  return kind === "dropdown" ? (
    <DropdownMenuItem onSelect={onSelect} variant={variant}>
      {icon}
      {label}
    </DropdownMenuItem>
  ) : (
    <ContextMenuItem onSelect={onSelect} variant={variant}>
      {icon}
      {label}
    </ContextMenuItem>
  );
}

export function MenuSeparator() {
  const kind = useContext(MenuKind);
  return kind === "dropdown" ? <DropdownMenuSeparator /> : <ContextMenuSeparator />;
}
