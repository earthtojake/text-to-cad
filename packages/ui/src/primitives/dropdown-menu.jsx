"use client";

import * as React from "react";
import { Check, ChevronRight, Minus } from "lucide-react";
import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";

import { cn } from "@cad/ui/utils"
import { ScrollArea } from "@cad/ui/primitives/scroll-area";

// A menu's open state, held here so its trigger can open it at a finger's click (below).
const MenuOpenContext = React.createContext(null);

/** @param {React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Root>} props */
function DropdownMenu({
  open: openProp,
  defaultOpen = false,
  onOpenChange,
  ...props
}) {
  const [own, setOwn] = React.useState(defaultOpen);
  const controlled = openProp !== undefined;
  const open = controlled ? openProp : own;
  const change = React.useCallback(next => { if (!controlled) setOwn(next); onOpenChange?.(next); }, [controlled, onOpenChange]);
  const menu = React.useMemo(() => ({ open, change }), [open, change]);
  return <MenuOpenContext.Provider value={menu}>
    <DropdownMenuPrimitive.Root data-slot="dropdown-menu" open={open} onOpenChange={change} {...props} />
  </MenuOpenContext.Provider>;
}

const DropdownMenuTrigger = React.forwardRef(/**
 * @param {React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Trigger>} props
 * @param {React.ForwardedRef<React.ComponentRef<typeof DropdownMenuPrimitive.Trigger>>} ref
 */ function DropdownMenuTrigger({
  onPointerDown,
  onClick,
  ...props
}, ref) {
  const menu = React.useContext(MenuOpenContext);
  // A finger's press on the trigger, and whether the menu was open as it landed.
  const finger = React.useRef(null);
  // A mouse and a pen open the menu at the press (Radix's own). A finger toggles it at its tap's click, as it opens a
  // popover: a menu opened at a finger's press was shut again by what the rest of the tap sends on a phone (held
  // until no click came, it stayed). The press is marked handled, which is how Radix is told to leave it. The tap
  // toggles what the menu was as the finger landed: an open menu also shuts itself on that tap (a press outside its
  // content), and reading its state at the click would open it again.
  return <DropdownMenuPrimitive.Trigger ref={ref} data-slot="dropdown-menu-trigger" {...props}
    onPointerDown={event => {
      onPointerDown?.(event);
      finger.current = event.pointerType === "touch" ? { open: Boolean(menu?.open) } : null;
      if (finger.current) event.preventDefault();
    }}
    onClick={event => {
      onClick?.(event);
      const press = finger.current;
      finger.current = null;
      if (press && !event.defaultPrevented) menu?.change(!press.open);
    }} />;
});

const DropdownMenuContent = React.forwardRef(/**
 * @param {React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content>} props
 * @param {React.ForwardedRef<React.ComponentRef<typeof DropdownMenuPrimitive.Content>>} ref
 */ function DropdownMenuContent({
  className,
  sideOffset = 4,
  container,
  children,
  ...props
}, ref) {
  const contentRef = React.useRef(null);
  const mergedRef = React.useCallback(node => {
    contentRef.current = node;
    if (typeof ref === "function") ref(node); else if (ref) ref.current = node;
  }, [ref]);
  // A menu taller than the room it has scrolls in the chrome's one scroll region.
  // Focus landing on the menu's own trigger is not focus leaving the menu. A menu opens on its trigger's pointerdown
  // (Radix's), and Safari on iOS gives a tapped button focus only at the tap's click, after the menu has opened: a
  // non-modal menu (`modal={false}`, the navbar's) took that for focus outside and shut at once, where a press held
  // long enough to send no click kept it. A second press on the trigger still shuts it (its own toggle).
  const onFocusOutside = event => {
    props.onFocusOutside?.(event);
    if (event.defaultPrevented) return;
    const target = event.target;
    const id = contentRef.current?.id;
    if (id && target instanceof Element && target.closest("[aria-controls]")?.getAttribute("aria-controls") === id) event.preventDefault();
  };
  return (
    <DropdownMenuPrimitive.Portal container={container}>
      <DropdownMenuPrimitive.Content
        ref={mergedRef}
        data-slot="dropdown-menu-content"
        sideOffset={sideOffset}
        className={cn(
          "z-50 flex max-h-(--radix-dropdown-menu-content-available-height) min-w-[8rem] origin-(--radix-dropdown-menu-content-transform-origin) flex-col overflow-hidden rounded-md border bg-popover p-1 text-xs text-popover-foreground shadow-md data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          className
        )}
        {...props}
        onFocusOutside={onFocusOutside}
      ><ScrollArea className="min-h-0 flex-1">{children}</ScrollArea></DropdownMenuPrimitive.Content>
    </DropdownMenuPrimitive.Portal>
  );
});

