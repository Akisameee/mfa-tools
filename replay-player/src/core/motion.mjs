export const clamp = (value) => Math.max(0, Math.min(1, value));
export const CLICK_MIN_DURATION = 300;
export const POINTER_MIN_MOVE_DURATION = 90;
export const POINTER_MAX_SPEED = 0.065; // Board units/ms, including peak speed.
export const CLICK_SETTLE_DURATION = 40;
export const ease = (value) => {
  const x = clamp(value);
  return x * x * (3 - 2 * x);
};
export function pointerMoveDuration(motion) {
  if (!motion) return 0;
  const distance = Math.hypot(
    motion.target[0] - motion.from[0],
    motion.target[1] - motion.from[1],
  );
  if (distance < 1e-6) return 0;
  // Longer trips gain a little average speed. Smoothstep peaks at 1.5 times
  // average speed, so the final term bounds even the middle of the movement.
  return Math.max(
    POINTER_MIN_MOVE_DURATION,
    70 + 38 * distance ** 0.8,
    (1.5 * distance) / POINTER_MAX_SPEED,
  );
}
export function clickDuration(operation) {
  return Math.max(
    CLICK_MIN_DURATION,
    pointerMoveDuration(operation.motion) + CLICK_SETTLE_DURATION,
  );
}
const segmenter =
  typeof Intl.Segmenter === "function"
    ? new Intl.Segmenter("zh", { granularity: "grapheme" })
    : null;
const characterCache = new Map();
export function characters(text) {
  let result = characterCache.get(text);
  if (result) return result;
  result = segmenter
    ? [...segmenter.segment(text)].map((s) => s.segment)
    : Array.from(text);
  if (characterCache.size >= 4096)
    characterCache.delete(characterCache.keys().next().value);
  characterCache.set(text, result);
  return result;
}
// Physical screen time, independent of the selected thinking multiplier.
export function messageDuration(text) {
  return Math.min(6000, Math.max(300, characters(text).length * 22));
}
export function operationMotion(operation, at, start, end) {
  if (!operation?.motion) return null;
  const note = operation.tool === "note";
  const moveDuration = pointerMoveDuration(operation.motion);
  const duration = Math.max(
      1,
      end - start,
      note ? moveDuration + 125 : clickDuration(operation),
    ),
    age = at - start;
  const phase = clamp(age / duration);
  const m = operation.motion,
    travel = moveDuration ? ease(age / moveDuration) : 1;
  const from = m.from,
    to = m.target;
  const x = from[0] + (to[0] - from[0]) * travel;
  const y = from[1] + (to[1] - from[1]) * travel;
  // Sample this movement's recent path so seeking and pausing reproduce the
  // same short afterimage without accumulating mutable cursor history.
  const trail = [54, 36, 18].flatMap((delay, index) => {
    if (!moveDuration || age < delay) return [];
    const past = ease((age - delay) / moveDuration);
    if (travel - past < 1e-5) return [];
    return [
      {
        x: from[0] + (to[0] - from[0]) * past,
        y: from[1] + (to[1] - from[1]) * past,
        delay,
        opacity: (index + 1) * 0.03,
      },
    ];
  });
  const typingStart = moveDuration + 90;
  const typingEnd = Math.max(typingStart + 1, duration - 35);
  const typing = note && age >= typingStart && phase < 1;
  const letters = characters(operation.args.text || "");
  return {
    x,
    y,
    trail,
    target: to,
    phase,
    pressed: note
      ? age >= moveDuration && age < moveDuration + 45
      : age >= duration && age < duration + 65,
    clickAge: age - (note ? moveDuration : duration),
    editing: note && age >= moveDuration + 25 && phase < 1,
    typing,
    text: letters
      .slice(
        0,
        Math.floor(
          clamp((age - typingStart) / (typingEnd - typingStart)) *
            letters.length,
        ),
      )
      .join(""),
    selected: age < typingStart,
    cell: m.cell,
    floating: m.floating,
    key: m.key,
    oldText: m.oldText,
  };
}
