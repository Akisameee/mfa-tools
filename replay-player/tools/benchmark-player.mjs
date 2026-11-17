import fs from "node:fs/promises";
import path from "node:path";
import { existsSync } from "node:fs";
import { chromium } from "playwright-core";
import { parseArgs } from "node:util";
const { values } = parseArgs({
  options: {
    url: { type: "string", default: "http://127.0.0.1:8765/" },
    seconds: { type: "string", default: "6" },
    output: {
      type: "string",
      default: "artifacts/player-refactor/baseline.json",
    },
  },
});
const browser = await chromium.launch({
  headless: true,
  executablePath: [
    path.join(
      process.env.LOCALAPPDATA || "",
      "Google/Chrome/Application/chrome.exe",
    ),
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  ].find(existsSync),
  args: [
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
  ],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1707, height: 960 },
    deviceScaleFactor: 1920 / 1707,
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const loadStart = performance.now();
  await page.goto(values.url);
  await page.waitForFunction(() => window.player, null, { timeout: 120000 });
  const loadSeconds = (performance.now() - loadStart) / 1000;
  const cases = await page.evaluate(() => {
    const events = player.bundle.events;
    return [
      { name: "early", at: 81844 },
      {
        name: "incremental-game",
        at: events.find((e) => e.kind === "begin" && e.tool === "wait").time,
      },
      { name: "late-dictionary", at: 11150000 },
      { name: "dense-page", at: events.find((e) => e.state === 2768).time },
    ];
  });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  const results = [];
  for (const item of cases) {
    await page.evaluate(({ at }) => {
      if (player.status.playing) player.command("toggle");
      player.command("plan");
      player.seek(at);
    }, item);
    await page.waitForTimeout(300);
    const before = await cdp.send("Performance.getMetrics");
    const data = await page.evaluate(async (seconds) => {
      const deltas = [],
        tasks = [],
        longTasks = [],
        clockDeltas = [];
      const observer = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) longTasks.push(e.duration);
      });
      observer.observe({ type: "longtask", buffered: false });
      let last = performance.now(),
        prevClock = document.querySelector("#elapsed").textContent,
        changedAt = last;
      const start = last;
      player.command("toggle");
      await new Promise((resolve) => {
        const tick = (now) => {
          deltas.push(now - last);
          last = now;
          const clock = document.querySelector("#elapsed").textContent;
          if (clock !== prevClock) {
            clockDeltas.push(now - changedAt);
            changedAt = now;
            prevClock = clock;
          }
          if (now - start >= seconds * 1000) resolve();
          else requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
      player.command("toggle");
      observer.disconnect();
      const sorted = deltas.slice(1).sort((a, b) => a - b),
        clocks = clockDeltas.slice(1).sort((a, b) => a - b);
      const q = (a, p) => a[Math.min(a.length - 1, Math.floor(a.length * p))];
      return {
        elapsedMs: last - start,
        rafFrames: deltas.length,
        clockUpdates: clockDeltas.length,
        rafP95Ms: q(sorted, 0.95),
        rafMaxMs: Math.max(...sorted),
        rafGapsOver25ms: sorted.filter((x) => x > 25).length,
        clockP95Ms: q(clocks, 0.95),
        clockMaxMs: Math.max(...clocks),
        longTasks,
        domNodes: document.querySelectorAll("*").length,
        toolRows: document.querySelectorAll(".tool-row").length,
        canvasCount: document.querySelectorAll("canvas").length,
        status: player.status,
      };
    }, +values.seconds);
    const after = await cdp.send("Performance.getMetrics");
    const a = Object.fromEntries(before.metrics.map((m) => [m.name, m.value])),
      b = Object.fromEntries(after.metrics.map((m) => [m.name, m.value]));
    data.cost = Object.fromEntries(
      [
        "ScriptDuration",
        "LayoutDuration",
        "RecalcStyleDuration",
        "TaskDuration",
        "LayoutCount",
        "RecalcStyleCount",
      ].map((k) => [k, b[k] - a[k]]),
    );
    data.heapMiB = b.JSHeapUsedSize / 1048576;
    results.push({ ...item, ...data });
    console.log(
      JSON.stringify({
        name: item.name,
        clockUpdates: data.clockUpdates,
        longTasks: data.longTasks,
        rafP95Ms: data.rafP95Ms,
        clockP95Ms: data.clockP95Ms,
        cost: data.cost,
        nodes: data.domNodes,
      }),
    );
  }
  await fs.mkdir(path.dirname(values.output), { recursive: true });
  await fs.writeFile(
    values.output,
    JSON.stringify(
      { loadSeconds, browser: browser.version(), results, errors },
      null,
      2,
    ),
  );
  if (errors.length) throw Error(errors.join("\n"));
} finally {
  await browser.close();
}
