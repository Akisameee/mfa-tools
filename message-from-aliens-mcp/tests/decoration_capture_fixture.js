// Exercise actual snapshot and pre-click capture without sending native input.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const pointer = id => ({isNull: () => id === 0, toString: () => String(id),
    equals: other => other && other.toString() === String(id)});
const nil = pointer(0), draw = pointer(1), cell = pointer(2);
const memory = {writeFloat() {}, writePointer() {}};
memory.add = () => memory;
const context = vm.createContext({
    ptr: pointer, Process: {pointerSize: 8}, rpc: {exports: {}},
    imageByName: () => draw,
    Memory: {allocUtf8String: value => value, alloc: () => memory},
    send() {},
});
for (const name of ['protocol.js', 'state.js', 'decorations.js', 'managed.js', 'click.js']) {
    vm.runInContext(fs.readFileSync(path.join(process.argv[2], name), 'utf8'), context);
}
Object.assign(context, {testDraw: draw, testCell: cell, testNil: nil});
vm.runInContext(`
    let frames = [], underlined = true, occupied = true;
    const grid = Array(24 * 9).fill(testNil);
    grid[13 * 9 + 6] = testCell; // row 2, column 13
    init = () => ({objectGetClass: () => 'class', methodFromName: (_, name) => name});
    klass = name => name;
    drawObject = () => testDraw;
    instance = (object, cls, name) => {
        if (name === 'slots') throw new Error('Decoration capture must not read Draw.slots');
        if (name === 'alien_slots') return grid;
        if (name === 'txt_slots') return [];
        if (name === 'alien_txt') return 'word';
        if (name === 'alien_right_text_down') return occupied ? [testCell] : [];
        return [];
    };
    instanceText = (object, cls, name) => name === 'current_page' ? 'page' : 'word';
    text = value => value;
    arrayElements = value => value;
    listItems = value => value;
    geometry = () => ({});
    renderedStyleContext = () => ({frames});
    renderedCellStyle = () => ({underlined, dim: false, highlight: false});
    transformPosition = () => ({x: 1, y: 2, z: 0});
    classInImage = () => 'Camera';
    checkedInvoke = () => testDraw;
    vector3 = () => ({x: 100, y: 200, z: 1});
    function target() { const request = {id: 1}; cellPixel(2, 13, request); return request.target; }
`, context);
const read = code => JSON.parse(vm.runInContext(`JSON.stringify(${code})`, context));

// Underlined interaction cells must not acquire a box from slot membership.
assert.deepEqual(read('drawSnapshot().boxes'), []);
assert.equal(read('drawSnapshot().cells[0]').underlined, true);
assert.equal(read('target()').boxed, false);
assert.equal(read('target()').underlined, true);

// A real single-cell rectangle remains boxed in both outputs.
vm.runInContext('frames = [[2,13,2,13]]; underlined = false;', context);
assert.deepEqual(read('drawSnapshot().boxes'), [[2, 13]]);
assert.equal(read('target()').boxed, true);
assert.equal(read('target()').underlined, false);

// Multirow cards preserve grouping without inventing separate single-cell boxes.
vm.runInContext('frames = [[2,13,3,13]];', context);
assert.deepEqual(read('drawSnapshot().boxes'), []);
assert.deepEqual(read('drawSnapshot().frames'), [[2, 13, 3, 13]]);
assert.equal(read('target()').boxed, false);
assert.deepEqual(read('target()').frame, {top: true, bottom: false, left: true, right: true});

// Empty cells also retain real outlines, independently of interaction metadata.
vm.runInContext('frames = [[2,13,2,13]]; occupied = false;', context);
assert.deepEqual(read('target()'), {empty: true, boxed: true});
