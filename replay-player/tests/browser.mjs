import assert from "node:assert/strict";
import { chromium } from "playwright-core";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const artifacts = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../artifacts/player-refactor");

const browser = await chromium.launch({
  headless: true,
  executablePath: [
    path.join(
      process.env.LOCALAPPDATA || "",
      "Google/Chrome/Application/chrome.exe",
    ),
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  ].find(existsSync),
});
try {
  const page = await browser.newPage({
    viewport: { width: 1707, height: 960 },
    deviceScaleFactor: 1920 / 1707,
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(process.env.PLAYER_URL || "http://127.0.0.1:8765/");
  await page.waitForFunction(() => window.player, null, { timeout: 120000 });
  assert.equal(await page.locator(".tool-row").count(), 0);
  assert.equal(await page.locator(".message:visible").count(), 0);
  const initial = await page.evaluate(() => player.status);
  assert.equal(initial.cursor, -1);
  await page.locator("#toggle").click();
  await page.waitForFunction(() =>
    document.querySelector(".user-message[data-generating]"),
  );
  await page.locator("#toggle").click();
  const partial = await page.locator(".user-message:visible").innerText();
  assert(partial.length > 0);
  assert(
    partial.length <
      (await page.evaluate(() => player.bundle.events[0].text.length)),
  );
  await page.waitForTimeout(80);
  assert.equal(
    await page.locator(".user-message:visible").innerText(),
    partial,
  );

  // Complete history remains reachable, but rendered rows stay bounded.
  await page.evaluate(() => player.command("end"));
  const final = await page.evaluate(() => player.status);
  const expected = await page.evaluate(() => {
    const end = player.bundle.events
      .filter((e) => e.kind === "end" && e.tool !== "compact_context")
      .at(-1);
    return {
      progress: end.progress,
      completed: end.completed,
      messages: player.bundle.events.filter((e) => e.kind === "message").length,
    };
  });
  assert.equal(final.completed, expected.completed);
  for (const kind of ["texts", "questions", "games"])
    assert.equal(
      await page.locator(`#${kind} .marked`).count(),
      expected.progress[kind].length,
    );
  assert.equal(
    await page.locator(".message:visible").count(),
    expected.messages,
  );
  assert((await page.locator(".tool-row").count()) <= 64);
  assert((await page.locator("*").count()) < 5000);
  assert.equal(await page.locator(".compaction-card").count(), 4);

  // Expand a large historical group and scroll back to its oldest calls.
  const largest = await page.evaluate(() => {
    const groups = [...document.querySelectorAll(".tool-group")].filter(
      (e) => !e.hidden,
    );
    return groups
      .sort(
        (a, b) =>
          parseInt(b.querySelector(".group-count").textContent) -
          parseInt(a.querySelector(".group-count").textContent),
      )[0]
      .querySelector(".group-count").textContent;
  });
  const group = page
    .locator(".tool-group")
    .filter({ has: page.locator(".group-count", { hasText: largest }) })
    .first();
  await group.evaluate((el) => {
    el.open = true;
  });
  await page.waitForTimeout(80);
  assert((await group.locator(".tool-row").count()) <= 64);
  await group.locator(".tool-list").evaluate((el) => {
    el.scrollTop = 0;
    el.dispatchEvent(new Event("scroll"));
  });
  await group.locator(".tool-row").first().click();
  assert((await group.locator(".tool-row pre:not([hidden])").count()) >= 1);

  // Seeking removes future annotations and returns time-zero messages to an event.
  await page.evaluate(() => player.command("home"));
  assert.equal(await page.locator(".tool-row").count(), 0);
  assert.equal(await page.locator(".message:visible").count(), 0);
  assert.equal(await page.locator("#words .marked").count(), 0);
  await page.selectOption("#speed", "rec");
  assert.equal(await page.evaluate(() => player.status.automaticSpeed), true);
  await page.selectOption("#speed", "32");
  assert.equal(await page.evaluate(() => player.status.speed), 32);
  await page.selectOption("#speed", "rec");

  // Geometry/glyph effects and note animation still use the original presentation.
  const noteAt = await page.evaluate(() => {
    const e = player.bundle.events.find(
      (e) =>
        e.kind === "begin" &&
        e.tool === "note" &&
        e.motion &&
        !e.motion.floating,
    );
    return { time: e.time, end: e.endTime };
  });
  await page.evaluate((at) => player.seek((at.time + at.end) / 2), noteAt);
  assert.equal(
    await page.evaluate(() => player.status.motion.key !== undefined),
    true,
  );
  await fs.mkdir(artifacts, { recursive: true });
  await page.screenshot({ path: path.join(artifacts, "note.png") });
  await page.evaluate(() => {
    player.seek(player.bundle.events.find((e) => e.state === 2768).time);
  });
  await page.screenshot({ path: path.join(artifacts, "dense-page.png") });

  assert.deepEqual(errors, []);
  console.log(
    "Browser: message animation/pause, seeking, progress, bounded rows, history/details, rec speeds and note passed",
  );
} finally {
  await browser.close();
}
