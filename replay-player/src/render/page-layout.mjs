const GAME_ASPECT = 24 / 13.5;

// Reserve the footer first; the game determines the column width, and chat
// receives the remaining space. Measurements run on resize, never per frame.
export function createPageLayout({ reflowProgress }) {
  const screen = document.querySelector("#screen");
  const left = document.querySelector("#left");
  const progress = document.querySelector("#progress");
  const properties = [
    "--game-column-width",
    "--chat-column-width",
    "--progress-min-height",
  ];
  let pending = null,
    previous = null;

  function reset() {
    for (const name of properties) screen.style.removeProperty(name);
    reflowProgress();
  }

  function layout() {
    pending = null;
    const css = getComputedStyle(screen);
    const width = parseFloat(css.width),
      height = parseFloat(css.height);
    previous = { width, height };
    // Measure the existing footer without a constrained height. Its height is
    // a floor for the fitted layout, even when a wider column needs fewer rows.
    reset();
    let footerHeight = parseFloat(getComputedStyle(progress).height);
    const border = parseFloat(getComputedStyle(left).borderRightWidth) || 0;
    for (let i = 0; i < 8; i++) {
      const column = (height - footerHeight) * GAME_ASPECT + border;
      if (column <= border || column >= width) break;
      screen.style.setProperty("--progress-min-height", `${footerHeight}px`);
      screen.style.setProperty("--game-column-width", `${column}px`);
      screen.style.setProperty("--chat-column-width", "minmax(0, 1fr)");
      reflowProgress();
      const measured = parseFloat(getComputedStyle(progress).height);
      if (Math.abs(measured - footerHeight) < 0.1) return;
      footerHeight = Math.max(footerHeight, measured);
    }
    // Very small/tall windows may not fit the fixed-size progress grids plus
    // a 16:9 game. Retain the readable intrinsic layout instead of overflowing.
    reset();
  }

  const observer = new ResizeObserver(([entry]) => {
    const { width, height } = entry.contentRect;
    if (
      previous &&
      Math.abs(previous.width - width) < 0.1 &&
      Math.abs(previous.height - height) < 0.1
    )
      return;
    if (pending === null) pending = requestAnimationFrame(layout);
  });
  layout();
  observer.observe(screen);
  return {
    dispose() {
      observer.disconnect();
      if (pending !== null) cancelAnimationFrame(pending);
    },
  };
}
