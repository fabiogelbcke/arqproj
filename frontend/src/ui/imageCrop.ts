// Cropping an image in the browser before it is uploaded (ImageCropDialog): the
// office's logo (any shape, empty margins trimmed) and a project's cover (3:2).

/** A crop in percent of the image, as the crop box gives it. */
export type Box = { x: number; y: number; width: number; height: number };

/** Covers have one shape everywhere they show (Fabio, 18 Oct 2026). */
export const COVER_ASPECT = 3 / 2;

export type Output = {
  type: "image/png" | "image/jpeg";
  long: number; // the longer side, in pixels, at most
  upscale: boolean; // a drawing (SVG) can grow; a photo never does
};
// A logo shows at most ~240 px wide; twice that for sharp screens, and room to spare.
export const LOGO_OUTPUT: Output = { type: "image/png", long: 1200, upscale: true };
// More than the widest the page shows a cover (about 1100 px, twice on sharp screens).
export const COVER_OUTPUT: Output = { type: "image/jpeg", long: 2400, upscale: false };

export async function loadImage(src: string): Promise<HTMLImageElement> {
  const image = new Image();
  image.src = src;
  await image.decode();
  return image;
}

/** The image's own size; an SVG without width and height has a shape from its viewBox. */
export function sizeOf(image: HTMLImageElement): { width: number; height: number } {
  return { width: image.naturalWidth || 300, height: image.naturalHeight || 150 };
}

/** Where the drawing is: the part that differs from the background (the corner's
 *  colour, or transparency), in percent, with a little room around it. Null when
 *  there is nothing to trim. `pixels` are RGBA rows, as a canvas gives them. */
export function contentBox(pixels: Uint8ClampedArray, width: number, height: number): Box | null {
  const at = (x: number, y: number) => (y * width + x) * 4;
  const [r, g, b, a] = pixels.slice(0, 4) as unknown as number[];
  const background = (i: number) => {
    const alpha = pixels[i + 3]!;
    if (a! < 16) return alpha < 16; // a transparent background
    return (
      alpha > 239 &&
      Math.abs(pixels[i]! - r!) < 24 &&
      Math.abs(pixels[i + 1]! - g!) < 24 &&
      Math.abs(pixels[i + 2]! - b!) < 24
    );
  };
  let top = height, bottom = -1, left = width, right = -1;
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++)
      if (!background(at(x, y))) {
        if (y < top) top = y;
        if (y > bottom) bottom = y;
        if (x < left) left = x;
        if (x > right) right = x;
      }
  if (bottom < 0) return null; // nothing drawn
  // A little room, so nothing touches the edge: 2% of the drawing's longer side.
  const pad = Math.max(1, Math.round(Math.max(right - left, bottom - top) * 0.02));
  left = Math.max(0, left - pad);
  top = Math.max(0, top - pad);
  right = Math.min(width - 1, right + pad);
  bottom = Math.min(height - 1, bottom + pad);
  const box = {
    x: (left / width) * 100,
    y: (top / height) * 100,
    width: ((right - left + 1) / width) * 100,
    height: ((bottom - top + 1) / height) * 100,
  };
  return box.width > 99 && box.height > 99 ? null : box;
}

