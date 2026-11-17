import { knownNote } from "../core/timeline.mjs";
import { annotationScore, annotationTooltip } from "../core/grading.mjs";

export function createProgressView({ bundle, playback }) {
  const $ = (s) => document.querySelector(s);
  const words = new Map(),
    groups = {},
    values = new WeakMap(),
    flashes = new Map();
  const wordState = new Map(),
    summaries = new Map();
  const grades = { correct: 0, close: 0, incorrect: 0, pending: 0 };
  let annotated = 0,
    completed = 0;
  const note = (key) =>
    (bundle.grading ? playback.state.writtenNotes : playback.state.notes).get(
      key,
    );
  function square() {
    const el = document.createElement("span");
    el.className = "square";
    return el;
  }
  const fragment = document.createDocumentFragment();
  for (const key of bundle.catalog.words) {
    const el = square();
    el.dataset.key = key;
    words.set(key, el);
    fragment.append(el);
  }
  $("#heatmap").append(fragment);
  $("#words small").textContent = ` / ${words.size}`;
  $("#heatmap").addEventListener("mouseover", (event) => {
    const el = event.target.closest(".square");
    if (el)
      el.title = annotationTooltip(
        bundle.grading,
        el.dataset.key,
        note(el.dataset.key),
      );
  });
  if (bundle.grading) {
    $("#words").title =
      "按历史标注版本显示模型评分；空心方块表示已标注但尚未评分";
    $("#words .progress-legend").title =
      "灰色未标注、红色错误、黄色接近、绿色正确；空心方块待评分";
  }
  for (const type of ["texts", "questions", "games"]) {
    const tiles = $(`#${type} .tiles`),
      elements = new Map(),
      fragment = document.createDocumentFragment();
    bundle.catalog[type].forEach((key, i) => {
      const el = square();
      el.dataset.number = String(i + 1);
      elements.set(key, el);
      fragment.append(el);
    });
    tiles.append(fragment);
    $(`#${type} small`).textContent = String(elements.size);
    groups[type] = { elements, previous: new Set(), signature: null };
  }
  function setSquare(el, value, status, animate) {
    const previous = values.get(el);
    if (previous === value) return;
    values.set(el, value);
    el.classList.toggle("marked", status !== "unknown");
    for (const key of ["correct", "close", "incorrect", "pending"])
      el.classList.toggle(key, key === status);
    if (!animate || previous === undefined) return;
    flashes.get(el)?.cancel();
    const animation = el.animate(
      [
        { outline: "1px solid rgba(255,255,255,1)", outlineOffset: "1px" },
        { outline: "1px solid rgba(255,255,255,0)", outlineOffset: "1px" },
      ],
      { duration: 650, easing: "ease-out" },
    );
    flashes.set(el, animation);
    animation.onfinish = () => {
      if (flashes.get(el) === animation) flashes.delete(el);
    };
  }
  function summary(selector, count, total, label, scores = null) {
    const signature = `${count}:${scores ? Object.values(scores).join(":") : ""}`;
    if (summaries.get(selector) === signature) return;
    summaries.set(selector, signature);
    const bar = $(selector);
    bar.style.setProperty(
      "--summary-fill",
      `${total ? ((scores ? scores.correct : count) / total) * 100 : 0}%`,
    );
    for (const key of ["close", "incorrect"])
      bar.style.setProperty(
        `--summary-${key}`,
        `${total && scores ? (scores[key] / total) * 100 : 0}%`,
      );
    bar.setAttribute("aria-valuemax", total);
    bar.setAttribute("aria-valuenow", count);
    bar.setAttribute("aria-valuetext", `${label} ${count} / ${total}`);
    bar.title = `${label} ${count} / ${total}${scores && bundle.grading ? `；正确 ${scores.correct}，接近 ${scores.close}，错误 ${scores.incorrect}，待评分 ${scores.pending}` : ""}`;
  }
  function update({ reset = false, keys = new Set(), progress = false } = {}) {
    if (reset) {
      for (const animation of flashes.values()) animation.cancel();
      flashes.clear();
    }
    for (const key of reset ? words.keys() : keys) {
      const el = words.get(key);
      if (!el) continue;
      const text = note(key),
        marked = knownNote(text),
        status = annotationScore(bundle.grading, key, text).status;
      const previous = wordState.get(key);
      if (previous?.text === text && previous?.status === status) continue;
      if (previous?.marked) {
        annotated--;
        grades[previous.status]--;
      }
      if (marked) {
        annotated++;
        grades[status]++;
      }
      wordState.set(key, { text, marked, status });
      setSquare(el, `${status}:${marked ? text : ""}`, status, !reset);
    }
    if ($("#words b").textContent !== String(annotated))
      $("#words b").textContent = String(annotated);
    summary("#words-bar", annotated, words.size, "已标注", grades);
    if (reset || progress) {
      completed = 0;
      for (const [type, group] of Object.entries(groups)) {
        const keys = playback.state.progress[type] || [],
          signature = keys.join("\0");
        completed += keys.length;
        if (signature === group.signature && !reset) continue;
        const finished = new Set(keys),
          changed = reset
            ? group.elements.keys()
            : new Set([...group.previous, ...finished]);
        for (const key of changed) {
          const el = group.elements.get(key);
          if (!el) continue;
          const done = finished.has(key);
          setSquare(el, done, done ? "correct" : "unknown", !reset);
          el.title = `${{ texts: "文本", questions: "题目", games: "游戏" }[type]} ${el.dataset.number} · ${done ? "已完成" : "尚未确认完成"}`;
        }
        group.previous = finished;
        group.signature = signature;
        $(`#${type} b`).textContent = String(finished.size);
      }
      summary(
        "#completion-bar",
        completed,
        Object.values(groups).reduce((sum, g) => sum + g.elements.size, 0),
        "已通过",
      );
    }
  }
  function layout() {
    const css = getComputedStyle($("#progress")),
      size = parseFloat(css.getPropertyValue("--tile-size")),
      gap = parseFloat(css.getPropertyValue("--tile-gap"));
    for (const type of ["texts", "questions", "games", "words"]) {
      const tiles = $(`#${type} .tiles`),
        columns = Math.max(
          1,
          Math.floor((tiles.clientWidth + gap) / (size + gap)),
        );
      tiles.style.setProperty(
        "--tile-rows",
        Math.max(1, Math.ceil(bundle.catalog[type].length / columns)),
      );
    }
  }
  const resize = new ResizeObserver(layout);
  resize.observe($("#progress"));
  layout();
  return {
    update,
    reflow: layout,
    note,
    get annotated() {
      return annotated;
    },
    dispose() {
      resize.disconnect();
    },
  };
}
