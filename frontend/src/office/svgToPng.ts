// Email programs don't show SVG images (A32), so an SVG logo also goes up as a PNG.
// Drawn here, in the browser: its lettering renders with the fonts it has on the
// site, which a server without fonts couldn't promise.
export const LOGO_PNG_SIZE = 600; // the longer side, in pixels; emails show it ~200 wide

export function isSvg(file: Blob & { name?: string }): boolean {
  return file.type === "image/svg+xml" || !!file.name?.toLowerCase().endsWith(".svg");
}

export async function svgToPng(svg: Blob, size = LOGO_PNG_SIZE): Promise<Blob> {
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    // An SVG without width and height still has a shape, from its viewBox.
    const wide = image.naturalWidth || 2;
    const high = image.naturalHeight || 1;
    const scale = size / Math.max(wide, high);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(wide * scale));
    canvas.height = Math.max(1, Math.round(high * scale));
    canvas.getContext("2d")!.drawImage(image, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve, reject) =>
      canvas.toBlob((png) => (png ? resolve(png) : reject(new Error("png"))), "image/png"),
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}