/** The logo's trimmed box: read from a small copy, which is plenty to find edges. */
export function trimmed(image: HTMLImageElement): Box | null {
  const { width, height } = sizeOf(image);
  const scale = Math.min(1, 400 / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  return contentBox(context.getImageData(0, 0, canvas.width, canvas.height).data, canvas.width, canvas.height);
}

/** The largest box of this shape, centred. */
export function centred(aspect: number, width: number, height: number): Box {
  const wide = width / height > aspect;
  const w = wide ? ((height * aspect) / width) * 100 : 100;
  const h = wide ? 100 : (width / aspect / height) * 100;
  return { x: (100 - w) / 2, y: (100 - h) / 2, width: w, height: h };
}

/** The pixel size the crop is saved at. */
export function outputSize(box: Box, image: { width: number; height: number }, output: Output) {
  const width = (box.width / 100) * image.width;
  const height = (box.height / 100) * image.height;
  let scale = output.long / Math.max(width, height);
  if (!output.upscale) scale = Math.min(1, scale);
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

/** The cropped image, as a file to upload. */
export async function cropToFile(image: HTMLImageElement, box: Box, output: Output, name: string): Promise<File> {
  const size = sizeOf(image);
  const { width, height } = outputSize(box, size, output);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d")!;
  if (output.type === "image/jpeg") {
    context.fillStyle = "#fff"; // a transparent PNG made into a photo: white, not black
    context.fillRect(0, 0, width, height);
  }
  context.imageSmoothingQuality = "high";
  // An SVG is drawn at the scale it needs, so it stays sharp.
  const scaleX = width / ((box.width / 100) * size.width);
  const scaleY = height / ((box.height / 100) * size.height);
  context.drawImage(
    image,
    (-box.x / 100) * size.width * scaleX,
    (-box.y / 100) * size.height * scaleY,
    size.width * scaleX,
    size.height * scaleY,
  );
  const blob = await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((made) => (made ? resolve(made) : reject(new Error("crop"))), output.type, 0.88),
  );
  return new File([blob], name, { type: output.type });
}

/** The background's colour when the image has a plain one: its four corners the
 *  same opaque colour (a logo exported on white, say). Null when it is already
 *  transparent, or a photo. */
export function flatBackground(pixels: Uint8ClampedArray, width: number, height: number): [number, number, number] | null {
  const corners = [0, width - 1, (height - 1) * width, height * width - 1].map((p) => p * 4);
  const [first] = corners;
  for (const i of corners) {
    if (pixels[i + 3]! < 250) return null;
    if (distance(pixels, i, [pixels[first!]!, pixels[first! + 1]!, pixels[first! + 2]!]) > 24) return null;
  }
  return [pixels[first!]!, pixels[first! + 1]!, pixels[first! + 2]!];
}

const distance = (pixels: Uint8ClampedArray, i: number, [r, g, b]: [number, number, number]) =>
  Math.max(Math.abs(pixels[i]! - r), Math.abs(pixels[i + 1]! - g), Math.abs(pixels[i + 2]! - b));

const CLEAR = 32; // this close to the background: removed
const SOFT = 96; // up to this, at its edge: partly see-through, so edges stay smooth

/** The background's colour made transparent everywhere, holes in letters too
 *  (the inside of an "o" is background, not white), keeping edges smooth.
 *  `pixels` change in place. */
export function clearBackground(pixels: Uint8ClampedArray, width: number, height: number, colour: [number, number, number]): void {
  const removed = new Uint8Array(width * height);
  for (let p = 0; p < width * height; p++) if (distance(pixels, p * 4, colour) <= CLEAR) removed[p] = 1;
  for (let p = 0; p < width * height; p++) {
    const i = p * 4;
    if (removed[p]) {
      pixels[i + 3] = 0;
      continue;
    }
    // A pixel beside the removed background, blended with it: keep only its own share.
    const x = p % width;
    const beside =
      (x > 0 && removed[p - 1]) || (x < width - 1 && removed[p + 1]) || removed[p - width] || removed[p + width];
    const d = distance(pixels, i, colour);
    if (beside && d < SOFT) pixels[i + 3] = Math.round((pixels[i + 3]! * (d - CLEAR)) / (SOFT - CLEAR));
  }
}

/** The image without its plain background, as a PNG address; null when it has none. */
export async function withoutBackground(image: HTMLImageElement): Promise<string | null> {
  const { width: w, height: h } = sizeOf(image);
  const scale = Math.min(1, 2400 / Math.max(w, h));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(w * scale));
  canvas.height = Math.max(1, Math.round(h * scale));
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  const data = context.getImageData(0, 0, canvas.width, canvas.height);
  const colour = flatBackground(data.data, canvas.width, canvas.height);
  if (!colour) return null;
  clearBackground(data.data, canvas.width, canvas.height, colour);
  context.putImageData(data, 0, 0);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  return blob && URL.createObjectURL(blob);
}
