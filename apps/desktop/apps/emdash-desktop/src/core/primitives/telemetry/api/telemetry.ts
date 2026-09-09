import type { AgentProviderId } from '@emdash/plugins/agents/types';
import type { SpawnPurpose } from '@emdash/shared/perf';
import type { OpenInAppId } from '@core/primitives/open-in-apps/api/open-in-apps';
import type { TaskLifecycleStatus } from '@core/primitives/tasks/api';
import type { PullRequestMergeStrategy } from '@root/src/core/services/pull-requests/api';

type EmptyProps = Record<string, never>;

/** One `spawns_<purpose>` counter per spawn purpose, derived from SPAWN_PURPOSES. */
type SpawnCountProps = {
  [P in SpawnPurpose as `spawns_${P}`]?: number;
};

export type FocusView = 'home' | 'project' | 'task' | 'settings';
export type FocusMainPanel = 'agents' | 'editor' | 'diff' | 'browser' | 'terminal';
export type FocusedRegion = 'main' | 'bottom';

export type FocusTrigger = 'navigation' | 'panel_switch' | 'region_switch';

export interface TelemetryEnvelope {
  event_ts_ms?: number;
  session_id?: string;
  project_id?: string;
  task_id?: string;
  conversation_id?: string;
}

export interface FocusContext {
  active_view: FocusView | null;
  active_main_panel: FocusMainPanel | null;
  focused_region: FocusedRegion | null;
}

export type SettingName = 'theme' | 'default_provider' | 'telemetry' | 'notifications';

