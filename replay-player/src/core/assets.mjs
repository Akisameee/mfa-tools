import { resolveSpeedPlan } from "./speed-plan.mjs";

export async function loadReplay() {
  const response = await fetch("data/replay.json");
  if (!response.ok) throw Error("请先运行 prepare.py 生成录制数据");
  const bundle = await response.json();
  const grading = await fetch(bundle.gradingFile || "data/grading.json", {
    cache: "no-store",
  });
  if (grading.ok) {
    const separate = await grading.json();
    bundle.grading =
      separate.recording === bundle.recording &&
      separate.assetsFingerprint === bundle.glyphs.fingerprint
        ? separate.grading
        : null;
  } else if (grading.status !== 404)
    throw Error(`读取评分失败：${grading.status}`);
  const planResponse = await fetch("recording-plan.json", {
    cache: "no-store",
  });
  if (!planResponse.ok) throw Error(`读取切速配置失败：${planResponse.status}`);
  const plan = resolveSpeedPlan(await planResponse.json(), bundle);
  const hashGlyphs = new Map(),
    callResults = new Map();
  for (const snapshot of bundle.states)
    for (const [key, hash] of Object.entries(snapshot.ids || {}))
      hashGlyphs.set(hash, key);
  for (const event of bundle.events) {
    if (event.kind === "end") {
      callResults.set(event.call, event);
      if (event.character?.hash)
        hashGlyphs.set(event.character.hash, event.character.key);
    }
    if (event.kind === "begin" && event.args?.hash)
      hashGlyphs.set(
        event.args.hash,
        event.motion?.key ||
          event.focus?.key ||
          hashGlyphs.get(event.args.hash),
      );
  }
  const atlas = new Image();
  atlas.src = bundle.glyphs.atlas;
  await Promise.all([
    atlas.decode(),
    document.fonts.load('16px "Replay PT Sans"'),
    document.fonts.load('16px "Replay FZ Hei"'),
  ]);
  return { bundle, plan, atlas, hashGlyphs, callResults };
}
