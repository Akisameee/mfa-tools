import { viewAt, sourceAt, rateAt } from "../src/core/tempo.mjs";

// Advance screen time, then invert the continuous tempo map. Crossing a segment
// never pauses the recording clock, jumps it, or creates animation debt.
let state = { position: 0, playing: false, duration: 0, segments: [] };
let anchor = performance.now(),
  anchorView = 0;
onmessage = ({ data }) => {
  state = { ...state, ...data };
  anchor = performance.now();
  anchorView = viewAt(state.segments, state.position);
};
setInterval(() => {
  if (!state.playing || !state.segments.length) return;
  const position = sourceAt(
    state.segments,
    anchorView + performance.now() - anchor,
  );
  postMessage({
    position,
    playing: position < state.duration,
    actualSpeed: rateAt(state.segments, position),
    revision: state.revision,
  });
}, 20);
