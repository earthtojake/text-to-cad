import { describe, expect, it } from 'vitest';
import { parseFrontmatter } from './validation';

describe('parseFrontmatter', () => {
  it('parses single-line quoted values', () => {
    const { frontmatter } = parseFrontmatter(`---
name: "review"
description: "Review code changes"
---

# Review
`);

    expect(frontmatter).toEqual({
      name: 'review',
      description: 'Review code changes',
      license: undefined,
      compatibility: undefined,
      'allowed-tools': undefined,
    });
  });

  it('parses literal block descriptions without exposing the YAML marker', () => {
    const { frontmatter } = parseFrontmatter(`---
name: docs
description: |
  Edit documentation.
  Keep the prose direct.
---

# Docs
`);

    expect(frontmatter.description).toBe('Edit documentation.\nKeep the prose direct.');
  });

  it('parses folded block descriptions as display-friendly text', () => {
    const { frontmatter } = parseFrontmatter(`---
name: docs
description: >
  Edit documentation.
  Keep the prose direct.
---

# Docs
`);

    expect(frontmatter.description).toBe('Edit documentation. Keep the prose direct.');
  });

  it('continues parsing fields after a block scalar', () => {
    const { frontmatter } = parseFrontmatter(`---
name: docs
description: |-
  Edit documentation.
license: MIT
---

# Docs
`);

    expect(frontmatter.description).toBe('Edit documentation.');
    expect(frontmatter.license).toBe('MIT');
  });
});
