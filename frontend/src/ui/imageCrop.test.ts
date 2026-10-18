import { describe, expect, it } from "vitest";

import { COVER_OUTPUT, LOGO_OUTPUT, centred, clearBackground, contentBox, flatBackground, outputSize } from "./imageCrop";

/** An image of `rows` (one letter a pixel): "." background, "#" drawing, "w" white. */
function image(rows: string[], background: [number, number, number, number]) {
  const width = rows[0]!.length;
  const pixels = new Uint8ClampedArray(width * rows.length * 4);
  rows.join("").split("").forEach((cell, p) => {
    const colour = cell === "#" ? [20, 20, 20, 255] : cell === "w" ? [255, 255, 255, 255] : background;
    pixels.set(colour, p * 4);
  });
  return { pixels, width, height: rows.length };
}
const alpha = (pixels: Uint8ClampedArray) => [...pixels].filter((_, i) => i % 4 === 3);

describe("trimming a logo's empty margins", () => {
  const rows = ["..........", "..........", "...####...", "...####...", "..........", ".........."];

  it("finds the drawing on a transparent background", () => {
    const { pixels, width, height } = image(rows, [0, 0, 0, 0]);
    const box = contentBox(pixels, width, height)!;
    expect(box.x).toBeCloseTo(20); // a pixel of room on each side
    expect(box.width).toBeCloseTo(60);
    expect(box.y).toBeCloseTo((1 / 6) * 100);
  });

  it("finds it on a white background too", () => {
    const { pixels, width, height } = image(rows, [255, 255, 255, 255]);
    expect(contentBox(pixels, width, height)!.width).toBeCloseTo(60);
  });

  it("has nothing to trim when the drawing fills the image, or there is none", () => {
    const full = image(["##", "##"], [0, 0, 0, 0]);
    expect(contentBox(full.pixels, full.width, full.height)).toBeNull();
    const empty = image(["..", ".."], [0, 0, 0, 0]);
    expect(contentBox(empty.pixels, empty.width, empty.height)).toBeNull();
  });
});

describe("removing a plain background", () => {
  it("is offered for a logo on white, not for a transparent one or a photo", () => {
    const onWhite = image(["....", ".##.", "...."], [255, 255, 255, 255]);
    expect(flatBackground(onWhite.pixels, onWhite.width, onWhite.height)).toEqual([255, 255, 255]);
    const clear = image(["....", ".##.", "...."], [0, 0, 0, 0]);
    expect(flatBackground(clear.pixels, clear.width, clear.height)).toBeNull();
    const photo = image(["#..w", "....", "w..#"], [120, 160, 200, 255]); // corners differ
    expect(flatBackground(photo.pixels, photo.width, photo.height)).toBeNull();
  });

  it("clears the background's colour everywhere, holes in letters too", () => {
    // An "o" on white: its inside is background as well.
    const ring = image(["wwwww", "w###w", "w#w#w", "w###w", "wwwww"], [255, 255, 255, 255]);
    clearBackground(ring.pixels, ring.width, ring.height, [255, 255, 255]);
    const a = alpha(ring.pixels);
    expect(a[0]).toBe(0); // the corner
    expect(a[2 * 5 + 2]).toBe(0); // the inside of the ring
    expect(a[1 * 5 + 1]).toBe(255); // the ring itself stays
  });

  it("keeps an edge pixel blended with the background partly see-through", () => {
    const edge = image(["ww", "wg"].map((r) => r), [255, 255, 255, 255]);
    edge.pixels.set([200, 200, 200, 255], 3 * 4); // a light grey beside white
    clearBackground(edge.pixels, edge.width, edge.height, [255, 255, 255]);
    const a = alpha(edge.pixels)[3]!;
    expect(a).toBeGreaterThan(0);
    expect(a).toBeLessThan(255);
  });
});

describe("a crop's shape and size", () => {
  it("starts a cover as the largest 3:2 box, centred", () => {
    expect(centred(3 / 2, 4000, 2000)).toEqual({ x: 12.5, y: 0, width: 75, height: 100 }); // a wide photo
    const tall = centred(3 / 2, 3000, 4000); // a phone photo held upright
    expect(tall.width).toBe(100);
    expect(tall.height).toBeCloseTo(50);
    expect(tall.y).toBeCloseTo(25);
  });

  it("never enlarges a photo, but draws a logo large enough to stay sharp", () => {
    const whole = { x: 0, y: 0, width: 100, height: 100 };
    expect(outputSize(whole, { width: 900, height: 600 }, COVER_OUTPUT)).toEqual({ width: 900, height: 600 });
    expect(outputSize(whole, { width: 6000, height: 4000 }, COVER_OUTPUT)).toEqual({ width: 2400, height: 1600 });
    expect(outputSize({ x: 0, y: 40, width: 100, height: 20 }, { width: 120, height: 120 }, LOGO_OUTPUT)).toEqual({
      width: 1200,
      height: 240,
    });
  });
});
