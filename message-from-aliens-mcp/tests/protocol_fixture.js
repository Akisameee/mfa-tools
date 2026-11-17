// The real RPC wrapper must preserve effectful failures without exposing internals.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = vm.createContext({rpc: {exports: {}}, Promise});
const load = name => vm.runInContext(fs.readFileSync(path.join(process.argv[2], name), 'utf8'), context);
load('protocol.js');
load('time.js');
load('annotations.js');
vm.runInContext(`
    let failure = null, saves = 0;
    init = () => ({methodFromName: () => 'SaveGame'});
    klass = () => 'Global';
    Memory = {allocUtf8String: value => value};
    NIL = null;
    checkedInvoke = () => { saves++; throw gameError('UNITY_REJECTED'); };
    operations.wait.leave({seconds: 60}, (_, error) => { failure = error; });
`, context);
assert.equal(vm.runInContext('saves', context), 1);
assert.equal(vm.runInContext('failure.code', context), 'TIME_SAVE_FAILED');
assert.equal(vm.runInContext('failure.details.advanced', context), true);
assert.equal(vm.runInContext('failure.details.seconds', context), 60);

vm.runInContext(`
    api = null;
    drawSnapshot = () => { throw gameError('DRAW_NOT_FOUND'); };
    glyphWords = () => ['opaque'];
    glyphPaths = () => { throw new Error('private source details'); };
    rpc.exports.wait = () => Promise.reject(failure);
`, context);
load('exports.js');
assert.equal(context.rpc.exports.ping(), true);
assert.equal(context.rpc.exports.snapshot().error.code, 'DRAW_NOT_FOUND');
assert.equal(context.rpc.exports.glyphPaths('token').error.code, 'INTERNAL_ERROR');
assert.deepEqual(Array.from(context.rpc.exports.glyphWords()), ['opaque']);
(async () => {
    const result = await context.rpc.exports.wait(60);
    assert.equal(result.error.code, 'TIME_SAVE_FAILED');
    assert.equal(result.error.details.advanced, true);
    assert.equal(result.error.details.seconds, 60);
})().catch(error => { console.error(error); process.exitCode = 1; });
