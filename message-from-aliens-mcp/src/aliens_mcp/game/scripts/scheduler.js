/* Main-thread scheduling and background-setting restoration. */
'use strict';
const inputState = {thread: null, request: null, inside: false, listeners: []};

function installInput(thread, window) {
    if (inputState.thread !== null) {
        if (inputState.thread !== thread) throw gameError('THREAD_CHANGED');
        return;
    }
    const a = init();
    const resolve = value => a.resolveIcall(value.readUtf8String());
    const icall = (name, result, args) => {
        const address = resolve(Memory.allocUtf8String(name));
        if (address.isNull()) throw gameError('NATIVE_BINDING_UNAVAILABLE');
        return new NativeFunction(address, result, args);
    };
    const getBackground = icall('UnityEngine.Application::get_runInBackground', 'bool', []);
    const setBackground = icall('UnityEngine.Application::set_runInBackground', 'void', ['bool']);
    const user32 = Process.getModuleByName('user32.dll');
    const wake = new NativeFunction(user32.getExportByName('PostMessageW'), 'bool',
                                   ['pointer', 'uint32', 'size_t', 'ssize_t']);
    inputState.wake = () => wake(ptr(window), 0, 0, 0); // WM_NULL: no focus or mouse changes.

    // Only called on the main thread. Restore the player's background setting
    // before resolving, including when projection or input processing fails.
    function finish(request, error) {
        try {
            if (request.background !== undefined) setBackground(request.background);
        } catch (e) {
            error = gameError('BACKGROUND_RESTORE_FAILED');
        }
        clearTimeout(request.timer);
        inputState.inside = false;
        inputState.request = null;
        if (request.cancelled) return;
        if (request.urlError) error = gameError('URL_DECODE_FAILED');
        if (error) request.reject(error);
        else {
            const result = request.urls && request.urls.length ? {
                ok: true, event: 'external_url', urls: request.urls, opened: false,
            } : request.result || {ok: true, row: request.row, col: request.col, type: request.type};
            if (request.target) result.target = request.target;
            request.resolve(result);
        }
    }

    const installed = [];
    try {
        installEffects(a, thread, resolve, installed);
        const update = a.methodFromName(klass('Draw'), Memory.allocUtf8String('Update'), 0);
        if (update.isNull()) throw gameError('UPDATE_UNAVAILABLE');
        installClickHooks(a, thread, installed);
        installed.push(Interceptor.attach(a.methodAddress(update), {
            onEnter() {
                const request = inputState.request;
                if (this.threadId !== thread || !request || !request.phase || request.cancelled) return;
                this.request = request;
                try {
                    operations[request.kind].enter(request);
                } catch (error) {
                    this.request = null;
                    finish(request, error);
                }
            },
            onLeave() {
                const request = this.request;
                if (!request) return;
                inputState.inside = false;
                try { operations[request.kind].leave(request, finish); }
                catch (error) { finish(request, error); }
            },
        }));
        // A paused player still pumps its window messages. This hook enables the
        // normal player loop; it never invokes Update manually or changes focus.
        const resume = {
            onLeave() {
                const request = inputState.request;
                if (this.threadId !== thread || !request) return;
                if (request.cancelled) { finish(request); return; }
                if (request.phase) return;
                try {
                    request.background = getBackground();
                    setBackground(1);
                    request.phase = 1;
                } catch (error) {
                    finish(request, error);
                }
            },
        };
        for (const name of ['PeekMessageW', 'DispatchMessageW',
                            'MsgWaitForMultipleObjects', 'MsgWaitForMultipleObjectsEx']) {
            installed.push(Interceptor.attach(user32.getExportByName(name), resume));
        }
    } catch (error) {
        for (const listener of installed) listener.detach();
        throw error;
    }
    inputState.listeners = installed;
    inputState.thread = thread;
    Interceptor.flush();
}

function queueInput(request, thread, window) {
    const {row, col} = request;
    if (request.kind === 'click' &&
        (!Number.isInteger(row) || row < 0 || row >= ROWS ||
        !Number.isInteger(col) || col < 0 || col >= COLS)) {
        throw gameError('INVALID_GRID_POSITION');
    }
    if (!Number.isInteger(thread) || thread <= 0) throw gameError('THREAD_UNAVAILABLE');
    installInput(thread, window);
    if (inputState.request) throw gameError('INPUT_BUSY');
    return new Promise((resolve, reject) => {
        Object.assign(request, {phase: 0, reads: 0, positions: 0, resolve, reject});
        request.timer = setTimeout(() => {
            request.cancelled = true;
            reject(gameError('INPUT_TIMEOUT'));
            inputState.wake();
        }, 5000);
        inputState.request = request;
        Interceptor.flush();
        if (!inputState.wake()) {
            clearTimeout(request.timer);
            inputState.request = null;
            reject(gameError('WAKE_FAILED'));
        } else {
            // Cover a wait that was already in flight when the hooks were installed.
            setTimeout(() => { if (inputState.request === request) inputState.wake(); }, 20);
        }
    });
}
