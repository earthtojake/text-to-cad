import type React from 'react';
import type { BrowserWebviewElement } from './browser-webview-types';

declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      webview: React.DetailedHTMLProps<
        React.HTMLAttributes<BrowserWebviewElement>,
        BrowserWebviewElement
      > & {
        src?: string;
        partition?: string;
        allowpopups?: boolean;
      };
    }
  }
}
