import { eventTime } from "../core/timeline.mjs";
import { characters, messageDuration, ease } from "../core/motion.mjs";
import { messageText } from "../core/conversation.mjs";
import { COMPACTION_SPEED } from "../core/tempo.mjs";
import { VirtualToolList } from "./virtual-tool-list.mjs";

export function createChatView({
  bundle,
  playback,
  hashGlyphs,
  callResults,
  getBoard,
  getOfflineExport,
}) {
  const root = document.querySelector("#chat"),
    scrollRoot = document.querySelector("#conversation-scroll");
  const elements = [],
    groups = [],
    tools = new Map(),
    compactions = new Map(),
    generating = new Map();
  let currentGroup = null,
    previousPosition = 0,
    previousTempo = null,
    tail = 0;
  let scrollRequested = false,
    instant = false,
    scrollTail = 0;
  const scrolls = new Map();
  function node(tag, name, text) {
    const el = document.createElement(tag);
    if (name) el.className = name;
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function label(event) {
    const a = event.args || {};
    return (
      {
        click: `${a.type === "right" ? "右键" : "左键"} · (${a.row}, ${a.col})`,
        note: `→ ${a.text || "清除标注"}`,
        glyph: "",
        look: a.type === "screenshot" ? "截图" : "页面",
        wait: `${a.seconds} 秒`,
      }[event.tool] || ""
    );
  }
  function preview(item, key) {
    if (!item.result) return;
    let canvas = item.result.querySelector("canvas");
    if (!canvas) {
      canvas = node("canvas", "glyph-preview");
      canvas.width = canvas.height = 64;
      canvas.title = key ? "字形" : "字形未记录";
      item.result.append(canvas);
    }
    getBoard().preview(canvas, key);
  }
  function details(item) {
    item.detail.replaceChildren();
    const data =
      item.end && item.end.index <= playback.cursor
        ? {
            arguments: item.event.args,
            result: item.end.event.result,
            error: item.end.event.error,
          }
        : item.event.args;
    const text = JSON.stringify(data, null, 2);
    let previous = 0;
    for (const match of text.matchAll(/\b[a-z0-9]{4}\b/g)) {
      if (!hashGlyphs.has(match[0])) continue;
      item.detail.append(
        document.createTextNode(text.slice(previous, match.index)),
      );
      const canvas = node("canvas", "detail-glyph");
      canvas.width = canvas.height = 64;
      getBoard().preview(canvas, hashGlyphs.get(match[0]));
      item.detail.append(canvas);
      previous = match.index + match[0].length;
    }
    item.detail.append(document.createTextNode(text.slice(previous)));
  }
  function updateRow(item) {
    if (!item.el) return;
    const done = item.end && item.end.index <= playback.cursor,
      failed = done && item.end.event.status === "error";
    item.el.classList.toggle("pending", !done);
    item.el.classList.toggle("failed", !!failed);
    item.badge.textContent = done ? (failed ? "×" : "✓") : "·";
    item.badge.title = done ? (failed ? "失败" : "完成") : "执行中";
    if (!item.detail.hidden) details(item);
  }
  function createRow(item) {
    item.el = node("div", "tool-row");
    item.badge = node("span", "badge");
    item.detail = node("pre");
    item.detail.hidden = !item.expanded;
    const description = node("div", "tool-description"),
      name = node("span", "name", item.event.tool),
      args = node("span", "args", label(item.event));
    args.title = label(item.event);
    item.result = node("div", "tool-target");
    description.append(name, item.result, args);
    item.el.append(description, item.badge, item.detail);
    if (item.event.args?.hash) preview(item, item.key);
    item.el.onclick = () => {
      item.detail.hidden = !item.detail.hidden;
      item.expanded = !item.detail.hidden;
      if (item.detail.hidden) item.detail.replaceChildren();
      else details(item);
      item.group.virtual.measure(item);
    };
    updateRow(item);
  }
  function release(item) {
    item.el = item.result = item.detail = item.badge = null;
  }
  const ends = new Map(
    bundle.events.flatMap((e, index) =>
      e.kind === "end" ? [[e.call, { event: e, index }]] : [],
    ),
  );
  let building = null;
  function closeGroup(index) {
    if (building) building.closeIndex = index;
    building = null;
  }
  for (const [index, event] of bundle.events.entries()) {
    if (event.kind === "message") {
      closeGroup(index);
      const text = messageText(event),
        el = node(
          "div",
          event.role === "user" ? "message user-message" : "message",
          text,
        );
      el.dataset.role = event.role || "assistant";
      el.hidden = true;
      root.append(el);
      elements[index] = { type: "message", el, text, event, index };
    } else if (event.kind === "begin" && event.tool === "compact_context") {
      closeGroup(index);
      const el = node("div", "compaction-card"),
        header = node("div", "compaction-header"),
        status = node("span", "compaction-status");
      header.append(
        node("span", "", "压缩上下文"),
        node("span", "compaction-speed", `${COMPACTION_SPEED}×`),
        status,
      );
      el.append(header);
      el.hidden = true;
      root.append(el);
      const item = {
        type: "compaction",
        el,
        status,
        event,
        index,
        end: ends.get(event.call),
      };
      elements[index] = item;
      compactions.set(event.call, item);
    } else if (event.kind === "begin") {
      if (!building) {
        const el = node("details", "tool-group"),
          summary = node("summary", "", "工具调用"),
          count = node("span", "group-count"),
          list = node("div", "tool-list");
        summary.append(count);
        el.append(summary, list);
        el.hidden = true;
        root.append(el);
        building = {
          el,
          count,
          list,
          items: [],
          visible: 0,
          closeIndex: Infinity,
        };
        const group = building;
        groups.push(group);
        el.addEventListener("toggle", () => {
          if (el.open) group.virtual.setVisible(group.visible, true);
          else group.virtual.clear();
        });
      }
      const item = {
        type: "tool",
        event,
        index,
        end: ends.get(event.call),
        group: building,
        key:
          event.motion?.key ||
          event.focus?.key ||
          callResults.get(event.call)?.character?.key ||
          hashGlyphs.get(event.args?.hash),
      };
      tools.set(event.call, item);
      building.items.push(item);
      elements[index] = item;
    }
  }
  for (const group of groups)
    group.virtual = new VirtualToolList(
      group.list,
      group.items,
      createRow,
      release,
    );
  function requestScroll(smooth = playback.playing) {
    const offline = getOfflineExport();
    if (offline) {
      offline.dom.requestScroll(smooth);
      return;
    }
    scrollRequested = true;
    instant ||= !smooth;
  }
  function openLists() {
    return groups.filter((g) => g.el.open).map((g) => g.list);
  }
  function flushScroll(time = performance.now()) {
    if (getOfflineExport()) return;
    // All layout reads are batched before scroll writes, and only after content changes.
    if (scrollRequested) {
      const measurements = [...openLists(), scrollRoot].map((el) => ({
        el,
        target: Math.max(0, el.scrollHeight - el.clientHeight),
        from: el.scrollTop,
      }));
      for (const { el, target, from } of measurements) {
        const old = scrolls.get(el);
        if (instant || old?.target !== target)
          scrolls.set(el, { from, target, start: time, instant });
      }
      scrollRequested = false;
      instant = false;
    }
    let active = false;
    for (const [el, state] of scrolls) {
      const fraction = state.instant ? 1 : ease((time - state.start) / 220);
      el.scrollTop = state.from + (state.target - state.from) * fraction;
      if (fraction >= 1) scrolls.delete(el);
      else active = true;
    }
    if (active && !playback.playing && !scrollTail)
      scrollTail = requestAnimationFrame((now) => {
        scrollTail = 0;
        flushScroll(now);
      });
  }
  function compaction(item) {
    const done = item.end && item.end.index <= playback.cursor,
      failed = done && item.end.event.status === "error";
    item.el.classList.toggle("pending", !done);
    item.el.classList.toggle("failed", !!failed);
    item.status.textContent = done ? (failed ? "失败" : "已完成") : "压缩中";
  }
  function reset(cursor) {
    generating.clear();
    cancelAnimationFrame(tail);
    tail = 0;
    scrolls.clear();
    previousPosition = playback.position;
    previousTempo = playback.tempo;
    currentGroup = null;
    for (const item of elements)
      if (item?.type === "message") {
        item.el.hidden = item.index > cursor;
        item.el.textContent = item.text;
        item.el.removeAttribute("data-generating");
      }
    for (const item of compactions.values()) {
      item.el.style.animation = "none";
      item.el.hidden = item.index > cursor;
      if (!item.el.hidden) compaction(item);
    }
    for (const group of groups) {
      group.virtual.clear();
      let low = 0,
        high = group.items.length;
      group.el.style.animation = "none";
      while (low < high) {
        const mid = (low + high) >>> 1;
        if (group.items[mid].index <= cursor) low = mid + 1;
        else high = mid;
      }
      group.visible = low;
      group.count.textContent = `${low} 次`;
      group.el.hidden = !low;
      group.el.open = low > 0 && group.closeIndex > cursor;
      if (group.el.open) {
        currentGroup = group;
        group.virtual.setVisible(low, true);
      }
    }
    requestScroll(false);
  }
  function event(index, animate = true) {
    const e = bundle.events[index],
      item = elements[index];
    if (e.kind === "message") {
      if (currentGroup) {
        currentGroup.el.open = false;
        currentGroup.virtual.clear();
      }
      currentGroup = null;
      item.el.hidden = false;
      if (animate) {
        item.letters ||= characters(item.text);
        item.el.setAttribute("data-generating", "");
        generating.set(index, {
          item,
          age: Math.max(
            0,
            playback.tempo.toView(playback.position) -
              playback.tempo.toView(eventTime(e)),
          ),
          duration: messageDuration(item.text),
          count: -1,
        });
      }
    } else if (e.kind === "begin" && e.tool === "compact_context") {
      if (currentGroup) {
        currentGroup.el.open = false;
        currentGroup.virtual.clear();
      }
      currentGroup = null;
      item.el.style.animation = "";
      item.el.hidden = false;
      compaction(item);
    } else if (e.kind === "begin") {
      const group = item.group;
      currentGroup = group;
      if (group.el.hidden) group.el.style.animation = "";
      group.el.hidden = false;
      group.el.open = true;
      group.count.textContent = `${++group.visible} 次`;
      group.virtual.setVisible(group.visible, true);
    } else if (e.kind === "end") {
      if (compactions.has(e.call)) compaction(compactions.get(e.call));
      else if (tools.has(e.call)) updateRow(tools.get(e.call));
    }
    if (e.kind === "begin" || e.kind === "message") requestScroll();
  }
  function revealMessages(elapsed = 0) {
    let changed = false;
    for (const [index, animation] of generating) {
      const { item, duration } = animation;
      animation.age += elapsed;
      const count = Math.min(
        item.letters.length,
        Math.max(
          1,
          Math.floor((animation.age / duration) * item.letters.length),
        ),
      );
      if (count !== animation.count) {
        item.el.textContent = item.letters.slice(0, count).join("");
        animation.count = count;
        changed = true;
      }
      if (count === item.letters.length) {
        item.el.removeAttribute("data-generating");
        generating.delete(index);
      }
    }
    if (changed) requestScroll(false);
  }
  function advanceMessages() {
    revealMessages(
      previousTempo
        ? Math.max(
            0,
            previousTempo.toView(playback.position) -
              previousTempo.toView(previousPosition),
          )
        : 0,
    );
    previousPosition = playback.position;
    previousTempo = playback.tempo;
  }
  function finishTail() {
    if (
      getOfflineExport() ||
      tail ||
      !generating.size ||
      playback.position < playback.duration
    )
      return;
    let previous = performance.now();
    const tick = (now) => {
      tail = 0;
      if (playback.position < playback.duration) return;
      revealMessages(now - previous);
      previous = now;
      flushScroll(now);
      if (generating.size) tail = requestAnimationFrame(tick);
    };
    tail = requestAnimationFrame(tick);
  }
  const resize = new ResizeObserver(() => {
    if (playback.playing) requestScroll(false);
  });
  resize.observe(root);
  return {
    reset,
    event,
    advanceMessages,
    revealMessages,
    finishTail,
    requestScroll,
    flushScroll,
    openLists,
    previewForCall: (call) => tools.get(call)?.result?.querySelector("canvas"),
    get mountedRows() {
      return groups.reduce((sum, g) => sum + g.virtual.mounted.size, 0);
    },
  };
}
