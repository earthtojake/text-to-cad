import { describe, expect, it } from 'vitest';
import { hostDependencyDefinitionSchema } from '#primitives/host-dependencies/api';
import {
  CORE_DEPENDENCIES,
  GIT_DEPENDENCY_DESCRIPTOR,
  RECOMMENDED_CORE_DEPENDENCIES,
  REQUIRED_CORE_DEPENDENCIES,
} from './core-dependencies';

describe('CORE_DEPENDENCIES', () => {
  it('keeps every core dependency in exactly one classification set', () => {
    const requiredIds = new Set(REQUIRED_CORE_DEPENDENCIES.map((dependency) => dependency.id));
    const recommendedIds = new Set(
      RECOMMENDED_CORE_DEPENDENCIES.map((dependency) => dependency.id)
    );

    for (const dependency of REQUIRED_CORE_DEPENDENCIES) {
      expect(recommendedIds.has(dependency.id)).toBe(false);
    }
    for (const dependency of RECOMMENDED_CORE_DEPENDENCIES) {
      expect(requiredIds.has(dependency.id)).toBe(false);
    }
    expect(new Set(CORE_DEPENDENCIES.map((dependency) => dependency.id))).toEqual(
      new Set([...requiredIds, ...recommendedIds])
    );
  });

  it('defines valid host dependency descriptors for all system dependencies', () => {
    expect(() =>
      CORE_DEPENDENCIES.map((dependency) => hostDependencyDefinitionSchema.parse(dependency))
    ).not.toThrow();
  });

  it('marks linux apt install options as always elevated with sudo-free commands', () => {
    for (const dependency of CORE_DEPENDENCIES) {
      const linuxOptions = dependency.installCommands?.linux ?? [];
      for (const option of linuxOptions) {
        if (option.method !== 'apt') continue;
        expect(option.elevation).toBe('always');
        expect(option.command).toMatch(
          /^DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=60 update && DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=60 install -y /
        );
        expect(option.packages).not.toHaveLength(0);
        expect(option.command).not.toContain('sudo');
      }
    }
  });

  it('keeps the git apt command sudo-free', () => {
    expect(GIT_DEPENDENCY_DESCRIPTOR.installCommands?.linux).toEqual([
      {
        method: 'apt',
        command:
          'DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=60 update && DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=60 install -y git',
        packages: ['git'],
        recommended: true,
        elevation: 'always',
      },
    ]);
  });
});
