import { knownNote } from "./timeline.mjs";

const statuses = { correct: "correct", partial: "close", wrong: "incorrect" };

export function annotationScore(grading, key, note) {
  if (!knownNote(note)) return { status: "unknown", reason: "" };
  // Preserve the existing ungraded playback mode until scores are attached.
  if (!grading) return { status: "correct", reason: "" };
  const annotation = note.normalize("NFC").trim();
  const score = grading.lookup?.[key]?.[annotation];
  return {
    status: statuses[score?.grade] || "pending",
    reason: score?.reason || "此版本标注尚未评分",
  };
}

export function annotationTooltip(grading, key, note) {
  const lines = [`译文：${knownNote(note) ? note : "未标注"}`];
  const reference = grading?.references?.[key];
  if (reference) {
    lines.push(`参考答案：${reference.english || reference.key}`);
    if (reference.numeric_value !== undefined)
      lines.push(`参考数值：${reference.numeric_value}`);
    if (reference.dictionary_text)
      lines.push(`游戏字典原文：\n${reference.dictionary_text}`);
  } else if (grading) lines.push("参考答案：暂无资料");
  if (grading && knownNote(note)) {
    const { status, reason } = annotationScore(grading, key, note);
    const label = {
      correct: "正确",
      close: "接近",
      incorrect: "错误",
      pending: "待评分",
    }[status];
    lines.push(`评分：${label}`);
    if (reason) lines.push(`评分理由：${reason}`);
  }
  return lines.join("\n");
}
