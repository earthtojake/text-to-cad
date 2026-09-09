const skillSvgs = import.meta.glob<string>('../../../../assets/images/skills/*.svg', {
  query: '?raw',
  import: 'default',
  eager: true,
});
const mcpSvgs = import.meta.glob<string>('../../../../assets/images/mcp/*.svg', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const svgByName: Record<string, string> = {};
for (const [path, raw] of [...Object.entries(skillSvgs), ...Object.entries(mcpSvgs)]) {
  svgByName[path.split('/').pop()!.replace('.svg', '')] = raw;
}

const skillToIcon: Record<string, string> = {
  // OpenAI curated skills
  'cloudflare-deploy': 'cloudflare',
  figma: 'figma',
  'figma-implement-design': 'figma',
  'gh-address-comments': 'github',
  'gh-fix-ci': 'github',
  'jupyter-notebook': 'jupyter',
  linear: 'linear',
  'netlify-deploy': 'netlify',
  'notion-knowledge-capture': 'notion',
  'notion-meeting-intelligence': 'notion',
  'notion-research-documentation': 'notion',
  'notion-spec-to-implementation': 'notion',
  playwright: 'playwright',
  'render-deploy': 'render',
  sentry: 'sentry',
  'vercel-deploy': 'vercel',
  yeet: 'github',

  // OpenAI generic skills
  'openai-docs': 'openai',
  sora: 'openai',
  imagegen: 'openai',
  'skill-creator': 'openai',
  'skill-installer': 'openai',

  // Commonly installed skills
  cloudflare: 'cloudflare',
  'durable-objects': 'cloudflare',
  wrangler: 'cloudflare',
  'ai-sdk': 'vercel',
  'vercel-react-best-practices': 'vercel',
  'find-docs': 'context7',
  'gh-issue-fix-flow': 'github',
  shadcn: 'shadcn',
  mysql: 'mysql',
  postgres: 'postgresql',
  'react-doctor': 'react',
  'react-email': 'react',
  resend: 'resend',
  'resend-design-skills': 'resend',
  'resend-brand': 'resend',
  elysiajs: 'bun',
  'frontend-design': 'anthropic',
  'webapp-testing': 'anthropic',
  'web-artifacts-builder': 'anthropic',
  'find-skills': 'anthropic',
  'review-and-refactor': 'anthropic',
  'web-design-guidelines': 'anthropic',
  'mcp-builder': 'anthropic',
  'algorithmic-art': 'anthropic',
  'canvas-design': 'anthropic',
  'theme-factory': 'anthropic',
  'brand-guidelines': 'anthropic',
  'doc-coauthoring': 'anthropic',
  'internal-comms': 'anthropic',
  stripe: 'stripe',
  slack: 'slack',
  notion: 'notion',
  netlify: 'netlify',
};

const keywordRules: Array<{ test: (id: string) => boolean; icon: string }> = [
  { test: (id) => /^swiftui[-_]/.test(id) || id === 'swift-concurrency-expert', icon: 'swift' },
  { test: (id) => /\b(ios|xcode)\b/.test(id) || id.startsWith('ios-'), icon: 'xcode' },
  {
    test: (id) => /\b(macos|app-store|appstore)\b/.test(id) || id.startsWith('macos-'),
    icon: 'apple',
  },
  { test: (id) => id.startsWith('gh-') || id.includes('github'), icon: 'github' },
  { test: (id) => id.includes('cloudflare') || id.includes('worker'), icon: 'cloudflare' },
  {
    test: (id) => id.includes('vercel') || id.includes('nextjs') || id.includes('next-js'),
    icon: 'vercel',
  },
  { test: (id) => id.startsWith('react-') || id.startsWith('react:'), icon: 'react' },
  { test: (id) => id.includes('notion'), icon: 'notion' },
  { test: (id) => id.includes('figma'), icon: 'figma' },
  { test: (id) => id.includes('sentry'), icon: 'sentry' },
  { test: (id) => id.includes('linear'), icon: 'linear' },
  { test: (id) => id.includes('stripe'), icon: 'stripe' },
  { test: (id) => id.includes('resend'), icon: 'resend' },
  { test: (id) => id.includes('postgres') || id.includes('postgresql'), icon: 'postgresql' },
  { test: (id) => id.includes('mysql'), icon: 'mysql' },
  { test: (id) => id.includes('playwright'), icon: 'playwright' },
];

const sourceIcons: Record<string, string> = {
  openai: 'openai',
  anthropic: 'anthropic',
};

export function resolveSkillIcon(skillId: string, source: string): string | undefined {
  const name =
    skillToIcon[skillId] ?? keywordRules.find((r) => r.test(skillId))?.icon ?? sourceIcons[source];
  return name ? svgByName[name] : undefined;
}
