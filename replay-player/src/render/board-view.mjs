import { annotationLayout } from "./annotation.mjs";
import { dividerLines, frameLines, underlineLines } from "./geometry.mjs";
import { ease, clamp } from "../core/motion.mjs";
import { annotationScore } from "../core/grading.mjs";

export function createBoardView({
  bundle,
  atlas,
  playback,
  presentation,
  previewForCall,
}) {
  const canvas = document.querySelector("#board"),
    effectsCanvas = document.querySelector("#board-effects");
  const context = effectsCanvas.getContext("2d"),
    sceneContext = canvas.getContext("2d");
  const GAME_INK = "#e9d9a9",
    theme = getComputedStyle(document.documentElement);
  const ANNOTATION_COLORS = Object.fromEntries(
    ["correct", "close", "incorrect"].map((s) => [
      s,
      theme.getPropertyValue(`--status-${s}`).trim(),
    ]),
  );
  const ANNOTATION_TINT_OPACITY = Number(
    theme.getPropertyValue("--annotation-tint-opacity"),
  );
  const inspectionPreviews = new Map();
  let boardRevision = 0,
    annotationRevision = 0,
    lastBoardDraw = null,
    cachedScene = null;
  let size = { width: canvas.clientWidth, height: canvas.clientHeight };
  const resize = new ResizeObserver((entries) => {
    const box = entries[0].contentRect;
    size = { width: Math.round(box.width), height: Math.round(box.height) };
    cachedScene = null;
    lastBoardDraw = null;
    drawBoard();
  });
  resize.observe(canvas);
  function drawGlyph(ctx, key, x, y, width, height) {
    const rect = bundle.glyphs.items[key];
    if (rect) ctx.drawImage(atlas, ...rect, x, y, width, height);
    else {
      ctx.strokeStyle = "#776b51";
      ctx.strokeRect(
        x + width * 0.2,
        y + height * 0.2,
        width * 0.6,
        height * 0.6,
      );
    }
  }

  function resetGlyphPreview(preview, key) {
    const ctx = preview.getContext("2d");
    ctx.clearRect(0, 0, 64, 64);
    drawGlyph(ctx, key, 4, 4, 56, 56);
  }

  function currentMotion() {
    return presentation.motion(playback.position, playback.tempo);
  }

  function currentAnnotation(key) {
    return bundle.grading
      ? playback.state.writtenNotes.get(key)
      : playback.state.notes.get(key);
  }

  function drawBoard() {
    if (!bundle) return;
    const pixelRatio = window.devicePixelRatio || 1,
      w = size.width,
      h = size.height;
    if (
      canvas.width !== Math.round(w * pixelRatio) ||
      canvas.height !== Math.round(h * pixelRatio)
    ) {
      canvas.width = Math.round(w * pixelRatio);
      canvas.height = Math.round(h * pixelRatio);
      effectsCanvas.width = canvas.width;
      effectsCanvas.height = canvas.height;
      cachedScene = null;
    }
    const motion = currentMotion();
    const inspection = inspectionStatus();
    const animated =
      Boolean(motion && (motion.opacity > 0 || motion.editing)) ||
      inspection.effects.length > 0 ||
      inspectionPreviews.size > 0;
    // Thinking still advances the timer, but needs no repeated canvas painting
    // once pointer/editor/inspection effects have finished.
    if (
      !animated &&
      lastBoardDraw &&
      !lastBoardDraw.animated &&
      lastBoardDraw.revision === boardRevision &&
      lastBoardDraw.w === w &&
      lastBoardDraw.h === h &&
      lastBoardDraw.pixelRatio === pixelRatio
    )
      return;
    lastBoardDraw = { revision: boardRevision, w, h, pixelRatio, animated };
    const ctx = context,
      scale = Math.min(w / 24, h / 13.5);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, effectsCanvas.width, effectsCanvas.height);
    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    ctx.translate((w - scale * 24) / 2, (h - scale * 13.5) / 2);
    ctx.scale(scale, scale);
    const frame =
      playback.state.frame === null
        ? null
        : bundle.states[playback.state.frame];
    if (!frame) {
      if (!cachedScene || cachedScene.frame !== null) {
        sceneContext.setTransform(1, 0, 0, 1, 0, 0);
        sceneContext.fillStyle = "#000";
        sceneContext.fillRect(0, 0, canvas.width, canvas.height);
        cachedScene = { frame: null };
      }
      drawInspection(ctx, inspection);
      return;
    }
    // A click result is visible on the same tick as the button press.
    const editingCell =
      motion?.editing &&
      !motion.floating &&
      (!motion.page || motion.page === frame.page)
        ? frame.cells.find(
            (cell) =>
              cell.row === motion.cell?.[0] &&
              cell.col === motion.cell?.[1] &&
              cell.word === motion.key,
          )
        : null;
    if (
      !cachedScene ||
      cachedScene.frame !== frame ||
      cachedScene.editingCell !== editingCell ||
      cachedScene.annotationRevision !== annotationRevision
    ) {
      sceneContext.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      sceneContext.fillStyle = "#000";
      sceneContext.fillRect(0, 0, w, h);
      sceneContext.translate((w - scale * 24) / 2, (h - scale * 13.5) / 2);
      sceneContext.scale(scale, scale);
      drawFrame(sceneContext, frame, 1, null, editingCell, !editingCell);
      cachedScene = { frame, editingCell, annotationRevision };
    }
    // The browser composites the cached board and transparent effects canvas.
    if (editingCell) {
      ctx.save();
      ctx.globalAlpha = editingCell.dim ? 0.4 : 1;
      drawAnnotation(
        ctx,
        motion.selected ? motion.oldText : motion.text,
        editingCell.col,
        editingCell.row * 1.5,
        motion,
        editingCell.word,
      );
      ctx.restore();
      drawUnderlines(ctx, frame.cells);
    }
    drawInspection(ctx, inspection);
    if (motion?.floating && motion.editing) drawFloatingNote(ctx, motion);
    if (motion && motion.opacity > 0) drawMouse(ctx, motion, scale);
  }

  function drawFrame(
    ctx,
    frame,
    opacity,
    motion,
    excludedCell = null,
    includeUnderlines = true,
  ) {
    ctx.save();
    ctx.globalAlpha = opacity;
    ctx.lineWidth = 0.028;
    ctx.strokeStyle = GAME_INK;
    ctx.fillStyle = GAME_INK;
    const line = (x1, y1, x2, y2) => {
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    };
    for (const points of dividerLines(frame.geometry || {})) line(...points);
    ctx.save();
    ctx.lineCap = "square";
    ctx.beginPath();
    for (const [x1, y1, x2, y2] of frameLines(frame)) {
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
    }
    ctx.stroke();
    ctx.restore();
    for (const cell of frame.cells) {
      const x = cell.col,
        y = cell.row * 1.5;
      if (cell.highlight) {
        ctx.fillStyle = "#514733";
        ctx.fillRect(x + 0.02, y + 0.02, 0.96, 1);
      }
      ctx.globalAlpha = opacity * (cell.dim ? 0.4 : 1);
      drawGlyph(ctx, cell.word, x + 0.06, y + 0.055, 0.88, 0.88);
      const editing =
        motion?.editing &&
        !motion.floating &&
        motion.cell?.[0] === cell.row &&
        motion.cell?.[1] === cell.col &&
        cell.word === motion.key &&
        (!motion.page || motion.page === frame.page);
      const text = editing
        ? motion.selected
          ? motion.oldText
          : motion.text
        : cell.note || "?";
      if (cell !== excludedCell)
        drawAnnotation(ctx, text, x, y, editing ? motion : null, cell.word);
      ctx.globalAlpha = opacity;
    }
    if (includeUnderlines) drawUnderlines(ctx, frame.cells, opacity);
    ctx.restore();
  }

  function drawUnderlines(ctx, cells, opacity = 1) {
    ctx.save();
    ctx.strokeStyle = GAME_INK;
    ctx.lineWidth = 0.028;
    ctx.lineCap = "square";
    for (const { points, dim } of underlineLines(cells)) {
      ctx.globalAlpha = opacity * (dim ? 0.4 : 1);
      ctx.beginPath();
      ctx.moveTo(points[0], points[1]);
      ctx.lineTo(points[2], points[3]);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawAnnotation(ctx, text, x, y, motion = null, key = motion?.key) {
    ctx.save();
    const roundedField = (left, top, width, height, radius) => {
      ctx.beginPath();
      ctx.roundRect(left, top, width, height, radius);
    };
    if (motion) {
      ctx.fillStyle = "#161c1b";
      roundedField(x + 0.05, y + 1.025, 0.9, 0.43, 0.065);
      ctx.fill();
    }
    const gradingText =
      bundle.grading && (!motion || motion.selected)
        ? currentAnnotation(key)
        : text;
    const tint =
      ANNOTATION_COLORS[
        annotationScore(bundle.grading, key, gradingText).status
      ];
    if (tint) {
      ctx.save();
      ctx.globalAlpha *= ANNOTATION_TINT_OPACITY;
      ctx.fillStyle = tint;
      roundedField(x + 0.025, y + 1.005, 0.95, 0.475, 0.075);
      ctx.fill();
      ctx.restore();
    }
    if (motion) {
      ctx.strokeStyle = "#8dbda8";
      ctx.lineWidth = 0.012;
      roundedField(x + 0.05, y + 1.025, 0.9, 0.43, 0.065);
      ctx.stroke();
      if (motion.selected) {
        ctx.fillStyle = "#365848";
        roundedField(x + 0.07, y + 1.045, 0.86, 0.39, 0.05);
        ctx.fill();
      }
    }
    const { font, lines, lineHeight, height } = annotationLayout(ctx, text);
    const textTop = y + 1.01 + (0.46 - height) / 2;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillStyle = GAME_INK;
    lines.forEach((line, index) =>
      ctx.fillText(line, x + 0.5, textTop + index * lineHeight),
    );
    if (motion && !motion.selected && Math.floor(motion.age / 380) % 2 === 0) {
      const caretX =
        x + 0.5 + ctx.measureText(lines.at(-1) || "").width / 2 + 0.015;
      const caretY = textTop + Math.max(0, lines.length - 1) * lineHeight;
      ctx.strokeStyle = GAME_INK;
      ctx.lineWidth = 0.018;
      ctx.beginPath();
      ctx.moveTo(caretX, caretY);
      ctx.lineTo(caretX, caretY + font);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawFloatingNote(ctx, motion) {
    // A single-cell editor at the recorded pointer target; no invented navigation.
    const x = motion.target[0] - 0.5,
      y = motion.target[1] - 1.25;
    ctx.save();
    ctx.fillStyle = "#070a09";
    ctx.fillRect(x - 0.08, y - 0.08, 1.16, 1.66);
    ctx.strokeStyle = "#293a32";
    ctx.lineWidth = 0.012;
    ctx.strokeRect(x - 0.08, y - 0.08, 1.16, 1.66);
    drawGlyph(ctx, motion.key, x + 0.06, y + 0.055, 0.88, 0.88);
    drawAnnotation(
      ctx,
      motion.selected ? motion.oldText : motion.text,
      x,
      y,
      motion,
    );
    ctx.restore();
  }

  function drawMouse(ctx, motion, scale) {
    ctx.save();
    ctx.globalAlpha = motion.opacity;
    for (const ghost of motion.trail) {
      const dx = (ghost.x - motion.x) * scale,
        dy = (ghost.y - motion.y) * scale;
      const distance = Math.hypot(dx, dy);
      // Keep the afterimage subtle even on a fast trip across the board.
      const fraction = Math.min(1, (24 * ghost.delay) / (54 * distance));
      drawPointer(
        ctx,
        motion.x + (dx * fraction) / scale,
        motion.y + (dy * fraction) / scale,
        scale,
        ghost.opacity,
      );
    }
    if (motion.clickAge >= 0 && motion.clickAge < 180) {
      const pulse = motion.clickAge / 180;
      ctx.strokeStyle = `rgba(226,237,231,${(1 - pulse) * 0.65})`;
      ctx.lineWidth = 1 / scale;
      ctx.beginPath();
      ctx.arc(motion.x, motion.y, 0.06 + pulse * 0.2, 0, Math.PI * 2);
      ctx.stroke();
    }
    drawPointer(ctx, motion.x, motion.y, scale);
    ctx.restore();
  }

  function drawPointer(ctx, x, y, scale, opacity = 1) {
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(1 / scale, 1 / scale);
    ctx.rotate(Math.PI / 9);
    ctx.scale(0.78, 0.78);
    ctx.globalAlpha *= opacity;
    // Four vertices, with the third inset to make a concave arrowhead. The tip
    // remains the click hotspot, and size stays constant across board scales.
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(11, 25);
    ctx.lineTo(12, 13);
    ctx.lineTo(25, 11);
    ctx.closePath();
    ctx.fillStyle = "#eef3ee";
    ctx.strokeStyle = "#080c0a";
    ctx.lineWidth = 1.2;
    ctx.lineJoin = "miter";
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  function inspectionStatus() {
    const frame =
      playback.state.frame === null
        ? null
        : bundle.states[playback.state.frame];
    return presentation.inspection(playback.position, playback.tempo, frame);
  }

  function paintInspectionMark(ctx, x, y, width, height, age, lineWidth) {
    const outline = clamp(age / 220),
      fade = 1 - ease((age - 840) / 160);
    ctx.save();
    ctx.strokeStyle = GAME_INK;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = "butt";
    ctx.lineJoin = "miter";
    ctx.globalAlpha = fade;
    ctx.shadowBlur = 0;
    // Trace a square-cornered frame clockwise before starting the scan.
    const points = [
      [x, y],
      [x + width, y],
      [x + width, y + height],
      [x, y + height],
      [x, y],
    ];
    let remaining = 2 * (width + height) * outline;
    ctx.beginPath();
    ctx.moveTo(x, y);
    for (let i = 1; i < points.length && remaining > 0; i++) {
      const [ax, ay] = points[i - 1],
        [bx, by] = points[i];
      const length = Math.hypot(bx - ax, by - ay),
        fraction = Math.min(1, remaining / length);
      ctx.lineTo(ax + (bx - ax) * fraction, ay + (by - ay) * fraction);
      remaining -= length;
    }
    ctx.stroke();
    if (age >= 240 && age < 800) {
      ctx.beginPath();
      ctx.rect(x, y, width, height);
      ctx.clip();
      const rise = width * 0.5;
      const center = y - rise + clamp((age - 240) / 560) * (height + rise * 2);
      ctx.beginPath();
      ctx.moveTo(x, center + rise);
      ctx.lineTo(x + width, center - rise);
      ctx.lineWidth = lineWidth * 2;
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawInspection(ctx, inspection = inspectionStatus()) {
    // Restore previous previews before compositing this frame's independent effects.
    for (const { preview, key } of inspectionPreviews.values())
      resetGlyphPreview(preview, key);
    inspectionPreviews.clear();
    const { effects } = inspection,
      painted = new Set();
    for (const { age, cells, key, call } of effects) {
      if (!key) continue;
      for (const cell of cells) {
        const id = `${cell.row}:${cell.col}`;
        if (painted.has(id)) continue;
        painted.add(id);
        paintInspectionMark(
          ctx,
          cell.col + 0.025,
          cell.row * 1.5 + 0.025,
          0.95,
          0.95,
          age,
          0.025,
        );
      }
      const preview = previewForCall(call);
      if (preview) {
        resetGlyphPreview(preview, key);
        const target = preview.getContext("2d");
        paintInspectionMark(target, 2, 2, 60, 60, age, 2);
        inspectionPreviews.set(call, { preview, key });
      }
    }
  }

  return {
    draw: drawBoard,
    motion: currentMotion,
    inspection: inspectionStatus,
    glyph: drawGlyph,
    preview: resetGlyphPreview,
    note: currentAnnotation,
    invalidate({ frame = false, notes = false } = {}) {
      if (frame) boardRevision++;
      if (notes) annotationRevision++;
    },
    dispose() {
      resize.disconnect();
    },
  };
}
