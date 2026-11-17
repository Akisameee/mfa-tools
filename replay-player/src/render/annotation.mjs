import { characters } from "../core/motion.mjs";

export const TEXT_FONT =
  '"Replay PT Sans", "Replay FZ Hei", "Microsoft YaHei", sans-serif';
const layoutCaches = new WeakMap();

export function annotationLayout(ctx, text, width = 0.94, height = 0.46) {
  let cache = layoutCaches.get(ctx);
  if (!cache) layoutCaches.set(ctx, (cache = new Map()));
  const key = JSON.stringify([text, width, height]);
  const cached = cache.get(key);
  if (cached) {
    ctx.font = `${cached.font}px ${TEXT_FONT}`;
    return cached;
  }
  const letters = characters(text);
  // Start at a readable size. Short notes keep one line at full size.
  for (let font = 0.28; font >= 0.06; font -= 0.005) {
    ctx.font = `${font}px ${TEXT_FONT}`;
    const lines = [];
    let line = "";
    for (const ch of letters) {
      if (line && ctx.measureText(line + ch).width > width) {
        lines.push(line);
        line = "";
      }
      line += ch;
    }
    lines.push(line);
    const lineHeight = font * 1.06;
    if (lines.length * lineHeight <= height || font < 0.065) {
      const result = {
        font,
        lines,
        lineHeight,
        height: lines.length * lineHeight,
      };
      if (cache.size >= 4096) cache.delete(cache.keys().next().value);
      cache.set(key, result);
      return result;
    }
  }
}
