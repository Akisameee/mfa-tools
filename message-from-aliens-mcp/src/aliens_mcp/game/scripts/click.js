function gridCellAt(row, col) {
    const draw = drawObject();
    if (draw.isNull()) throw gameError('PAGE_UNAVAILABLE');
    const grid = instance(draw, klass('Draw'), 'alien_slots');
    const cell = arrayElements(grid)[col * ROWS + ROWS - 1 - row];
    if (!cell || cell.isNull()) throw gameError('CELL_UNAVAILABLE');
    // Grid objects are reused: a nonempty word may belong to an earlier page.
    const block = Object.keys(BLOCK_FIELDS).find(name =>
        listItems(instance(draw, klass('Draw'), BLOCK_FIELDS[name])).some(item => item.equals(cell)));
    const index = col * ROWS + ROWS - 1 - row;
    const input = arrayElements(instance(draw, klass('Draw'), 'txt_slots'))[index];
    return {draw, cell, input, block};
}

function cellPixel(row, col, request) {
    const a = init(), {draw, cell, input, block} = gridCellAt(row, col);
    // Project the actual character, including letterboxing and camera scaling.
    const position = transformPosition(cell);
    if (!position) throw gameError('POSITION_UNAVAILABLE');
    const cameraClass = classInImage(imageByName('UnityEngine.CoreModule.dll'), 'Camera', 'UnityEngine');
    const camera = checkedInvoke(a.methodFromName(cameraClass, Memory.allocUtf8String('get_main'), 0), NIL);
    if (camera.isNull()) throw gameError('CAMERA_UNAVAILABLE');
    const method = a.methodFromName(cameraClass, Memory.allocUtf8String('WorldToScreenPoint'), 1);
    const point = Memory.alloc(12);
    point.writeFloat(position.x);
    point.add(4).writeFloat(position.y);
    point.add(8).writeFloat(position.z);
    const args = Memory.alloc(PTR_SIZE);
    args.writePointer(point);
    const pixel = vector3(checkedInvoke(method, camera, args));
    if (!pixel || !Number.isFinite(pixel.x) || !Number.isFinite(pixel.y) || pixel.z <= 0) {
        throw gameError('OUTSIDE_CAMERA');
    }
    // Capture the current cell on the game thread before Update handles input
    // or navigation reuses the grid objects for another page.
    const cellClass = a.objectGetClass(cell);
    const word = block === undefined ? null : instanceText(cell, cellClass, 'alien_txt');
    const styles = renderedStyleContext(draw);
    const boxed = styles.frames.some(([top, left, bottom, right]) =>
        top === row && bottom === row && left === col && right === col);
    const frame = frameAt(row, col, styles.frames);
    request.target = word ? {
        word,
        note: input && !input.isNull() ? text(getter(input, 'get_text')) : null,
        ...renderedCellStyle(draw, cell, cellClass, styles),
        boxed, ...(frame ? {frame} : {}),
    } : {empty: true, boxed, ...(frame ? {frame} : {})};
    send({event: 'click_target', request_id: request.id, target: request.target});
    return pixel;
}


function installClickHooks(a, thread, installed) {
    const input = classInImage(imageByName('UnityEngine.InputLegacyModule.dll'), 'Input', 'UnityEngine');
    const entry = (name, argc) => {
        const info = a.methodFromName(input, Memory.allocUtf8String(name), argc);
        if (info.isNull()) throw gameError('INPUT_BINDING_UNAVAILABLE');
        const address = a.runtime === 'mono' ? a.internalCall(info) : a.methodAddress(info);
        if (address.isNull()) throw gameError('INPUT_BINDING_UNAVAILABLE');
        return address;
    };
    for (const name of ['GetMouseButtonDown', 'GetMouseButton', 'GetMouseButtonUp']) {
        installed.push(Interceptor.attach(entry(name, 1), {
            onEnter(args) { this.button = args[0].toInt32(); },
            onLeave(result) {
                const request = inputState.request;
                if (!inputState.inside || this.threadId !== thread || !request || request.cancelled) return;
                const pressed = name === 'GetMouseButtonUp' ? request.phase === 2 : request.phase === 1;
                result.replace(this.button === request.button && pressed ? 1 : 0);
                if (name === 'GetMouseButtonDown' && this.button === request.button && pressed) request.reads++;
            },
        }));
    }
    // Mono's injected getter writes an out Vector3; IL2CPP's getter uses a
    // Windows x64 hidden return buffer. Both put that buffer in argument 0.
    const mousePosition = a.runtime === 'mono' ? entry('get_mousePosition_Injected', 1) :
                          entry('get_mousePosition', 0);
    installed.push(Interceptor.attach(mousePosition, {
        onEnter(args) { this.buffer = args[0]; },
        onLeave() {
            const request = inputState.request;
            if (!inputState.inside || this.threadId !== thread || !request || request.cancelled) return;
            this.buffer.writeFloat(request.pixel.x);
            this.buffer.add(4).writeFloat(request.pixel.y);
            this.buffer.add(8).writeFloat(0);
            request.positions++;
        },
    }));

}
rpc.exports.click = function (row, col, type, thread, window, id) {
    if (type !== 'left' && type !== 'right') throw gameError('INVALID_BUTTON');
    return queueInput({kind: 'click', row, col, type, id, button: type === 'left' ? 0 : 1}, thread, window);
};


operations.click = {
    enter(request) {
        if (request.phase === 1) request.pixel = cellPixel(request.row, request.col, request);
        inputState.inside = true;
    },
    leave(request, finish) {
        if (request.phase === 1) request.phase = 2;
        else finish(request, request.reads && request.positions ? null : gameError('CLICK_NOT_READ'));
    },
};
