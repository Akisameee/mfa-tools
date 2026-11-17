// Full history stays in data. Only the current scroll window owns DOM/canvases.
export class VirtualToolList {
  constructor(element, items, createRow, releaseRow) {
    Object.assign(this, { element, items, createRow, releaseRow });
    this.visible = 0;
    this.mounted = new Map();
    this.prefix = [0];
    for (const item of items)
      this.prefix.push(this.prefix.at(-1) + (item.key ? 31 : 28));
    this.top = document.createElement("div");
    this.bottom = document.createElement("div");
    this.top.className = this.bottom.className = "tool-spacer";
    element.addEventListener("scroll", () => this.render());
  }
  clear() {
    for (const item of this.mounted.values()) this.releaseRow(item);
    this.mounted.clear();
    this.element.replaceChildren();
    this.range = "";
    this.prefix = [0];
    for (const item of this.items) {
      item.expanded = false;
      this.prefix.push(this.prefix.at(-1) + (item.key ? 31 : 28));
    }
  }
  setVisible(count, follow = false) {
    this.visible = count;
    this.render(follow);
  }
  render(follow = false) {
    if (!this.visible) {
      this.clear();
      return;
    }
    const max = this.prefix[this.visible],
      y = follow ? max : this.element.scrollTop;
    let low = 0,
      high = this.visible;
    while (low < high) {
      const mid = (low + high) >>> 1;
      if (this.prefix[mid] < y) low = mid + 1;
      else high = mid;
    }
    const start = Math.max(0, Math.min(this.visible - 64, low - 20)),
      end = Math.min(this.visible, start + 64);
    const signature = `${start}:${end}:${this.visible}`;
    if (signature === this.range) return;
    this.range = signature;
    for (const [index, item] of this.mounted)
      if (index < start || index >= end) {
        this.releaseRow(item);
        this.mounted.delete(index);
      }
    const fragment = document.createDocumentFragment();
    this.top.style.height = `${this.prefix[start]}px`;
    this.bottom.style.height = `${max - this.prefix[end]}px`;
    fragment.append(this.top);
    for (let i = start; i < end; i++) {
      const item = this.items[i];
      if (!this.mounted.has(i)) {
        this.createRow(item);
        this.mounted.set(i, item);
      }
      fragment.append(item.el);
    }
    fragment.append(this.bottom);
    this.element.replaceChildren(fragment);
  }
  measure(item) {
    // Expanded details are a user action, not work repeated during playback.
    const index = this.items.indexOf(item),
      height = item.el.offsetHeight;
    const delta = height - (this.prefix[index + 1] - this.prefix[index]);
    for (let i = index + 1; i < this.prefix.length; i++)
      this.prefix[i] += delta;
    this.range = "";
    this.render();
  }
}
