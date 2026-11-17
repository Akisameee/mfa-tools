/* Read the styles the game actually rendered, without parsing menu conditions. */
'use strict';

function sameColor(first, second) {
    return !!first && !!second && first.length === second.length &&
           first.every((value, i) => Math.abs(value - second[i]) < 0.0001);
}

function underlineAt(position, lines) {
    if (!position) return false;
    // Draw.Write places underline segments 0.92 world units below glyph centers.
    return lines.some(([start, end]) =>
        Math.abs(start.y - end.y) < 0.001 && Math.abs(start.x - end.x) > 0.001 &&
        Math.abs(position.y - 0.92 - start.y) < 0.01 &&
        Math.abs(position.z - start.z) < 0.01 &&
        position.x >= Math.min(start.x, end.x) - 0.001 &&
        position.x <= Math.max(start.x, end.x) + 0.001);
}

function rectangleBounds(points) {
    if (points.length !== 5 || points.some(p => !p || ![p.x, p.y, p.z].every(Number.isFinite))) return null;
    const near = (a, b) => Math.abs(a - b) < 0.001;
    const first = points[0], last = points[4];
    if (!near(first.x, last.x) || !near(first.y, last.y)) return null;
    const xs = points.map(p => p.x), ys = points.map(p => p.y);
    const left = Math.min(...xs), right = Math.max(...xs);
    const bottom = Math.min(...ys), top = Math.max(...ys);
    if (right - left < 0.001 || top - bottom < 0.001) return null;
    const corners = new Set();
    for (let i = 0; i < 4; i++) {
        const p = points[i], next = points[i + 1];
        if (!near(p.z, first.z) || !near(next.z, first.z) ||
            !(near(p.x, next.x) !== near(p.y, next.y)) ||
            !(near(p.x, left) || near(p.x, right)) ||
            !(near(p.y, bottom) || near(p.y, top))) return null;
        corners.add((near(p.x, right) ? 'r' : 'l') + (near(p.y, top) ? 't' : 'b'));
    }
    return corners.size === 4 ? {left, right, bottom, top, z: first.z} : null;
}

function gridFrames(rectangles, positions) {
    const unique = new Map();
    for (const rect of rectangles) {
        const inside = positions.filter(p => Math.abs(p.z - rect.z) < 0.01 &&
            p.x > rect.left + 0.001 && p.x < rect.right - 0.001 &&
            p.y > rect.bottom + 0.001 && p.y < rect.top - 0.001);
        if (!inside.length) continue;
        const rows = inside.map(p => p.row), cols = inside.map(p => p.col);
        const frame = [Math.min(...rows), Math.min(...cols), Math.max(...rows), Math.max(...cols)];
        // Only publish complete rectangular grid regions, including empty slots.
        if (inside.length === (frame[2] - frame[0] + 1) * (frame[3] - frame[1] + 1)) {
            unique.set(frame.join(','), frame);
        }
    }
    return [...unique.values()].sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);
}

function frameAt(row, col, frames) {
    const matches = frames.filter(([top, left, bottom, right]) =>
        (top !== bottom || left !== right) && row >= top && row <= bottom && col >= left && col <= right);
    matches.sort((a, b) => (a[2] - a[0] + 1) * (a[3] - a[1] + 1) -
                           (b[2] - b[0] + 1) * (b[3] - b[1] + 1));
    if (!matches.length) return null;
    const [top, left, bottom, right] = matches[0];
    return {top: row === top, bottom: row === bottom, left: col === left, right: col === right};
}

function managedColor(object) {
    if (!object || object.isNull()) return null;
    const raw = init().unbox(object);
    return [0, 4, 8, 12].map(offset => raw.add(offset).readFloat());
}

function visibleRenderer(renderer) {
    const a = init(), enabled = getter(renderer, 'get_enabled');
    if (enabled.isNull() || !a.unbox(enabled).readU8()) return false;
    const object = getter(renderer, 'get_gameObject');
    if (object.isNull()) return false;
    const active = getter(object, 'get_activeInHierarchy');
    return !active.isNull() && !!a.unbox(active).readU8();
}

function renderedStyleContext(draw) {
    const a = init(), cls = klass('Draw'), lines = [], rectangles = [];
    const value = Memory.alloc(4), args = Memory.alloc(PTR_SIZE);
    args.writePointer(value);
    const colorMethod = a.methodFromName(cls, Memory.allocUtf8String('DefaultColor'), 1);
    value.writeS32(0);
    const normal = managedColor(checkedInvoke(colorMethod, draw, args));
    value.writeS32(3);
    const dim = managedColor(checkedInvoke(colorMethod, draw, args));
    for (const renderer of listItems(instance(draw, cls, 'selected'))) {
        if (renderer.isNull() || !visibleRenderer(renderer)) continue;
        const count = getter(renderer, 'get_positionCount');
        if (count.isNull()) continue;
        const size = a.unbox(count).readS32();
        if (size !== 2 && size !== 5) continue;
        const rendererClass = a.objectGetClass(renderer);
        const getPosition = a.methodFromName(rendererClass, Memory.allocUtf8String('GetPosition'), 1);
        const worldSpace = getter(renderer, 'get_useWorldSpace');
        const local = !worldSpace.isNull() && !a.unbox(worldSpace).readU8();
        const transform = local ? getter(renderer, 'get_transform') : NIL;
        const points = [];
        for (let index = 0; index < size; index++) {
            value.writeS32(index);
            let point = vector3(checkedInvoke(getPosition, renderer, args));
            if (local && point) {
                const vector = Memory.alloc(12), vectorArgs = Memory.alloc(PTR_SIZE);
                vector.writeFloat(point.x);
                vector.add(4).writeFloat(point.y);
                vector.add(8).writeFloat(point.z);
                vectorArgs.writePointer(vector);
                const method = a.methodFromName(a.objectGetClass(transform),
                    Memory.allocUtf8String('TransformPoint'), 1);
                point = vector3(checkedInvoke(method, transform, vectorArgs));
            }
            points.push(point);
        }
        if (size === 2 && points.every(Boolean)) lines.push(points);
        if (size === 5) {
            const rect = rectangleBounds(points);
            if (rect) rectangles.push(rect);
        }
    }
    const positions = [];
    if (rectangles.length) {
        arrayElements(instance(draw, cls, 'alien_slots')).forEach((cell, index) => {
            if (cell.isNull()) return;
            const sprite = instance(cell, a.objectGetClass(cell), 'sp');
            const position = sprite.isNull() ? null : transformPosition(sprite);
            if (position) positions.push({...position, row: ROWS - 1 - index % ROWS, col: Math.floor(index / ROWS)});
        });
    }
    return {lines, normal, dim, frames: gridFrames(rectangles, positions)};
}

function renderedCellStyle(draw, cell, cellClass, context) {
    const sprite = instance(cell, cellClass, 'sp');
    const color = sprite.isNull() ? null : managedColor(getter(sprite, 'get_color'));
    const position = sprite.isNull() ? null : transformPosition(sprite);
    return {
        underlined: underlineAt(position, context.lines),
        dim: !!color && !sameColor(context.normal, context.dim) && !!sameColor(color, context.dim),
        highlight: characterHighlighted(cell, cellClass),
    };
}
