import { useEffect, useRef, useState } from 'react';
import { Orbit, X } from 'lucide-react';
import { Button } from '@hardcore/ui/primitives/button';
import { Slider } from '@hardcore/ui/primitives/slider';
import { Popover, PopoverAnchor, PopoverTrigger, PopoverContent } from '@hardcore/ui/primitives/popover';
import { cn } from '@hardcore/ui/utils';
import { ViewportAnimationBar, animationControlsHaveContent } from '../playbar/ViewportAnimationBar.js';
import { FileSheetStaticSection, FileSheetSliderField, FILE_SHEET_PRECISION_SLIDER_CLASSES, parseFileSheetNumberInput } from '../../inspector/FileSheet.js';
import { MAX_ORBIT_SPEED, normalizeOrbit } from './orbitPreferences.js';
import { TOOLBAR_ICON_BUTTON_CLASS } from '../ToolbarButton.js';

export const FULLSCREEN_TOOLBAR_IDLE_MS = 2000;

// Visibility is shared by the bottom transport and corner Exit. Clock updates
// never wake them, and pointer activity never rerenders the CAD surface.
function useToolbarVisibility(surface, controls, held) {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const document = controls.current?.ownerDocument;
    if (!document) return;
    const target = surface || document;
    let timer;
    let pointerHeld = false;
    const wake = () => {
      setVisible(true);
      clearTimeout(timer);
      if (!held && !pointerHeld) timer = setTimeout(() => {
        if (!controls.current?.querySelector(':focus-visible')) setVisible(false);
      }, FULLSCREEN_TOOLBAR_IDLE_MS);
    };
    const press = event => {
      pointerHeld = controls.current?.contains(event.target) === true;
      wake();
    };
    const release = () => { pointerHeld = false; wake(); };
    wake();
    target.addEventListener('pointermove', wake, { passive: true });
    target.addEventListener('pointerdown', press, { passive: true });
    target.addEventListener('wheel', wake, { passive: true });
    document.addEventListener('pointerup', release);
    document.addEventListener('pointercancel', release);
    document.addEventListener('keydown', wake);
    document.addEventListener('focusin', wake);
    return () => {
      clearTimeout(timer);
      target.removeEventListener('pointermove', wake);
      target.removeEventListener('pointerdown', press);
      target.removeEventListener('wheel', wake);
      document.removeEventListener('pointerup', release);
      document.removeEventListener('pointercancel', release);
      document.removeEventListener('keydown', wake);
      document.removeEventListener('focusin', wake);
    };
  }, [surface, controls, held]);
  return visible;
}

const buttonClass = cn(TOOLBAR_ICON_BUTTON_CLASS, 'shrink-0');
const stopEscape = event => event.stopPropagation();

/**
 * Fullscreen is the Animate tool with the rest of the viewer put away: when the
 * file has animation, the same playbar, otherwise no tool at all. The corner
 * keeps what is fullscreen's own — orbit speed and Exit.
 */
export default function FullscreenToolbar({ surface, orbitSpeed, onOrbitSpeedChange, animation = null, disabled = false, onExit }) {
  const controls = useRef(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [playbarMenuOpen, setPlaybarMenuOpen] = useState(false);
  const visible = useToolbarVisibility(surface, controls, settingsOpen || playbarMenuOpen);
  const hasAnimation = animationControlsHaveContent(animation);
  const pointerClass = visible ? 'pointer-events-auto' : 'pointer-events-none';

  return <div ref={controls} role="group" aria-label="Fullscreen controls" data-visible={visible}
    aria-hidden={!visible} inert={!visible}
    className={cn('pointer-events-none absolute inset-0 z-40 transition-opacity duration-200 motion-reduce:transition-none', visible ? 'opacity-100' : 'opacity-0')}>
    {hasAnimation && <ViewportAnimationBar runtime={animation} disabled={disabled} className={pointerClass} onMenuOpenChange={setPlaybarMenuOpen}/>}
    <Popover open={settingsOpen} onOpenChange={setSettingsOpen}>
      <PopoverAnchor asChild>
        <div className={cn('absolute right-3 top-3 flex items-center gap-1', pointerClass)}>
          <PopoverTrigger asChild>
            <Button type="button" variant="ghost" size="icon-xs" className={buttonClass}
              aria-label="Orbit settings" aria-pressed={settingsOpen}>
              <Orbit className="size-3" aria-hidden="true"/>
            </Button>
          </PopoverTrigger>
          <Button type="button" variant="ghost" size="icon-xs" className={buttonClass}
            aria-label="Exit fullscreen" title="Exit fullscreen" onClick={onExit}>
            <X className="size-3" aria-hidden="true"/>
          </Button>
        </div>
      </PopoverAnchor>
      <PopoverContent align="end" sideOffset={8} collisionPadding={12} aria-label="Orbit settings" onEscapeKeyDown={stopEscape}
        className="w-72 max-w-[calc(100vw-24px)] max-h-[min(calc(100dvh-24px),var(--radix-popover-content-available-height))] overflow-y-auto p-0 text-tiny [&>section:last-child]:border-b-0">
        <FileSheetStaticSection title="Orbit">
          <FileSheetSliderField compact label="Speed"
            value={`${Number(orbitSpeed.toFixed(2))}×`} onValueCommit={value => onOrbitSpeedChange(normalizeOrbit({
              speed: parseFileSheetNumberInput(value, { fallback: orbitSpeed, min: 0, max: MAX_ORBIT_SPEED }) }).speed)}
            valueInputProps={{ ariaLabel: 'Orbit speed value' }}>
            <Slider thumbProps={{ 'aria-label': 'Orbit speed', 'aria-valuetext': orbitSpeed === 0 ? 'Off' : `${orbitSpeed}×` }} min={0} max={MAX_ORBIT_SPEED} step={0.05} value={[orbitSpeed]}
              onValueChange={([speed]) => onOrbitSpeedChange(speed)} className={FILE_SHEET_PRECISION_SLIDER_CLASSES}/>
          </FileSheetSliderField>
        </FileSheetStaticSection>
      </PopoverContent>
    </Popover>
  </div>;
}
