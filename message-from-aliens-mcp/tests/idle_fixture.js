const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({
    rpc: {exports: {}},
    init: () => ({methodFromName: (_, name) => name}),
    Memory: {allocUtf8String: value => value},
    klass: name => name,
    drawObject: () => ({isNull: () => false}),
    instanceText: () => 'money enlarge',
    stringArgument: value => value,
    Date: {now: () => 1000000000000},
});
vm.runInContext(fs.readFileSync(require('node:path').join(require('node:path').dirname(process.argv[2]), 'protocol.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);
vm.runInContext(`
    let flags, money, calls, fail;
    function reset() {
        flags = {idlestarttime: Date.now(), idlecurrenttime: Date.now(), idlefactory: 0};
        money = 10; calls = []; fail = false;
    }
    reset();
    idleFlag = (name, value) => value === undefined ? (flags[name] ?? -1) : (flags[name] = value);
    idleMoney = value => value === undefined ? money : (money = value);
    checkedInvoke = method => {
        calls.push(method);
        if (method === 'IdleTimePass') {
            const ticks = Math.floor((Date.now() - flags.idlecurrenttime) / 640 * (flags.idlefactory + 1));
            money += ticks * 2;
            flags.idlecurrenttime += ticks * 640 / (flags.idlefactory + 1);
            if (fail && calls.filter(x => x === method).length === 2) throw new Error('Native calculation failed');
        }
    };
`, context);
assert.equal(vm.runInContext('advanceTime(1.28).seconds', context), 1.28);
assert.equal(vm.runInContext('flags.idlestarttime', context), 1000000000000 - 1280);
assert.equal(vm.runInContext('flags.idlecurrenttime', context), 1000000000000);
assert.equal(vm.runInContext('money', context), 14);
assert.equal(vm.runInContext('Date.now()', context), 1000000000000);
assert.equal(vm.runInContext('JSON.stringify(calls)', context), '["IdleTimePass","IdleTimePass","UpdateText"]');

vm.runInContext('reset(); fail = true;', context);
assert.throws(() => vm.runInContext('advanceTime(1.28)', context), /Native calculation failed/);
assert.equal(vm.runInContext('money', context), 10);
assert.equal(vm.runInContext('flags.idlestarttime', context), 1000000000000);
assert.equal(vm.runInContext('flags.idlecurrenttime', context), 1000000000000);

vm.runInContext('reset();', context);
for (const value of ['-1', '0', 'true', 'NaN', 'Infinity', '86401', '0.0001']) {
    assert.throws(() => vm.runInContext(`advanceTime(${value})`, context), /INVALID_SECONDS/);
}
assert.equal(vm.runInContext('calls.length', context), 0);
vm.runInContext('flags.idlefactory = 2147483647;', context);
assert.throws(() => vm.runInContext('advanceTime(100)', context), /TIMER_CAPACITY/);
assert.equal(vm.runInContext('calls.length', context), 0);
vm.runInContext('reset(); delete flags.idlecurrenttime;', context);
assert.throws(() => vm.runInContext('advanceTime(100)', context), /TIMER_NOT_INITIALIZED/);
assert.equal(vm.runInContext('calls.length', context), 0);
vm.runInContext("reset(); instanceText = () => 'another-page';", context);
assert.throws(() => vm.runInContext('advanceTime(100)', context), /WAIT_UNAVAILABLE/);
assert.equal(vm.runInContext('calls.length', context), 0);
