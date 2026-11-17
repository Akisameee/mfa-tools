// Exercise the production commit/rollback flow with managed calls simulated.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const cell = {word: 'donor', isNull: () => false};
const input = {isNull: () => false};
const context = vm.createContext({
    rpc: {exports: {}},
    init: () => ({
        objectGetClass: () => 'AlienCharacter',
        methodFromName: (_, name) => name,
        unbox: value => value,
    }),
    Memory: {allocUtf8String: value => value},
    instance: () => input,
    instanceInt: () => 49,
    instanceText: object => object.word,
    getter: () => ({readU8: () => 0}),
});
vm.runInContext(fs.readFileSync(require('node:path').join(require('node:path').dirname(process.argv[2]), 'protocol.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);
vm.runInContext(`
    let stored = 'old', fail = false, calls = [];
    annotationCells = () => [testCell];
    readAnnotation = () => stored;
    setAnnotationWord = (cell, word) => { cell.word = word; };
    stringArgument = value => value;
    checkedInvoke = (method, cell, value) => {
        calls.push([cell.word, value]);
        stored = value;
        if (fail && value === 'new') throw new Error('Save failed');
    };
`, Object.assign(context, {testCell: cell}));

// Off-page target uses native EndEdit with the requested identity, then restores
// the donor component before returning to the normal game loop.
assert.equal(vm.runInContext("editNote('off-page', 'new').ok", context), true);
assert.equal(cell.word, 'donor');
assert.equal(vm.runInContext('stored', context), 'new');
assert.equal(vm.runInContext("JSON.stringify(calls)", context), '[["off-page","new"]]');

vm.runInContext("stored = 'old'; calls = []; fail = true;", context);
assert.throws(() => vm.runInContext("editNote('off-page', 'new')", context), /Save failed/);
assert.equal(cell.word, 'donor');
assert.equal(vm.runInContext('stored', context), 'old');
assert.equal(vm.runInContext('JSON.stringify(calls)', context),
    '[["off-page","new"],["off-page","old"]]');

vm.runInContext("calls = []; fail = false;", context);
assert.equal(vm.runInContext("editNote('donor', '').text", context), '');
assert.equal(cell.word, 'donor');
assert.throws(() => vm.runInContext("editNote('off-page', 'x'.repeat(50))", context), /ANNOTATION_TOO_LONG/);
assert.equal(vm.runInContext('calls.length', context), 1);

// Existing focus must not be stolen for a background annotation operation.
vm.runInContext('getter = () => ({readU8: () => 1});', context);
assert.throws(() => vm.runInContext("editNote('off-page', 'new')", context), /ANNOTATION_FIELD_UNAVAILABLE/);
assert.equal(cell.word, 'donor');
