import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getFilesClient } from '@core/features/files/api/browser/client';
import {
  preserveLastGoodModel,
  restoreLastGoodModel,
  shouldAutoRestoreCadBackup,
  shouldMarkCadRunInterrupted,
} from './cad-last-good';

vi.mock('@core/features/files/api/browser/client', () => ({ getFilesClient: vi.fn() }));

const options = {
  workspacePath: '/work/repo',
  modelPath: 'examples/plate.step',
  sourcePath: 'examples/plate.step.py',
  contextKey: 'cad-model:examples/plate',
  runId: 'run-1',
  recordedAt: '2026-08-24T10:00:00.000Z',
};

describe('preserveLastGoodModel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('allows initial generation when no model exists yet', async () => {
    vi.mocked(getFilesClient).mockResolvedValue({
      fs: {
        exists: vi.fn(async () => ({ success: true, data: { exists: false } })),
      },
    } as never);

    await expect(preserveLastGoodModel(options)).resolves.toBeUndefined();
  });

  it('copies an existing artifact into the hidden recovery directory', async () => {
    const modelBytes = new TextEncoder().encode('accepted-step-at-backup-time');
    const sourceBytes = new TextEncoder().encode('source-at-backup-time');
    const exists = vi.fn(async ({ uri }: { uri: unknown }) => {
      const target = decodeURIComponent(String(uri));
      return {
        success: true,
        data: {
          exists:
            target.endsWith('examples/plate.step') || target.endsWith('examples/plate.step.py'),
        },
      };
    });
    const createDirectory = vi.fn(async () => ({ success: true, data: undefined }));
    const copy = vi.fn(async () => ({ success: true, data: undefined }));
    const readBytes = vi
      .fn()
      .mockResolvedValueOnce({
        success: true,
        data: {
          bytes: async () => modelBytes,
          meta: { mimeType: 'application/step', truncated: false },
        },
      })
      .mockResolvedValueOnce({
        success: true,
        data: {
          bytes: async () => sourceBytes,
          meta: { mimeType: 'text/x-python', truncated: false },
        },
      });
    vi.mocked(getFilesClient).mockResolvedValue({
      fs: { exists, createDirectory, copy, readBytes },
    } as never);

    const snapshot = await preserveLastGoodModel(options);

    expect(createDirectory).toHaveBeenCalledTimes(2);
    expect(copy).toHaveBeenCalledTimes(2);
    expect(snapshot).toMatchObject({
      modelPath: 'examples/plate.step',
      backupPath: '.hardcore/last-good/examples%2Fplate-run-1.step',
      sidecarPath: 'examples/plate.step.json',
      sourcePath: 'examples/plate.step.py',
      sourceBackupPath: '.hardcore/last-good/examples%2Fplate-run-1.source.py',
      validationStatus: 'unknown',
      revisionId: 'sha256:40158d556412844f3f9b3447542cb515743bfd966856a4a9d412bd51b4e8ab30',
      modelHash: '40158d556412844f3f9b3447542cb515743bfd966856a4a9d412bd51b4e8ab30',
      sourceHash: '0e3029b74d363be199f5b4aa2f0dc832bd1b8906aa9873fd1d6ac41314048580',
    });
    expect(snapshot?.sidecarBackupPath).toBeUndefined();
  });

  it('backs up the .step.json sidecar beside the accepted STEP', async () => {
    const exists = vi.fn(async ({ uri }: { uri: unknown }) => {
      const target = decodeURIComponent(String(uri));
      return {
        success: true,
        data: {
          exists:
            target.endsWith('examples/plate.step') || target.endsWith('examples/plate.step.json'),
        },
      };
    });
    const createDirectory = vi.fn(async () => ({ success: true, data: undefined }));
    const copy = vi.fn(async () => ({ success: true, data: undefined }));
    const readBytes = vi.fn(async () => ({
      success: true,
      data: {
        bytes: async () => new TextEncoder().encode('step'),
        meta: { mimeType: 'application/step', truncated: false },
      },
    }));
    vi.mocked(getFilesClient).mockResolvedValue({
      fs: { exists, createDirectory, copy, readBytes },
    } as never);

    const snapshot = await preserveLastGoodModel({ ...options, sourcePath: undefined });

    expect(copy).toHaveBeenCalledTimes(2);
    expect(snapshot).toMatchObject({
      backupPath: '.hardcore/last-good/examples%2Fplate-run-1.step',
      sidecarPath: 'examples/plate.step.json',
      sidecarBackupPath: '.hardcore/last-good/examples%2Fplate-run-1.step.json',
    });
    expect(snapshot?.sourceBackupPath).toBeUndefined();
  });

  it('restores the model and generator from their recovery copies', async () => {
    const readBytes = vi.fn(async () => ({
      success: true,
      data: {
        bytes: async () => new Uint8Array([1, 2, 3]),
        meta: { mimeType: 'application/octet-stream' },
      },
    }));
    const upload = vi.fn(async () => ({ success: true, data: undefined }));
    vi.mocked(getFilesClient).mockResolvedValue({ fs: { readBytes, upload } } as never);

    await restoreLastGoodModel({
      workspacePath: options.workspacePath,
      snapshot: {
        modelPath: options.modelPath,
        backupPath: '.hardcore/last-good/plate-run-1.step',
        sourcePath: options.sourcePath,
        sourceBackupPath: '.hardcore/last-good/plate-run-1.source.py',
        recordedAt: options.recordedAt,
        validationStatus: 'unknown',
      },
    });

    expect(readBytes).toHaveBeenCalledTimes(2);
    expect(upload).toHaveBeenCalledTimes(2);
    expect(upload).toHaveBeenCalledWith(
      expect.objectContaining({ overwrite: true }),
      expect.objectContaining({ name: 'plate.step' })
    );
    expect(upload).toHaveBeenCalledWith(
      expect.objectContaining({ overwrite: true }),
      expect.objectContaining({ name: 'plate.step.py' })
    );
  });

  it('restores the sidecar copy with the STEP, and removes one a failed rebuild left behind', async () => {
    const readBytes = vi.fn(async () => ({
      success: true,
      data: {
        bytes: async () => new Uint8Array([1, 2, 3]),
        meta: { mimeType: 'application/octet-stream' },
      },
    }));
    const upload = vi.fn(async () => ({ success: true, data: undefined }));
    const copy = vi.fn(async () => ({ success: true, data: undefined }));
    const exists = vi.fn(async () => ({ success: true, data: { exists: true } }));
    const remove = vi.fn(async () => ({ success: true, data: undefined }));
    vi.mocked(getFilesClient).mockResolvedValue({
      fs: { readBytes, upload, copy, exists, delete: remove },
    } as never);

    await restoreLastGoodModel({
      workspacePath: options.workspacePath,
      snapshot: {
        modelPath: options.modelPath,
        backupPath: '.hardcore/last-good/plate-run-1.step',
        sidecarPath: 'examples/plate.step.json',
        sidecarBackupPath: '.hardcore/last-good/plate-run-1.step.json',
        recordedAt: options.recordedAt,
        validationStatus: 'unknown',
      },
    });
    expect(copy).toHaveBeenCalledTimes(1);
    expect(remove).not.toHaveBeenCalled();

    await restoreLastGoodModel({
      workspacePath: options.workspacePath,
      snapshot: {
        modelPath: options.modelPath,
        backupPath: '.hardcore/last-good/plate-run-1.step',
        sidecarPath: 'examples/plate.step.json',
        recordedAt: options.recordedAt,
        validationStatus: 'unknown',
      },
    });
    expect(copy).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it('can restore the last valid model without erasing a direct source edit', async () => {
    const readBytes = vi.fn(async () => ({
      success: true,
      data: {
        bytes: async () => new Uint8Array([1, 2, 3]),
        meta: { mimeType: 'application/octet-stream' },
      },
    }));
    const upload = vi.fn(async () => ({ success: true, data: undefined }));
    vi.mocked(getFilesClient).mockResolvedValue({ fs: { readBytes, upload } } as never);

    await restoreLastGoodModel({
      workspacePath: options.workspacePath,
      restoreSource: false,
      snapshot: {
        modelPath: options.modelPath,
        backupPath: '.hardcore/last-good/plate-run-1.step',
        sourcePath: options.sourcePath,
        sourceBackupPath: '.hardcore/last-good/plate-run-1.source.py',
        recordedAt: options.recordedAt,
        validationStatus: 'unknown',
      },
    });

    expect(readBytes).toHaveBeenCalledOnce();
    expect(upload).toHaveBeenCalledOnce();
    expect(upload).toHaveBeenCalledWith(
      expect.objectContaining({ overwrite: true }),
      expect.objectContaining({ name: 'plate.step' })
    );
  });

  it('re-reads a truncated CAD backup at its full reported size before restoring', async () => {
    const fullBytes = new Uint8Array(592_139);
    const readBytes = vi
      .fn()
      .mockResolvedValueOnce({
        success: true,
        data: {
          bytes: async () => new Uint8Array(204_800),
          meta: {
            mimeType: 'application/step',
            truncated: true,
            totalSize: fullBytes.byteLength,
          },
        },
      })
      .mockResolvedValueOnce({
        success: true,
        data: {
          bytes: async () => fullBytes,
          meta: {
            mimeType: 'application/step',
            truncated: false,
            totalSize: fullBytes.byteLength,
          },
        },
      });
    const upload = vi.fn(async () => ({ success: true, data: undefined }));
    vi.mocked(getFilesClient).mockResolvedValue({ fs: { readBytes, upload } } as never);

    await restoreLastGoodModel({
      workspacePath: options.workspacePath,
      restoreSource: false,
      snapshot: {
        modelPath: options.modelPath,
        backupPath: '.hardcore/last-good/plate-run-1.step',
        recordedAt: options.recordedAt,
        validationStatus: 'unknown',
      },
    });

    expect(readBytes).toHaveBeenLastCalledWith(
      expect.objectContaining({ options: { maxBytes: fullBytes.byteLength } })
    );
    expect(upload).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ size: fullBytes.byteLength })
    );
  });
});

