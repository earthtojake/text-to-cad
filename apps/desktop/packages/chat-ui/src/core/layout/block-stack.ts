// Re-exports from the canonical location in components/rows/markdown/.
// layoutBlockStack and measureBlockCached now live alongside the renderers they
// depend on (BLOCK_REGISTRY, Prose/Code/Table defs).
export {
  layoutBlockStack,
  measureBlockCached,
  type BlockStackOpts,
} from '@components/rows/markdown/block-stack';
