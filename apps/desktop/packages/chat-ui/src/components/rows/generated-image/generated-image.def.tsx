import type { MeasureCtx } from '@core/define';
import { defineUnit } from '@core/units';
import { pxTokens } from '@styles/px-tokens';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import type { ChatGeneratedImage } from '@/model';
import {
  generatedImageGridMetrics,
  type GeneratedImageGridOptions,
} from './generated-image-layout';
import { GeneratedImage } from './GeneratedImage';
import { generatedImageVars, type GeneratedImageStyleVars } from './generated-image.css';

type GeneratedImageVars = GeneratedImageStyleVars & GeneratedImageGridOptions;

function metrics(item: ChatGeneratedImage, ctx: MeasureCtx, vars: GeneratedImageVars) {
  return generatedImageGridMetrics(item.attachments.length, ctx.width, vars);
}

export const generatedImageUnitDef = defineUnit<ChatGeneratedImage, GeneratedImageVars>({
  kind: 'generated-image',
  margin: { top: 4, bottom: 8 },
  vars: {
    gap: 8,
    tileSize: 280,
    maxTileSize: 280,
    minTwoColumnWidth: 360,
  },

  estimate(item, ctx, vars): number {
    return metrics(item, ctx, vars).height;
  },

  measure(item, ctx, vars): number {
    return metrics(item, ctx, vars).height;
  },

  Render(props) {
    const layout = () => {
      const ctx = props.ctx.measureCtx?.();
      return ctx
        ? metrics(props.data, ctx, props.vars)
        : {
            columns: 1,
            rows: 1,
            tileSize: props.vars.maxTileSize,
            height: props.vars.maxTileSize,
          };
    };
    return (
      <div
        style={{
          ...assignInlineVars(
            generatedImageVars,
            pxTokens({
              gap: props.vars.gap,
              tileSize: layout().tileSize,
            })
          ),
          width: '100%',
          height: `${layout().height}px`,
        }}
      >
        <GeneratedImage item={props.data} />
      </div>
    );
  },
});
