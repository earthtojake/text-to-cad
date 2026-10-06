// How builds and jobs read: JSON for REST (and MCP's structured content), and short text
// for an agent. Text tells the agent what happened and what to do next, nothing more.
import type { Build, Job, Service } from './service.ts';
import { isTerminal, viewsOf } from './service.ts';

export function buildTitle(build: Build): string {
  if (build.title) return build.title;
  const from = build.primary ?? build.entry[0] ?? build.id;
  return from.split('/').pop()!.replace(/\.[^.]+$/, '');
}

/** Every file of the build the viewer opens, the primary first. */
export function buildViews(service: Service, build: Build): string[] {
  return viewsOf(service.buildFiles(build).map((file) => file.path), build.primary);
}

export function buildJson(service: Service, build: Build, extra: Record<string, unknown> = {}) {
  return {
    id: build.id,
    status: build.status,
    title: buildTitle(build),
    link: build.status === 'succeeded' || build.primary ? service.buildLink(build) : `${service.config.publicUrl}/b/${build.id}`,
    primary: build.primary,
    outputs: build.outputs.map((file) => file.path),
    views: build.status === 'succeeded' ? buildViews(service, build).map((path) => ({ path, link: service.buildLink(build, path) })) : [],
    entry: build.entry,
    pythonpath: build.pythonpath,
    base: build.parentId,
    error: build.error,
    progress: isTerminal(build.status) ? null : build.progress,
    log: build.log,
    thumbnail: build.thumbnailKey ? service.objectUrl(build.thumbnailKey) : null,
    view: { available: !!build.exportKey, error: build.exportError },
    flags: { network: !!build.flags?.network, dropped: build.flags?.dropped ?? [] },
    cadgen: build.cadgen,
    limits: build.limits,
    cost: build.cost,
    createdAt: build.createdAt,
    startedAt: build.startedAt,
    finishedAt: build.finishedAt,
    ...extra,
  };
}

export function jobJson(service: Service, job: Job) {
  return {
    id: job.id,
    kind: job.kind,
    build: job.buildId,
    status: job.status,
    request: job.kind === 'inspect' ? { code: job.request.code } : job.request,
    error: job.error,
    progress: isTerminal(job.status) ? null : job.progress,
    exitCode: job.result?.exitCode ?? null,
    stdout: job.result?.stdout ?? '',
    stderr: job.result?.stderr ?? '',
    log: job.result?.log ?? '',
    images: (job.result?.images ?? []).map((image) => ({ url: image.url, type: image.type, path: image.path })),
    flags: { network: !!job.flags?.network },
    cost: job.cost,
    createdAt: job.createdAt,
    finishedAt: job.finishedAt,
    link: `${service.config.publicUrl}/b/${job.buildId}`,
  };
}

const tail = (text: string, lines: number) => {
  const all = text.trimEnd().split('\n');
  return all.slice(-lines).join('\n');
};

function where(error: { file?: string | null; line?: number | null }) {
  if (!error.file) return '';
  return error.line ? ` (${error.file}:${error.line})` : ` (${error.file})`;
}

function progressLine(progress: Build['progress']): string {
  if (!progress) return '';
  const parts = [progress.phase, progress.progress ? `${progress.progress[0]}/${progress.progress[1]}` : null, progress.elapsed ? `${Math.round(progress.elapsed)} s` : null]
    .filter(Boolean);
  return parts.length ? ` (${parts.join(', ')})` : '';
}

export function buildText(service: Service, build: Build, { deduped = false } = {}): string {
  const lines: string[] = [];
  const title = buildTitle(build);
  if (build.status === 'succeeded') {
    lines.push(`Build ${build.id} (${title}) succeeded${deduped ? ' (an identical build already existed)' : ''}.`);
    lines.push(`Link: ${service.buildLink(build)}`);
    const others = buildViews(service, build).slice(1);
    if (others.length) {
      const shown = others.slice(0, 8).map((path) => service.buildLink(build, path));
      lines.push(`Also in the viewer: ${shown.join(', ')}${others.length > 8 ? ` and ${others.length - 8} more` : ''}`);
    }
    if (build.outputs.length) lines.push(`Outputs: ${build.outputs.map((file) => file.path).join(', ')}`);
    if (!build.entry.length) lines.push('No entry script: the files were published as sent.');
    if (!build.primary) {
      lines.push('The build has no viewable CAD file: a model writes its outputs with a decorator, e.g. @step(out="../STEP/part.step").');
    } else if (!build.exportKey) {
      lines.push(`The link cannot show the model yet: ${build.exportError ?? 'no viewer export was recorded'}.`);
    }
  } else if (build.status === 'failed') {
    const error = build.error ?? { message: 'unknown error', kind: 'model' };
    lines.push(`Build ${build.id} failed${deduped ? ' (an identical build already failed)' : ''}: ${error.message}${where(error)}`);
    if (build.log.trim()) lines.push('', 'Log (tail):', tail(build.log, 25));
    if (error.kind === 'model') lines.push('', `Fix the source and call cad_build again with base="${build.id}" and only the changed files.`);
    else if (error.kind === 'timeout') lines.push('', 'Make the model cheaper (fewer features, coarser detail) and build again.');
  } else {
    lines.push(`Build ${build.id} is ${build.status}${progressLine(build.progress)}.`);
    lines.push(`Call cad_status with id="${build.id}" to wait for the result.`);
  }
  if (build.flags?.network) lines.push('Note: this build\'s code tried to use the network, which sandboxes do not have.');
  if (build.flags?.dropped?.length) lines.push(`Dropped (not CAD outputs): ${build.flags.dropped.slice(0, 10).join(', ')}`);
  return lines.join('\n');
}

export function jobText(service: Service, job: Job): string {
  const lines: string[] = [];
  const name = job.kind === 'snapshot' ? 'Snapshot' : 'Inspection';
  if (job.status === 'succeeded' || job.status === 'failed') {
    if (job.status === 'succeeded') lines.push(`${name} ${job.id} of build ${job.buildId} finished.`);
    else lines.push(`${name} ${job.id} of build ${job.buildId} failed: ${job.error?.message ?? 'unknown error'}${job.error ? where(job.error) : ''}`);
    if (job.kind === 'inspect' && job.result) {
      lines.push(`Exit code: ${job.result.exitCode ?? 'none'}`);
      if (job.result.stdout.trim()) lines.push('', 'stdout:', tail(job.result.stdout, 60));
      if (job.result.stderr.trim()) lines.push('', 'stderr:', tail(job.result.stderr, 30));
    }
    for (const image of job.result?.images ?? []) lines.push(`Image: ${image.url}`);
    if (job.flags?.network) lines.push('Note: this code tried to use the network, which sandboxes do not have.');
  } else {
    lines.push(`${name} ${job.id} is ${job.status}${progressLine(job.progress)}. Call cad_status with id="${job.id}" to wait for it.`);
  }
  void service;
  return lines.join('\n');
}
