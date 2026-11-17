// Rich-text pastes can leave Markdown escapes in public user messages.
// Clean only the display text; keep transcript events and ordinary backslashes.
export function messageText(event) {
  return event.role === "user"
    ? event.text.replace(/\\([`*_{}\[\]()#+\-.!|>~])/g, "$1")
    : event.text;
}
