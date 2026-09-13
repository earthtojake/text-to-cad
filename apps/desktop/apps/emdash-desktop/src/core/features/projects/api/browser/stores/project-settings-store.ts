import type { ProjectConfigState } from '@emdash/core/runtimes/workspace-registry/api';
import { ok, type Result } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import { observe, pin, remote, type RemoteModel } from '@emdash/wire/state';
import { computed, makeObservable, observable, reaction, runInAction } from 'mobx';
import { Resource } from '@core/primitives/async-resource/browser/resource';
import {
  type MigrateProjectConfigRequest,
  type ProjectConfigMigration,
  type WriteProjectConfigRequest,
} from '@core/primitives/project-settings/api';
import type { HostObservation, ProjectHostObservation } from '../../host-observation';
import {
  projectConfigDomainsFromState,
  type MigrateProjectConfigResult,
  type ProjectDurableSettingsDomains,
  type ProjectHostSettingsSnapshot,
  type ProjectSettingsDomainPatch,
  type ProjectSettingsDomains,
  type ProjectSettingsError,
  type ProjectSettingsPage,
} from '../../project-settings-page';
import { projectsWireContract } from '../../wire-contract';
import { getProjectsWireClient } from '../client';
import type { ProjectHostAccess } from './project-context';

export class ProjectSettingsStore {
  readonly pageData: Resource<ProjectSettingsPage>;
  private readonly _configScope: Scope;
  private readonly _hostStateDisposer: () => void;
  private _projectConfig: ProjectConfigState | null = null;
  private _hostSettings: HostObservation<ProjectHostSettingsSnapshot> = {
    kind: 'never-observed',
  };
  private _projectConfigRemote: RemoteModel<typeof projectsWireContract.projectConfig> | null =
    null;
  private _disposed = false;

  constructor(
    private readonly projectId: string,
    private readonly host: ProjectHostAccess,
    private readonly clock: Clock = systemClock
  ) {
    this._configScope = createScope({ label: `project-settings-config:${projectId}` });
    this.pageData = new Resource(async () => {
      const result = await (await getProjectsWireClient()).getProjectSettingsPage({ projectId });
      if (!result.success) {
        throw new Error(
          result.error.type === 'project-not-found'
            ? `Project ${projectId} not found`
            : 'Failed to load project settings'
        );
      }
      this.applyPage(result.data);
      return result.data;
    }, [{ kind: 'demand' }]);

    makeObservable<this, '_hostSettings' | '_projectConfig'>(this, {
      _hostSettings: observable.ref,
      _projectConfig: observable.ref,
      durableDomains: computed,
      hostDomains: computed,
      domains: computed,
    });
    this._hostStateDisposer = reaction(
      () => this.host.state.kind,
      (kind, previous) => {
        if (kind !== 'ready') return;
        this.bindProjectConfig();
        if (previous !== undefined && previous !== 'ready') void this.load();
      },
      { fireImmediately: true }
    );
  }

  get durableDomains(): ProjectDurableSettingsDomains | null {
    return this.pageData.data?.durable ?? null;
  }

  get hostDomains(): ProjectHostObservation<ProjectHostSettingsSnapshot> {
    return this.host.observe(this._hostSettings);
  }

  get domains(): ProjectSettingsDomains | null {
    const durable = this.durableDomains;
    const host = this.hostDomains;
    if (!durable || host.kind === 'unavailable') return null;
    const domains: ProjectSettingsDomains = {
      ...host.value.domains,
      ...durable,
      placement: {
        ...host.value.domains.placement,
        ...durable.placement,
      },
    };
    if (!this._projectConfig) return domains;
    return {
      ...domains,
      ...projectConfigDomainsFromState(this._projectConfig, domains.lifecycle.writeTargets),
    };
  }

  get configMigrations(): ProjectConfigMigration[] | null {
    const host = this.hostDomains;
    if (!this.durableDomains) return null;
    return host.kind === 'unavailable' ? [] : host.value.configMigrations;
  }

  get shouldPromptConfigMigration(): boolean {
    const host = this.hostDomains;
    return host.kind === 'unavailable' ? false : host.value.shouldPromptConfigMigration;
  }

  async load(): Promise<ProjectSettingsPage | null> {
    await this.pageData.load();
    return this.pageData.data;
  }

  async save(
    patch: ProjectSettingsDomainPatch
  ): Promise<Result<ProjectSettingsPage, ProjectSettingsError>> {
    const result = await (
      await getProjectsWireClient()
    ).updateProjectSettings({
      projectId: this.projectId,
      patch,
    });
    if (!result.success) return result;
    this.applyPage(result.data);
    this.pageData.setValue(result.data);
    return ok(result.data);
  }

  async writeConfigToRepo(
    request: WriteProjectConfigRequest
  ): Promise<Result<ProjectSettingsPage, ProjectSettingsError>> {
    const result = await (
      await getProjectsWireClient()
    ).shareProjectSettingsToConfig({
      projectId: this.projectId,
      request,
    });
    if (result.success) {
      this.applyPage(result.data);
      this.pageData.setValue(result.data);
    }
    return result;
  }

  async migrateProjectConfig(
    request: MigrateProjectConfigRequest
  ): Promise<Result<MigrateProjectConfigResult, ProjectSettingsError>> {
    const result = await (
      await getProjectsWireClient()
    ).migrateProjectConfig({
      projectId: this.projectId,
      request,
    });
    if (result.success) {
      this.applyPage(result.data.page);
      this.pageData.setValue(result.data.page);
    }
    return result;
  }

  dispose(): void {
    this._disposed = true;
    this._hostStateDisposer();
    void this._configScope.dispose();
    void this._projectConfigRemote?.dispose();
    this.pageData.dispose();
  }

  private bindProjectConfig(): void {
    if (this._projectConfigRemote || this._disposed) return;
    void getProjectsWireClient()
      .then((client) => {
        if (this._disposed) return;
        const config = remote(projectsWireContract.projectConfig, client.projectConfig, {
          scope: this._configScope,
        });
        const current = config({ projectId: this.projectId }).states.current;
        pin(this._configScope, [current]);
        observe(
          current,
          (snapshot) => {
            if (snapshot.value === undefined) return;
            runInAction(() => {
              this._projectConfig = snapshot.value ?? null;
              if (snapshot.value && this._hostSettings.kind === 'observed') {
                this._hostSettings = {
                  ...this._hostSettings,
                  observedAt: this.clock.now(),
                  value: {
                    ...this._hostSettings.value,
                    domains: {
                      ...this._hostSettings.value.domains,
                      ...projectConfigDomainsFromState(
                        snapshot.value,
                        this._hostSettings.value.domains.lifecycle.writeTargets
                      ),
                    },
                  },
                };
              }
            });
          },
          { scope: this._configScope, immediate: true }
        );
        this._projectConfigRemote = config;
        if (this._disposed) void config.dispose();
      })
      .catch(() => {});
  }

  private applyPage(page: ProjectSettingsPage): void {
    if (page.host.kind === 'never-observed' && this._hostSettings.kind === 'observed') return;
    runInAction(() => {
      this._hostSettings = page.host;
    });
  }
}
