'use client';

/**
 * Toast — imperative notifications built on sonner, restyled onto --em-*
 * tokens.
 *
 * `toast` is a module-level namespace so non-React callers (stores, action
 * handlers) can raise notifications directly; `useToast` wraps the same
 * namespace for component ergonomics. Rendering requires a `Toaster` mounted
 * once per window by the host application.
 */

import type * as React from 'react';
import { Toaster as SonnerToaster, toast as sonnerToast, type ExternalToast } from 'sonner';
import { THEME_MANIFEST, useThemeOptional, type ThemeId } from '../theme-provider';
import * as styles from './toast.css';

export type ToastId = string | number;

/** Tone vocabulary for toasts; the base `toast(...)` call is neutral. */
export type ToastTone = 'neutral' | 'success' | 'error' | 'warning' | 'info';

export interface ToastAction {
  label: React.ReactNode;
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
}

export interface ToastOptions {
  /** Stable id for update-in-place: re-raising with the same id replaces the toast. */
  id?: ToastId;
  description?: React.ReactNode;
  /** Leading icon; tone calls render their built-in status icon when omitted. */
  icon?: React.ReactNode;
  action?: ToastAction;
  /** Milliseconds before auto-dismiss (sonner default: 4000). */
  duration?: number;
}

export interface ToastPromiseMessages<T> {
  loading: React.ReactNode;
  success: React.ReactNode | ((value: T) => React.ReactNode);
  error: React.ReactNode | ((error: unknown) => React.ReactNode);
}

function toExternal(options?: ToastOptions): ExternalToast | undefined {
  if (!options) return undefined;
  const { id, description, icon, action, duration } = options;
  return {
    ...(id !== undefined && { id }),
    ...(description !== undefined && { description }),
    ...(icon !== undefined && { icon }),
    ...(action && { action: { label: action.label, onClick: action.onClick } }),
    ...(duration !== undefined && { duration }),
  };
}

export const toast = Object.assign(
  (title: React.ReactNode, options?: ToastOptions): ToastId =>
    sonnerToast(title, toExternal(options)),
  {
    success: (title: React.ReactNode, options?: ToastOptions): ToastId =>
      sonnerToast.success(title, toExternal(options)),
    error: (title: React.ReactNode, options?: ToastOptions): ToastId =>
      sonnerToast.error(title, toExternal(options)),
    warning: (title: React.ReactNode, options?: ToastOptions): ToastId =>
      sonnerToast.warning(title, toExternal(options)),
    info: (title: React.ReactNode, options?: ToastOptions): ToastId =>
      sonnerToast.info(title, toExternal(options)),
    /**
     * Loading toast that resolves in place: shows `loading` while pending,
     * then swaps to the success or error message.
     */
    promise: <T,>(
      promise: Promise<T>,
      messages: ToastPromiseMessages<T>
    ): { unwrap: () => Promise<T> } => sonnerToast.promise(promise, messages),
    dismiss: (id?: ToastId): void => {
      sonnerToast.dismiss(id);
    },
  }
);

/** Thin hook over the module-level {@link toast} namespace. */
export function useToast(): { toast: typeof toast } {
  return { toast };
}

export interface ToasterProps {
  /**
   * Fallback theme for hosts rendering outside a ThemeProvider. Inside a
   * provider the context theme wins and this prop is ignored.
   */
  theme?: ThemeId;
}

/**
 * Renders the toast stack. Mount once per window, app-owned. Resolves light
 * vs dark from the surrounding ThemeProvider, falling back to the `theme`
 * prop outside one.
 */
export function Toaster({ theme }: ToasterProps) {
  const themeCtx = useThemeOptional();
  const themeId = themeCtx?.themeId ?? theme;
  const polarity = THEME_MANIFEST.find((e) => e.id === themeId)?.polarity ?? 'light';
  return <SonnerToaster theme={polarity} className={styles.toaster} />;
}
