import type { Block } from '@core/markdown/document';
import type { BlockDef } from './block-def';
import { codeBlockDef } from './code/code.def';
import { mermaidBlockDef } from './mermaid/mermaid.def';
import { proseBlockDef } from './prose/prose.def';
import { ruleBlockDef } from './rule/rule.def';
import { tableBlockDef } from './table/table.def';

// oxlint-disable-next-line typescript/no-explicit-any -- registry boundary
export const BLOCK_REGISTRY: Record<Block['kind'], BlockDef<any, any>> = {
  prose: proseBlockDef,
  code: codeBlockDef,
  table: tableBlockDef,
  rule: ruleBlockDef,
  mermaid: mermaidBlockDef,
};
