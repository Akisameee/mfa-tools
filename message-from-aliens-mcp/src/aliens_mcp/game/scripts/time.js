/* Only the incremental minigame's saved timestamps are shifted. */
'use strict';

function idleValue(kind, name, value) {
    const a = init(), write = value !== undefined;
    const method = a.methodFromName(klass('Global'),
        Memory.allocUtf8String((write ? 'Set' : 'Get') + (kind === 'double' ? 'DFlag' : 'Flag')), 2);
    const number = Memory.alloc(8), args = Memory.alloc(PTR_SIZE * 2);
    if (kind === 'double') number.writeDouble(write ? value : -1);
    else number.writeS64(write ? value : -1);
    args.writePointer(stringArgument(name).readPointer());
    args.add(PTR_SIZE).writePointer(number);
    const result = checkedInvoke(method, NIL, args);
    if (!write) {
        const unboxed = a.unbox(result);
        return kind === 'double' ? unboxed.readDouble() : Number(unboxed.readS64().toString());
    }
}

function idleFlag(name, value) { return idleValue('long', name, value); }
function idleMoney(value) { return idleValue('double', 'idlemoney', value); }

function advanceTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0.001 || seconds > 86400) {
        throw gameError('INVALID_SECONDS');
    }
    const draw = drawObject(), cls = klass('Draw');
    if (draw.isNull() || instanceText(draw, cls, 'current_page') !== 'money enlarge') {
        throw gameError('WAIT_UNAVAILABLE');
    }
    const pass = init().methodFromName(cls, Memory.allocUtf8String('IdleTimePass'), 0);
    const refresh = init().methodFromName(cls, Memory.allocUtf8String('UpdateText'), 1);
    const millis = Math.round(seconds * 1000);
    const initialStart = idleFlag('idlestarttime'), initialCurrent = idleFlag('idlecurrenttime');
    const factory = idleFlag('idlefactory');
    if (![initialStart, initialCurrent, factory].every(Number.isSafeInteger) ||
        initialStart < 0 || initialCurrent < 0 || factory < 0) {
        throw gameError('TIMER_NOT_INITIALIZED');
    }
    // Native IdleTimePass batches ticks with Mathf.FloorToInt (signed int32).
    const ticks = (Math.max(0, Date.now() - initialCurrent) + millis) / 640 * (factory + 1);
    if (ticks >= 2147483647) throw gameError('TIMER_CAPACITY');
    // Settle genuinely elapsed time first, then snapshot the state we may undo.
    checkedInvoke(pass, draw);
    const start = idleFlag('idlestarttime'), current = idleFlag('idlecurrenttime');
    const money = idleMoney();
    try {
        idleFlag('idlestarttime', start - millis);
        idleFlag('idlecurrenttime', current - millis);
        checkedInvoke(pass, draw);
        checkedInvoke(refresh, draw, stringArgument('a'));
    } catch (error) {
        try {
            idleFlag('idlestarttime', start);
            idleFlag('idlecurrenttime', current);
            idleMoney(money);
            checkedInvoke(refresh, draw, stringArgument('a'));
        } catch (restoreError) {
            throw gameError('TIME_RESTORE_FAILED');
        }
        throw error;
    }
    return {ok: true, seconds: millis / 1000};
}

rpc.exports.wait = function (seconds, thread, window) {
    return queueInput({kind: 'wait', seconds}, thread, window);
};

operations.wait = {
    enter(request) { request.result = advanceTime(request.seconds); },
    leave(request, finish) {
        try {
            // Draw.Update has now refreshed the page and checked the
            // native completion condition. Persist that final state.
            const save = init().methodFromName(klass('Global'), Memory.allocUtf8String('SaveGame'), 0);
            checkedInvoke(save, NIL);
            finish(request);
        } catch (error) {
            finish(request, gameError('TIME_SAVE_FAILED', {advanced: true, seconds: request.seconds, cause: error.code || 'INTERNAL_ERROR'}, error));
        }

    },
};
