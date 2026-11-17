/* Checked managed invocation and string arguments. */
function checkedInvoke(method, object, args) {
    if (method.isNull()) throw gameError('UNITY_METHOD_UNAVAILABLE');
    const exception = Memory.alloc(PTR_SIZE);
    exception.writePointer(NIL);
    const result = init().invoke(method, object, args || NIL, exception);
    if (!exception.readPointer().isNull()) throw gameError('UNITY_REJECTED');
    return result;
}

function stringArgument(value) {
    const argument = init().stringNewUtf16(Memory.allocUtf16String(value), value.length);
    const args = Memory.alloc(PTR_SIZE);
    args.writePointer(argument);
    return args;
}
