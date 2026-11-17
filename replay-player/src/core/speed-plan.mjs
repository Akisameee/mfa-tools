import { eventTime } from "./timeline.mjs";
import { TempoMap } from "./tempo.mjs";
import { messageDuration } from "./motion.mjs";
import { messageText } from "./conversation.mjs";

function timestamp(value) {
  const match = /^(\d+):([0-5]\d):([0-5]\d)(?:\.(\d{1,3}))?$/.exec(value);
  if (!match) throw Error(`Invalid plan timestamp: ${value}`);
  return (
    (+match[1] * 3600 + +match[2] * 60 + +match[3]) * 1000 +
    Number((match[4] || "").padEnd(3, "0"))
  );
}

export function resolveSpeedPlan(config, bundle) {
  if (config.recording !== bundle.recording)
    throw Error(
      `切速配置适用于 ${config.recording}，当前录制为 ${bundle.recording}`,
    );
  const validSpeed = (value) => Number.isFinite(value) && value > 0;
  if (!validSpeed(config.defaultSpeed))
    throw Error("Invalid default plan speed");
  const changes = [],
    duration = eventTime(bundle.events.at(-1));
  for (const change of config.changes) {
    if (!validSpeed(change.speed)) throw Error("Invalid plan speed");
    let at;
    if (change.afterMessage) {
      const selector = change.afterMessage;
      const messages = bundle.events.filter(
        (event) =>
          event.kind === "message" &&
          event.role === selector.role &&
          (selector.text === undefined ||
            event.text.trim() === selector.text.trim()),
      );
      const occurrence = selector.occurrence ?? 1;
      if (
        !Number.isInteger(occurrence) ||
        occurrence < 1 ||
        !messages[occurrence - 1] ||
        (selector.occurrence === undefined && messages.length !== 1)
      )
        throw Error(`切速配置无法唯一匹配消息：${JSON.stringify(selector)}`);
      const event = messages[occurrence - 1];
      at = eventTime(event);
      if (change.afterReveal) {
        const map = new TempoMap(bundle.events, config.defaultSpeed, changes);
        at = map.toSource(map.toView(at) + messageDuration(messageText(event)));
      }
    } else at = timestamp(change.at);
    if (at < 0 || at > duration || (changes.length && at <= changes.at(-1).at))
      throw Error("切速配置必须按时间递增，且位于录制范围内");
    changes.push({ at, speed: change.speed });
  }
  return {
    name: config.name || "rec",
    defaultSpeed: config.defaultSpeed,
    changes,
  };
}
