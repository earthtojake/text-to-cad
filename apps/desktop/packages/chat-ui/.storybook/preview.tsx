import type { Preview } from 'storybook-solidjs-vite';
import { DebugContext } from '../src/components/contexts/debug-context';
import { storyDecorator } from '../src/styles/storybook.css';
import '../src/chat-fonts.css';
import '../src/styles/global.css';
import './preview.css';

const preview: Preview = {
  parameters: {
    layout: 'centered',
  },
  decorators: [
    (Story, context) => {
      // storybook-solidjs makes `context.globals` a reactive Solid store and does
      // NOT remount the story when a toolbar global changes — it reconciles the
      // store in place. So globals must be read lazily inside the reactive tree
      // (accessors / JSX), never snapshotted here, or theme/debug won't update.
      const globals = context.globals as Record<string, string>;
      const theme = () => globals['theme'] ?? 'emlight';
      const debugOn = () => globals['debug'] === 'on';
      return (
        <DebugContext.Provider value={debugOn}>
          <div class={`${theme()} ${storyDecorator}`}>
            <Story />
          </div>
        </DebugContext.Provider>
      ) as unknown as ReturnType<typeof Story>;
    },
  ],
  globalTypes: {
    theme: {
      description: 'Color theme',
      defaultValue: 'emlight',
      toolbar: {
        title: 'Theme',
        icon: 'circlehollow',
        items: [
          { value: 'emlight', title: 'Light' },
          { value: 'emdark', title: 'Dark' },
        ],
        dynamicTitle: true,
      },
    },
    debug: {
      description: 'Layout boundary debug overlay',
      defaultValue: 'off',
      toolbar: {
        title: 'Debug',
        icon: 'ruler',
        items: [
          { value: 'off', title: 'Debug off' },
          { value: 'on', title: 'Debug on' },
        ],
        dynamicTitle: true,
      },
    },
  },
};

export default preview;
