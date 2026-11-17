export const knownNote = (note) =>
  Boolean(note && note.trim() && note.trim() !== "?");
export const eventTime = (event) => event.time ?? event.real;
export function indexAt(events, position) {
  let low = 0,
    high = events.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (eventTime(events[middle]) <= position) low = middle + 1;
    else high = middle;
  }
  return low - 1;
}
export function replayState(events, index) {
  const state = {
    frame: null,
    previousFrame: null,
    frameChangedAt: 0,
    notes: new Map(),
    writtenNotes: new Map(),
    pendingNotes: new Map(),
    completed: 0,
    progress: { texts: [], questions: [], games: [] },
    active: null,
  };
  for (let i = 0; i <= index; i++) applyEvent(state, events[i]);
  return state;
}
export function applyEvent(state, event) {
  if (event.kind === "begin") state.active = event;
  if (event.kind === "begin" && event.tool === "note")
    state.pendingNotes.set(event.call, event.args.text || "");
  if (event.kind !== "end") return;
  if (event.tool === "compact_context") return;
  if (event.tool === "note") {
    if (
      event.status === "ok" &&
      event.character?.key &&
      state.pendingNotes.has(event.call)
    )
      state.writtenNotes.set(
        event.character.key,
        state.pendingNotes.get(event.call),
      );
    state.pendingNotes.delete(event.call);
  }
  if (state.frame !== event.state) {
    state.previousFrame = state.frame;
    state.frameChangedAt = event;
  }
  state.frame = event.state;
  state.completed = event.completed;
  state.progress = event.progress || { texts: [], questions: [], games: [] };
  for (const [key, note] of Object.entries(event.updates))
    state.notes.set(key, note);
}
