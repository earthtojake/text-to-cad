import { useEffect, useRef, useState } from 'react';
import type { Chord } from '@core/primitives/keybindings/api';
import { chordFromCaptureEvent } from '@core/primitives/keybindings/browser';

export interface UseChordRecorderOptions {
  readonly onRecord: (chord: Chord) => void;
  readonly onCancel?: () => void;
}

export function useChordRecorder({ onRecord, onCancel }: UseChordRecorderOptions) {
  const [isRecording, setIsRecording] = useState(false);
  const onRecordRef = useRef(onRecord);
  const onCancelRef = useRef(onCancel);
  onRecordRef.current = onRecord;
  onCancelRef.current = onCancel;

  const cancelRecording = () => {
    setIsRecording(false);
    onCancelRef.current?.();
  };

  useEffect(() => {
    if (!isRecording) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      event.stopPropagation();
      if (event.key === 'Escape') {
        cancelRecording();
        return;
      }
      const captured = chordFromCaptureEvent(event);
      if (!captured) return;
      setIsRecording(false);
      onRecordRef.current(captured);
    };
    window.addEventListener('keydown', handleKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
  }, [isRecording]);

  return {
    isRecording,
    startRecording: () => setIsRecording(true),
    cancelRecording,
  };
}
