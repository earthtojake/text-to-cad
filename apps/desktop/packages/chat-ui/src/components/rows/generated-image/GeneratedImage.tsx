import { useCommands } from '@components/contexts/CommandsContext';
import { ImageOffIcon } from '@components/primitives/icons';
import { For, Match, Switch, createResource } from 'solid-js';
import type { ChatGeneratedImage, ChatImageAttachment } from '@/model';
import {
  generatedImage,
  generatedImageButton,
  generatedImageGrid,
  generatedImagePlaceholder,
  generatedImagePlaceholderIcon,
} from './generated-image.css';

export function GeneratedImage(props: { item: ChatGeneratedImage }) {
  return (
    <div class={generatedImageGrid} role="group" aria-label="Generated images">
      <For each={props.item.attachments}>
        {(attachment) => <ResolvedGeneratedImage attachment={attachment} item={props.item} />}
      </For>
    </div>
  );
}

function ResolvedGeneratedImage(props: {
  attachment: ChatImageAttachment;
  item: ChatGeneratedImage;
}) {
  const commands = useCommands();
  const [resolvedDataUrl] = createResource(
    () => (props.attachment.dataUrl ? null : props.attachment.id),
    async () => commands().resolveAttachment?.(props.attachment) ?? null
  );
  const dataUrl = () => props.attachment.dataUrl ?? resolvedDataUrl() ?? undefined;

  return (
    <Switch>
      <Match when={dataUrl()}>
        {(src) => (
          <button
            type="button"
            class={generatedImageButton}
            aria-label={`View generated image: ${props.attachment.name}`}
            onClick={(event) => {
              event.stopPropagation();
              commands().onViewImage?.({
                attachment: { ...props.attachment, dataUrl: src() },
                itemId: props.item.sourceItemId,
                source: props.item.source,
              });
            }}
          >
            <img
              src={src()}
              alt={`Generated image: ${props.attachment.name}`}
              class={generatedImage}
            />
          </button>
        )}
      </Match>
      <Match when={resolvedDataUrl.loading}>
        <div class={generatedImagePlaceholder} role="status" aria-live="polite">
          <span class={generatedImagePlaceholderIcon} aria-hidden="true">
            <ImageOffIcon />
          </span>
          <span>Loading image…</span>
        </div>
      </Match>
      <Match when>
        <div class={generatedImagePlaceholder} role="status" title={props.attachment.name}>
          <span class={generatedImagePlaceholderIcon} aria-hidden="true">
            <ImageOffIcon />
          </span>
          <span>Image unavailable</span>
        </div>
      </Match>
    </Switch>
  );
}
