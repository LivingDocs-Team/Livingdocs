// Hover effect for the clickable "function" boxes: the pointer position feeds a glow that follows it
// (see theme.css). The same class list is used by the CSS, so a new kind of box is added in both places.
import { useEffect } from 'react';

export const SPOTLIGHT_SELECTOR = [
  '.fx',
  '.tile',
  '.repository-item',
  '.documentation-library-item',
  '.documentation-search-result',
  '.suggestion-review-card',
  '.documentation-template',
].join(', ');

export function useSpotlight() {
  useEffect(() => {
    // The boxes live in a zoomed layer: pointer positions are window pixels, the glow is placed in layer pixels.
    const scale = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--ui-scale')) || 1;
    const onMove = (event) => {
      const box = event.target.closest?.(SPOTLIGHT_SELECTOR);
      if (!box) return;
      const rect = box.getBoundingClientRect();
      box.style.setProperty('--mx', `${(event.clientX - rect.left) / scale}px`);
      box.style.setProperty('--my', `${(event.clientY - rect.top) / scale}px`);
    };
    document.addEventListener('pointermove', onMove, { passive: true });
    return () => document.removeEventListener('pointermove', onMove);
  }, []);
}
