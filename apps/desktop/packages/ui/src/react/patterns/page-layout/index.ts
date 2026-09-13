import { PageHeader } from './page-header';
import { PageLayoutRoot, Sidebar, Content } from './page-layout';
import { PageSidebarMenu } from './page-sidebar-menu';

// ── Public namespace ──────────────────────────────────────────────────────────

/**
 * PageLayout — composable page-shell pattern for sidebar+content and
 * content-only views.
 *
 * Two-column (Library / Settings style):
 * ```tsx
 * <PageLayout sidebar={<PageLayout.SidebarMenu items={...} activeId={id} onSelect={...} />}>
 *   <PageLayout.Content maxWidth="3xl">
 *     <PageLayout.Header title="Prompts" description="..." sticky actions={<SearchInput />} />
 *     …
 *   </PageLayout.Content>
 * </PageLayout>
 * ```
 *
 * Single-column (Automations style):
 * ```tsx
 * <PageLayout>
 *   <PageLayout.Content>
 *     <PageLayout.Header title="Automations" description="..." actions={…} />
 *     …
 *   </PageLayout.Content>
 * </PageLayout>
 * ```
 */
export const PageLayout = Object.assign(PageLayoutRoot, {
  /** Bare sticky sidebar slot — use for fully custom sidebar content. */
  Sidebar,
  /** Sticky nav-item sidebar — generalizes the Library / Settings sidebar. */
  SidebarMenu: PageSidebarMenu,
  /** Centered content column with configurable max-width. */
  Content,
  /** Page-section header: title + description + actions + separator. */
  Header: PageHeader,
});

// ── Re-export types ───────────────────────────────────────────────────────────

export type { PageLayoutProps, PageSidebarProps, PageContentProps } from './page-layout';
export type {
  PageNavItem,
  PageNavDivider,
  PageNavSection,
  PageSidebarMenuItem,
  PageSidebarMenuProps,
} from './page-sidebar-menu';
export type { PageHeaderProps } from './page-header';
