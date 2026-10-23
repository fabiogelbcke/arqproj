// The project page's two columns, kept from leaving a large empty space (Fabio,
// 23 Oct 2026): the side column's cards under the details (the meeting, the e-mail
// sign-up) stay there unless that leaves it much taller than the main one; then
// they move under the stages, the meeting first (the main column is the more
// seen, and the meeting matters more). Decided by the columns' heights alone.
import { useLayoutEffect, useState, type RefObject } from "react";

/** How far the side column may run past the main one before a card moves. */
export const SLACK = 160;

/** How many of the movable cards, in order, move to the bottom of the main column.
 *  `main` and `side` are the columns' heights without them, `cards` their heights
 *  (the first to move first) and `gap` the space before each. */
export function cardsToMove(main: number, side: number, cards: number[], gap: number): number {
  let left = main;
  let right = side + cards.reduce((sum, height) => sum + gap + height, 0);
  let moved = 0;
  for (let i = 0; i < cards.length && right - left > SLACK; i++) {
    const card = gap + cards[i]!;
    // Only if the columns end up closer than they were.
    if (Math.abs(right - card - (left + card)) >= right - left) break;
    right -= card;
    left += card;
    moved++;
  }
  return moved;
}

const height = (element: Element) => element.getBoundingClientRect().height;

/** The columns' children, without the movable cards (marked `data-movable`). */
const fixed = (column: HTMLElement) => [...column.children].filter((child) => !child.hasAttribute("data-movable"));

/** Heights of a column's children with the gaps between them. */
function stacked(elements: Element[], gap: number) {
  return elements.reduce((sum, element, i) => sum + (i ? gap : 0) + height(element), 0);
}

/** How many movable cards sit in the main column. Measured before the page is
 *  painted and again when anything else in the columns changes size; the cards'
 *  own changes (a sign-up confirmed) don't move them. Stacked columns (phones):
 *  none. */
export function useBalancedColumns(main: RefObject<HTMLElement | null>, side: RefObject<HTMLElement | null>) {
  const [moved, setMoved] = useState(0);
  useLayoutEffect(() => {
    const left = main.current;
    const right = side.current;
    if (!left || !right) return;
    const measure = () => {
      if (Math.abs(left.getBoundingClientRect().top - right.getBoundingClientRect().top) > 1) {
        setMoved(0);
        return;
      }
      const gap = parseFloat(getComputedStyle(right).rowGap) || 0;
      // The movable cards in their order on the page, whichever column holds them.
      const cards = [...right.querySelectorAll(":scope > [data-movable]"), ...left.querySelectorAll(":scope > [data-movable]")]
        .sort((a, b) => Number(a.getAttribute("data-movable")) - Number(b.getAttribute("data-movable")))
        .map(height);
      setMoved(cardsToMove(stacked(fixed(left), gap), stacked(fixed(right), gap), cards, gap));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    for (const element of [...fixed(left), ...fixed(right)]) observer.observe(element);
    return () => observer.disconnect();
  });
  return moved;
}