/** @param {React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item> & { inset?: boolean, variant?: "default" | "destructive" }} props */
function DropdownMenuItem({
  className,
  inset,
  variant = "default",
  ...props
}) {
  return (
    <DropdownMenuPrimitive.Item
      data-slot="dropdown-menu-item"
      data-inset={inset}
      data-variant={variant}
      className={cn(
        "relative flex cursor-default items-center gap-2 rounded-sm min-h-row px-pad py-1.5 text-xs outline-hidden select-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[inset]:pl-8 data-[variant=destructive]:text-destructive data-[variant=destructive]:focus:bg-destructive/10 data-[variant=destructive]:focus:text-destructive dark:data-[variant=destructive]:focus:bg-destructive/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&_svg:not([class*='text-'])]:text-muted-foreground data-[variant=destructive]:*:[svg]:text-destructive!",
        className
      )}
      {...props}
    />
  );
}

// Checkbox and radio items carry their check on the RIGHT (`docs/design-system.md`, "Menus"): every row's text
// starts on one left edge, whether or not it is checked.
function DropdownMenuCheckboxItem({
  className,
  children,
  checked,
  ...props
}) {
  return (
    <DropdownMenuPrimitive.CheckboxItem
      data-slot="dropdown-menu-checkbox-item"
      className={cn(
        "relative flex cursor-default items-center gap-2 rounded-sm min-h-row py-1.5 pr-8 pl-pad text-xs outline-hidden select-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      checked={checked}
      {...props}
    >
      <span className="pointer-events-none absolute right-2 flex size-3.5 items-center justify-center">
        {/* A box some of whose items are ticked (`checked` "indeterminate") shows a dash, not a tick. */}
        <DropdownMenuPrimitive.ItemIndicator>
          {checked === "indeterminate" ? <Minus className="size-4" /> : <Check className="size-4" />}
        </DropdownMenuPrimitive.ItemIndicator>
      </span>
      {children}
    </DropdownMenuPrimitive.CheckboxItem>
  );
}

function DropdownMenuRadioGroup({
  ...props
}) {
  return <DropdownMenuPrimitive.RadioGroup data-slot="dropdown-menu-radio-group" {...props} />;
}

function DropdownMenuRadioItem({
  className,
  children,
  ...props
}) {
  return (
    <DropdownMenuPrimitive.RadioItem
      data-slot="dropdown-menu-radio-item"
      className={cn(
        "relative flex cursor-default items-center gap-2 rounded-sm min-h-row py-1.5 pr-8 pl-pad text-xs outline-hidden select-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      {...props}
    >
      <span className="pointer-events-none absolute right-2 flex size-3.5 items-center justify-center">
        <DropdownMenuPrimitive.ItemIndicator>
          <Check className="size-4" />
        </DropdownMenuPrimitive.ItemIndicator>
      </span>
      {children}
    </DropdownMenuPrimitive.RadioItem>
  );
}

/** @param {React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Label> & { inset?: boolean }} props */
function DropdownMenuLabel({
  className,
  inset,
  ...props
}) {
  return (
    <DropdownMenuPrimitive.Label
      data-slot="dropdown-menu-label"
      data-inset={inset}
      className={cn("min-h-row px-pad py-1.5 text-xs font-normal data-[inset]:pl-8", className)}
      {...props}
    />
  );
}

/** @param {React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Separator>} props */
function DropdownMenuSeparator({
  className,
  ...props
}) {
  return (
    <DropdownMenuPrimitive.Separator
      data-slot="dropdown-menu-separator"
      className={cn("-mx-1 my-1 h-px bg-border", className)}
      {...props}
    />
  );
}

function DropdownMenuShortcut({
  className,
  ...props
}) {
  return (
    <span
      data-slot="dropdown-menu-shortcut"
      className={cn("ml-auto text-tiny tracking-widest text-muted-foreground", className)}
      {...props}
    />
  );
}

function DropdownMenuSub({
  ...props
}) {
  return <DropdownMenuPrimitive.Sub data-slot="dropdown-menu-sub" {...props} />;
}

/** @param {React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.SubTrigger> & { inset?: boolean }} props */
function DropdownMenuSubTrigger({
  className,
  inset,
  children,
  ...props
}) {
  return (
    <DropdownMenuPrimitive.SubTrigger
      data-slot="dropdown-menu-sub-trigger"
      data-inset={inset}
      className={cn(
        "flex cursor-default items-center gap-2 rounded-sm min-h-row px-pad py-1.5 text-xs outline-hidden select-none focus:bg-accent focus:text-accent-foreground data-[inset]:pl-8 data-[state=open]:bg-accent data-[state=open]:text-accent-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&_svg:not([class*='text-'])]:text-muted-foreground",
        className
      )}
      {...props}
    >
      {children}
      <ChevronRight className="ml-auto size-4" />
    </DropdownMenuPrimitive.SubTrigger>
  );
}

// Portaled like the menu itself: rendered inside its parent menu, a submenu is positioned
// against — and clipped by — that menu whenever it is a containing block (a translucent,
// backdrop-blurred menu is one), which drew it off its trigger and out of sight.
/** @param {React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.SubContent>} props */
function DropdownMenuSubContent({
  className,
  ...props
}) {
  return (
    <DropdownMenuPrimitive.Portal>
    <DropdownMenuPrimitive.SubContent
      data-slot="dropdown-menu-sub-content"
      className={cn(
        "z-50 min-w-[8rem] origin-(--radix-dropdown-menu-content-transform-origin) overflow-hidden rounded-md border bg-popover p-1 text-xs text-popover-foreground shadow-lg data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
        className
      )}
      {...props}
    />
    </DropdownMenuPrimitive.Portal>
  );
}

// A submenu in place, for a menu with no room beside it for one (a phone's: `docs/design-system.md`, "Menus"): its
// row, pressed (or Right), shows its items under it, in the menu itself and indented, its chevron
// turning down while they show; pressed again (or Left) it hides them, and the menu's next opening starts
// it hidden (its items go with the menu). The same three parts as a submenu's, and its items are a
// submenu's own: radio and checkbox items, a label, a separator. Hidden or shown is its own unless the
// caller holds it (`open`, `onOpenChange`: a choice that hides it again).
const InlineSubContext = React.createContext({ open: false, setOpen: () => {} });

function DropdownMenuInlineSub({ open: held, onOpenChange, children }) {
  const [own, setOwn] = React.useState(false);
  const open = held ?? own;
  const setOpen = React.useCallback(next => { if (held === undefined) setOwn(next); onOpenChange?.(next); }, [held, onOpenChange]);
  const value = React.useMemo(() => ({ open, setOpen }), [open, setOpen]);
  return <InlineSubContext.Provider value={value}>{children}</InlineSubContext.Provider>;
}

/** @param {React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item> & { inset?: boolean }} props */
function DropdownMenuInlineSubTrigger({
  className,
  inset,
  children,
  onKeyDown,
  onSelect,
  ...props
}) {
  const { open, setOpen } = React.useContext(InlineSubContext);
  return (
    <DropdownMenuPrimitive.Item
      data-slot="dropdown-menu-inline-sub-trigger"
      data-inset={inset}
      data-state={open ? "open" : "closed"}
      aria-expanded={open}
      onSelect={event => { onSelect?.(event); event.preventDefault(); setOpen(!open); }}
      onKeyDown={event => {
        onKeyDown?.(event);
        const next = { ArrowRight: true, ArrowLeft: false }[event.key];
        if (event.defaultPrevented || next === undefined || next === open) return;
        event.preventDefault();
        setOpen(next);
      }}
      className={cn(
        "flex cursor-default items-center gap-2 rounded-sm min-h-row px-pad py-1.5 text-xs outline-hidden select-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[inset]:pl-8 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&_svg:not([class*='text-'])]:text-muted-foreground",
        className
      )}
      {...props}
    >
      {children}
      <ChevronRight className={cn("ml-auto size-4 transition-transform", open && "rotate-90")} aria-hidden="true" />
    </DropdownMenuPrimitive.Item>
  );
}

/** @param {React.ComponentPropsWithoutRef<"div">} props */
function DropdownMenuInlineSubContent({
  className,
  ...props
}) {
  const { open } = React.useContext(InlineSubContext);
  if (!open) return null;
  return (
    <div
      role="group"
      data-slot="dropdown-menu-inline-sub-content"
      className={cn("[&_[role^=menuitem]]:pl-5 [&_[data-slot=dropdown-menu-label]]:pl-5", className)}
      {...props}
    />
  );
}

export {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuInlineSub,
  DropdownMenuInlineSubContent,
  DropdownMenuInlineSubTrigger,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
};
