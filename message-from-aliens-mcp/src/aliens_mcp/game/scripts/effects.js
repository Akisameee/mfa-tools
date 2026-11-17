/* Observe exits and intercept external navigation during injected clicks. */
function installEffects(a, thread, resolve, installed) {
    // Unity 6 marshals OpenURL's string through a ManagedSpanWrapper. Replace
    // the actual native binding as well as the managed entry: IL2CPP callers
    // can inline the latter. Decode failures still block external navigation.
    const replaceUrl = (address, decode, signature) => {
        if (address.isNull()) throw gameError('URL_INTERCEPT_UNAVAILABLE');
        const original = new NativeFunction(address, 'void', signature);
        const replacement = new NativeCallback(function (value, method) {
            const request = inputState.request;
            if (Process.getCurrentThreadId() === thread && request &&
                request.kind === 'click' && request.phase) {
                try {
                    const url = decode(value);
                    if (url === null) throw gameError('URL_DECODE_FAILED');
                    if (!request.urls) request.urls = [];
                    if (!request.urls.includes(url)) request.urls.push(url);
                } catch (error) { request.urlError = true; }
                return;
            }
            // Calls outside an injected click keep their normal behaviour.
            if (signature.length === 1) original(value);
            else original(value, method);
        }, 'void', signature);
        Interceptor.replace(address, replacement);
        installed.push({detach() { Interceptor.revert(address); }});
    };
    const urlBinding = resolve(Memory.allocUtf8String(
        'UnityEngine.Application::OpenURL_Injected(UnityEngine.Bindings.ManagedSpanWrapper&)'));
    replaceUrl(urlBinding, value => {
        const length = value.add(PTR_SIZE).readS32();
        if (length < 0 || length > 200000) throw gameError('URL_DECODE_FAILED');
        return length ? value.readPointer().readUtf16String(length) : '';
    }, ['pointer']);
    // Observe the game's own exit call during this injected click. A lost
    // Frida connection alone does not prove that a click successfully quit.
    const application = classInImage(imageByName('UnityEngine.CoreModule.dll'), 'Application', 'UnityEngine');
    const openUrl = a.methodFromName(application, Memory.allocUtf8String('OpenURL'), 1);
    if (!openUrl.isNull() && !a.methodAddress(openUrl).isNull()) {
        replaceUrl(a.methodAddress(openUrl), text,
                   a.runtime === 'mono' ? ['pointer'] : ['pointer', 'pointer']);
    }
    const quitHooks = new Set();
    const observeQuit = address => {
        if (address.isNull() || quitHooks.has(address.toString())) return;
        quitHooks.add(address.toString());
        installed.push(Interceptor.attach(address, {
            onEnter() {
                const request = inputState.request;
                if (this.threadId === thread && inputState.inside && request &&
                    request.kind === 'click' && request.reads && request.positions && !request.quitObserved) {
                    request.quitObserved = true;
                    send({event: 'game_quit_requested', request_id: request.id});
                }
            },
        }));
    };
    // IL2CPP can inline both managed overloads; the native icall still runs.
    observeQuit(resolve(Memory.allocUtf8String('UnityEngine.Application::Quit(System.Int32)')));
    for (const argc of [0, 1]) {
        const quit = a.methodFromName(application, Memory.allocUtf8String('Quit'), argc);
        if (quit.isNull() || a.methodAddress(quit).isNull()) continue;
        observeQuit(a.methodAddress(quit));
    }

}