export type TelemetryEventProperties = {
  /** Boot durations attach when known (perf-vitals precedent); a boot that
   * never settles reports `boot_watchdog_triggered` instead. */
  app_started: { window_visible_ms?: number; usable_workspace_ms?: number };
  /** Boot watchdog (~60 s) fired before both boot success signals arrived. */
  boot_watchdog_triggered: {
    stuck_phase: string;
    backend_completed: boolean;
    window_loaded: boolean;
  };
  app_closed: { was_crash?: boolean };
  app_window_focused: EmptyProps;
  app_window_unfocused: EmptyProps;
  daily_active_user: { date: string; timezone: string };

  focus_changed: {
    view: FocusView | null;
    main_panel: FocusMainPanel | null;
    focused_region: FocusedRegion | null;
    trigger: FocusTrigger;
  };

  home_viewed: { from_view: FocusView | null };
  project_viewed: { from_view: FocusView | null };
  task_viewed: { from_view: FocusView | null };
  settings_viewed: { from_view: FocusView | null };

  project_added: { type: 'local' | 'ssh'; strategy: 'open' | 'create' | 'clone'; success: boolean };
  project_deleted: EmptyProps;

  task_created: {
    strategy: 'blank' | 'branch' | 'issue' | 'pr';
    has_initial_prompt: boolean;
    has_issue:
      | 'github'
      | 'linear'
      | 'jira'
      | 'gitlab'
      | 'plane'
      | 'plain'
      | 'forgejo'
      | 'featurebase'
      | 'asana'
      | 'none';
    provider: AgentProviderId | null;
  };
  task_provisioned: EmptyProps;
  /** Wall-clock cost of a full workspace provision, rounded to 100ms. */
  task_provision_timing: { duration_ms: number };
  task_archived: EmptyProps;
  task_status_changed: { from_status: TaskLifecycleStatus; to_status: TaskLifecycleStatus };
  task_deleted: EmptyProps;

  conversation_created: { provider: AgentProviderId; is_first_in_task: boolean };
  conversation_deleted: EmptyProps;
  agent_run_started: { provider: AgentProviderId };

  terminal_created: { terminal_id: string };
  terminal_deleted: { terminal_id: string };

  pr_created: { is_draft: boolean };
  pr_creation_failed: { error_type: string };
  pr_merged: {
    strategy: PullRequestMergeStrategy;
    bypass_requirements: boolean;
    success: boolean;
    error_type?: string;
  };

  vcs_branch_published: { success: boolean; error_type?: string };
  vcs_fetch: { success: boolean; error_type?: string };
  vcs_push: { success: boolean; error_type?: string };
  vcs_pull: { success: boolean; strategy?: string; conflicts?: boolean; error_type?: string };
  vcs_files_staged: { count: number; scope: 'single' | 'multiple' | 'all' };
  vcs_files_unstaged: { count: number; scope: 'single' | 'multiple' | 'all' };
  vcs_files_discarded: { count: number; scope: 'single' | 'multiple' | 'all' };

  user_signed_in: EmptyProps;
  user_signed_out: EmptyProps;

  integration_connected: { provider: 'github' | 'linear' | 'jira' | 'asana' };
  integration_disconnected: { provider: 'github' | 'linear' | 'jira' | 'asana' };
  issue_linked_to_task: {
    provider:
      | 'github'
      | 'linear'
      | 'jira'
      | 'gitlab'
      | 'plane'
      | 'plain'
      | 'forgejo'
      | 'featurebase'
      | 'asana';
  };

  open_in_external: { app: OpenInAppId | 'browser' };
  ssh_connection_attempted: { success: boolean };

  mcp_server_added: { source: 'catalog' | 'custom' };
  mcp_server_removed: EmptyProps;

  skill_installed: { source?: string };
  skill_uninstalled: EmptyProps;
  skill_created: EmptyProps;

  setting_changed: { setting: SettingName };
  sidebar_toggled: { side: 'left' | 'right'; state: 'open' | 'closed' };

  /**
   * Sampled-session performance vitals from the main process and workers.
   * Numbers-only payload; `process_name` is a fixed process identifier
   * (`main` or `worker_<name>`), never a path or command line.
   */
  perf_vitals: {
    process_name: string;
    rss_mb?: number;
    heap_used_mb?: number;
    heap_total_mb?: number;
    detached_contexts?: number;
    cpu_percent?: number;
    elu_percent?: number;
    loop_delay_p95_ms?: number;
    loop_delay_max_ms?: number;
    interval_ms?: number;
    app_process_count?: number;
    app_total_rss_mb?: number;
    renderer_rss_mb?: number;
    gpu_rss_mb?: number;
  } & SpawnCountProps;
  /** Sampled-session renderer responsiveness vitals (long tasks + INP). */
  perf_renderer_vitals: {
    long_tasks: number;
    long_task_total_ms: number;
    inp_ms: number;
    interval_ms: number;
  };

  $exception: {
    $exception_message: string;
    $exception_type: string;
    $exception_stack_trace_raw: string;
    $exception_fingerprint?: string;
    severity?: 'low' | 'medium' | 'high' | 'critical';
    component?: string;
    action?: string;
    user_action?: string;
    operation?: string;
    endpoint?: string;
    session_errors?: number;
    error_timestamp?: string;
    error_type?: string;
  };
  error: { error_type: string; scope: string };
};

export type TelemetryEvent = keyof TelemetryEventProperties;
export type TelemetryProperties<E extends TelemetryEvent> = TelemetryEventProperties[E] &
  TelemetryEnvelope;

export type TelemetryStatus = {
  enabled: boolean;
  envDisabled: boolean;
  userOptOut: boolean;
  hasKeyAndHost: boolean;
  /** True only when telemetry is enabled and this session won the perf-vitals sampling roll. */
  perf_sampled: boolean;
  session_id: string | null;
  instance_id: string | null;
};

/**
 * Core-facing telemetry port. Desktop owns the PostHog-specific implementation
 * and injects it at controller and service composition boundaries.
 */
export interface TelemetryService {
  capture<E extends TelemetryEvent>(
    event: E,
    properties?: TelemetryProperties<E> | Record<string, unknown>
  ): void;
  captureException(error: Error | unknown, additionalProperties?: Record<string, unknown>): void;
  getTelemetryStatus(): TelemetryStatus;
  setTelemetryEnabledViaUser(enabled: boolean): void;
}
