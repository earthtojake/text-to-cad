import { Textarea, type TextareaProps } from '@emdash/ui/react/primitives';
import React, { forwardRef, useEffect } from 'react';
import { cn } from '@core/primitives/styling/browser/cn';

export function useTextareaAutoFocus(
  ref: React.RefObject<HTMLTextAreaElement | null>,
  active: boolean
) {
  useEffect(() => {
    if (!active) return;

    const focusTextarea = () => {
      const textarea = ref.current;
      if (!textarea) return;
      textarea.focus();
      textarea.select();
    };

    let raf2: number | null = null;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => {
        focusTextarea();
      });
    });
    const timer = setTimeout(() => {
      focusTextarea();
    }, 80);

    return () => {
      cancelAnimationFrame(raf1);
      if (raf2 !== null) cancelAnimationFrame(raf2);
      clearTimeout(timer);
    };
  }, [active, ref]);
}

const CommentRoot = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex h-[140px] w-full flex-col rounded-lg border border-border bg-background text-foreground shadow-sm',
        className
      )}
      {...props}
    />
  )
);
CommentRoot.displayName = 'CommentRoot';

const CommentHeader = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex flex-row items-center justify-between space-y-0 px-6 py-4 pb-3',
        className
      )}
      {...props}
    />
  )
);
CommentHeader.displayName = 'CommentHeader';

const CommentTitle = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('text-sm font-semibold leading-none', className)} {...props} />
  )
);
CommentTitle.displayName = 'CommentTitle';

const CommentMeta = forwardRef<HTMLSpanElement, React.HTMLAttributes<HTMLSpanElement>>(
  ({ className, ...props }, ref) => (
    <span
      ref={ref}
      className={cn('text-xs font-normal text-foreground-muted', className)}
      {...props}
    />
  )
);
CommentMeta.displayName = 'CommentMeta';

const CommentActions = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex items-center gap-1.5', className)} {...props} />
  )
);
CommentActions.displayName = 'CommentActions';

const CommentBody = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex-1 overflow-hidden px-6 pb-5 pt-0', className)} {...props} />
  )
);
CommentBody.displayName = 'CommentBody';

const CommentTextarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => (
    <Textarea
      ref={ref}
      className={cn(
        'h-full resize-none border-border bg-background px-4 py-3 text-sm shadow-none focus-visible:ring-0 focus-visible:border-border focus-visible:outline-none',
        className
      )}
      {...props}
    />
  )
);
CommentTextarea.displayName = 'CommentTextarea';

export const Comment = {
  Root: CommentRoot,
  Header: CommentHeader,
  Title: CommentTitle,
  Meta: CommentMeta,
  Actions: CommentActions,
  Body: CommentBody,
  Textarea: CommentTextarea,
};
