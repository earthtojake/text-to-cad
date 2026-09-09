/**
 * fonts.ts — re-exports FontConfig, VariantMetrics, and DEFAULT_FONT_CONFIG
 * for backward compatibility.
 *
 * The canonical definitions now live in core/config.ts (alongside ChatConfig
 * and buildChatTheme) to avoid circular imports. Import from @core/config
 * directly when adding new code; these re-exports preserve existing importers.
 */

export type { FontConfig, VariantMetrics } from '@core/config';
import { DEFAULT_CONFIG, toFontConfig } from '@core/config';

/** Pre-built FontConfig from DEFAULT_CONFIG. Used by table/layout.ts. */
export const DEFAULT_FONT_CONFIG = toFontConfig(DEFAULT_CONFIG);