describe('shouldAutoRestoreCadBackup', () => {
  it('allows rollback only for the live run that captured the backup', () => {
    expect(shouldAutoRestoreCadBackup('run-live', 'run-live')).toBe(true);
    expect(shouldAutoRestoreCadBackup('run-from-stale-session', null)).toBe(false);
    expect(shouldAutoRestoreCadBackup('run-old', 'run-new')).toBe(false);
  });
});

describe('shouldMarkCadRunInterrupted', () => {
  it('marks a run interrupted only after that run was observed working and becomes idle', () => {
    expect(
      shouldMarkCadRunInterrupted({
        runStatus: 'generating',
        runId: 'run-live',
        observedWorkingRunId: 'run-live',
        isWorking: false,
        lifecycleStatus: 'idle',
        agentStatus: 'idle',
      })
    ).toBe(true);
    expect(
      shouldMarkCadRunInterrupted({
        runStatus: 'generating',
        runId: 'run-live',
        observedWorkingRunId: null,
        isWorking: false,
        lifecycleStatus: 'idle',
        agentStatus: 'idle',
      })
    ).toBe(false);
    expect(
      shouldMarkCadRunInterrupted({
        runStatus: 'generating',
        runId: 'run-live',
        observedWorkingRunId: 'run-live',
        isWorking: true,
        lifecycleStatus: 'working',
        agentStatus: 'working',
      })
    ).toBe(false);
  });
});
