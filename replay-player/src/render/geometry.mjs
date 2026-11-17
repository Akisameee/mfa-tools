// Recorded block anchors use Unity's bottom-up grid rows. The canvas uses
// top-down board units, with each row occupying 1.5 units.
export function dividerLines(geometry, rows = 9, columns = 24) {
  const lines = [];
  const middle = geometry.center_line;
  if (middle > 0 && middle < columns)
    lines.push([middle, 0, middle, rows * 1.5]);
  // Draw.ui_line_h is a fixed line below the first row, independent of titles.
  lines.push([0, 1.5, columns, 1.5]);
  const upper = geometry.right_message_u,
    lower = geometry.right_message_d;
  if (upper && lower && upper[1] > lower[1]) {
    const y = (rows - 1 - lower[1]) * 1.5;
    lines.push([middle ?? lower[0], y, columns, y]);
  }
  return lines;
}

// Match DrawRectRenderer(1, 1) and the 3-unit, two-row card frames. Adjacent
// cells share exact boundaries; combine coincident edges instead of insetting.
export function frameLines(frame) {
  const regions = [
    ...(frame.frames || []),
    ...(frame.boxes || []).map(([r, c]) => [r, c, r, c]),
  ];
  const groups = new Map();
  function edge(axis, position, start, end) {
    const key = `${axis}:${position}`;
    if (!groups.has(key)) groups.set(key, { axis, position, spans: [] });
    groups.get(key).spans.push([start, end]);
  }
  for (const [top, left, bottom, right] of regions) {
    const y = top * 1.5,
      height = top === bottom ? 1 : (bottom - top + 1) * 1.5;
    edge("h", y, left, right + 1);
    edge("h", y + height, left, right + 1);
    edge("v", left, y, y + height);
    edge("v", right + 1, y, y + height);
  }
  const lines = [];
  for (const { axis, position, spans } of groups.values()) {
    spans.sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const span of spans) {
      const last = merged.at(-1);
      if (last && span[0] <= last[1]) last[1] = Math.max(last[1], span[1]);
      else merged.push([...span]);
    }
    for (const [start, end] of merged)
      lines.push(
        axis === "h"
          ? [start, position, end, position]
          : [position, start, position, end],
      );
  }
  return lines;
}

export function underlineLines(cells) {
  const groups = new Map();
  for (const cell of cells) {
    if (!cell.underlined) continue;
    const key = `${cell.row}:${!!cell.dim}`;
    if (!groups.has(key))
      groups.set(key, { row: cell.row, dim: !!cell.dim, cols: [] });
    groups.get(key).cols.push(cell.col);
  }
  const lines = [];
  for (const { row, dim, cols } of groups.values()) {
    cols.sort((a, b) => a - b);
    const spans = [];
    for (const col of cols) {
      const last = spans.at(-1);
      if (last && col <= last[1]) last[1] = Math.max(last[1], col + 1);
      else spans.push([col, col + 1]);
    }
    for (const [left, right] of spans)
      lines.push({
        points: [left, row * 1.5 + 1.475, right, row * 1.5 + 1.475],
        dim,
      });
  }
  return lines;
}
