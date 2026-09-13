import { Button } from '@emdash/ui/react/primitives';
import * as React from 'react';
import { cn } from '@core/primitives/styling/browser/cn';

export const SidebarContainer = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('group/sidebar relative z-50 flex flex-col text-sm text-foreground', className)}
    {...props}
  />
));
SidebarContainer.displayName = 'SidebarContainer';

export const SidebarHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex flex-col gap-1 border-b-0', className)} {...props} />
  )
);
SidebarHeader.displayName = 'SidebarHeader';

export const SidebarContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex flex-1 flex-col overflow-hidden text-sm text-foreground-muted', className)}
    {...props}
  />
));
SidebarContent.displayName = 'SidebarContent';

export const SidebarGroup = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('mb-6 grid', className)} {...props} />
  )
);
SidebarGroup.displayName = 'SidebarGroup';

export const SidebarGroupContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn('grid gap-1', className)} {...props} />
));
SidebarGroupContent.displayName = 'SidebarGroupContent';

export const SidebarFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('mt-auto flex flex-col border-t px-3 py-3', className)}
      {...props}
    />
  )
);
SidebarFooter.displayName = 'SidebarFooter';

export const SidebarMenu = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn('', className)} {...props} />
);
SidebarMenu.displayName = 'SidebarMenu';

export const SidebarItemMiniButton = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement>
>(({ className, onMouseDown, onPointerDown, ...props }, ref) => (
  <Button
    ref={ref}
    variant="ghost"
    size="xs"
    icon
    className={className}
    onMouseDown={(event) => {
      event.preventDefault();
      onMouseDown?.(event);
    }}
    onPointerDown={(event) => {
      event.stopPropagation();
      onPointerDown?.(event);
    }}
    {...props}
  />
));
SidebarItemMiniButton.displayName = 'SidebarItemMiniButton';

const sidebarMenuItemClass =
  'flex h-8 w-full items-center gap-2 rounded-lg px-2 py-1 text-sm font-normal text-foreground-muted transition-[background-color,color] duration-100 hover:bg-(--em-surface-hover) hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 data-[active=true]:bg-(--em-surface-selected) data-[active=true]:text-foreground';

interface SidebarMenuButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isActive?: boolean;
}
export const SidebarMenuButton = React.forwardRef<HTMLButtonElement, SidebarMenuButtonProps>(
  ({ className, isActive, ...props }, ref) => (
    <button
      ref={ref}
      data-slot="button"
      data-active={isActive || undefined}
      className={cn(sidebarMenuItemClass, className)}
      onMouseDown={(e) => e.preventDefault()}
      {...props}
    />
  )
);

// Sidebar row labels use this as the named voice-control target. Primary
// activation is handled by the parent row's click handler via bubbling.
export const SidebarMenuAction = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement>
>(({ className, ...props }, ref) => (
  <button
    ref={ref}
    type="button"
    className={cn(
      'flex min-w-0 flex-1 items-center self-stretch rounded-md text-left text-inherit outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      className
    )}
    onMouseDown={(e) => e.preventDefault()}
    {...props}
  />
));
SidebarMenuAction.displayName = 'SidebarMenuAction';

interface SidebarMenuRowProps extends React.HTMLAttributes<HTMLDivElement> {
  isActive?: boolean;
}
export const SidebarMenuRow = React.forwardRef<HTMLDivElement, SidebarMenuRowProps>(
  ({ className, isActive, ...props }, ref) => (
    <div
      ref={ref}
      data-active={isActive || undefined}
      className={cn(sidebarMenuItemClass, className)}
      {...props}
    />
  )
);
