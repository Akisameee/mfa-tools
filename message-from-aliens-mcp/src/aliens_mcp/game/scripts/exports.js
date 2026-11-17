Object.assign(rpc.exports, {
    ping() { return true; },
    runtime() { return init().runtime; },
    dispose() {
        if (api && api.threadDetach && api.attachedThread) {
            api.threadDetach(api.attachedThread);
            api.attachedThread = null;
        }
    },
    snapshot() { return drawSnapshot(); },
    glyphWords() { return glyphWords(); },
    glyphPaths(word) { return glyphPaths(word); },
});

// One boundary handles synchronous and asynchronous failures consistently.
for (const [name, handler] of Object.entries(rpc.exports)) {
    rpc.exports[name] = function (...args) {
        try {
            const result = handler(...args);
            return result && typeof result.then === 'function' ? result.catch(rpcFailure) : result;
        } catch (error) { return rpcFailure(error); }
    };
}
