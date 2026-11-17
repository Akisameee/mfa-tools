/* Read game objects through the selected Mono or IL2CPP runtime. */
'use strict';

const NIL = ptr(0);
const PTR_SIZE = Process.pointerSize;

function classInImage(img, name, namespace) {
    return init().classFromName(img, Memory.allocUtf8String(namespace || ''),
                                Memory.allocUtf8String(name));
}

const IMAGE = imageByName('Assembly-CSharp.dll');
if (IMAGE.isNull()) throw gameError('ASSEMBLY_NOT_READY');
const classCache = new Map();

function klass(name) {
    if (classCache.has(name)) return classCache.get(name);
    const a = init();
    const found = a.classFromName(IMAGE, Memory.allocUtf8String(''), Memory.allocUtf8String(name));
    classCache.set(name, found);
    return found;
}

function fieldOf(klassPtr, name) {
    return init().fieldFromName(klassPtr, Memory.allocUtf8String(name));
}

/** Read a managed string through the runtime's public accessors. */
function text(pointer) {
    if (!pointer || pointer.isNull()) return null;
    const length = init().stringLength(pointer);
    if (length < 0 || length > 200000) return null;
    return init().stringChars(pointer).readUtf16String(length);
}

function instance(object, klassPtr, name) {
    const field = fieldOf(klassPtr, name);
    if (field.isNull()) return NIL;
    return init().fieldGetObject(field, object);
}

function instanceText(object, klassPtr, name) {
    return text(instance(object, klassPtr, name));
}

function instanceInt(object, klassPtr, name) {
    const boxed = instance(object, klassPtr, name);
    if (!boxed.isNull()) {
        return init().unbox(boxed).readS32();
    }
    const field = fieldOf(klassPtr, name);
    const raw = Memory.alloc(8);
    init().fieldStaticGet(field, raw);
    return raw.readS32();
}

function staticField(klassPtr, name) {
    const field = fieldOf(klassPtr, name);
    if (field.isNull()) return NIL;
    const holder = Memory.alloc(PTR_SIZE);
    init().fieldStaticGet(field, holder);
    return holder.readPointer();
}

function listItems(listPointer) {
    if (!listPointer || listPointer.isNull()) return [];
    const listClass = init().objectGetClass(listPointer);
    const items = instance(listPointer, listClass, '_items');
    const size = instanceInt(listPointer, listClass, '_size');
    if (items.isNull() || size <= 0) return [];
    const data = init().arrayData(items, PTR_SIZE);
    const out = [];
    for (let i = 0; i < size; i++) out.push(data.add(i * PTR_SIZE).readPointer());
    return out;
}

function arrayElements(arrayPointer) {
    if (!arrayPointer || arrayPointer.isNull()) return [];
    const length = init().arrayLength(arrayPointer);
    const data = init().arrayData(arrayPointer, PTR_SIZE);
    const out = [];
    for (let i = 0; i < length; i++) out.push(data.add(i * PTR_SIZE).readPointer());
    return out;
}

function drawObject() {
    const globalClass = klass('Global');
    const manager = staticField(globalClass, 'manager');
    return (!manager || manager.isNull()) ? NIL : manager;
}

/** Call a property getter (e.g. `get_transform`) and return the raw result object. */
function getter(object, methodName) {
    const objectClass = init().objectGetClass(object);
    const method = init().methodFromName(objectClass, Memory.allocUtf8String(methodName), 0);
    if (method.isNull()) return NIL;
    return checkedInvoke(method, object);
}

function vector3(object) {
    if (!object || object.isNull()) return null;
    const raw = init().unbox(object);
    return {x: raw.readFloat(), y: raw.add(4).readFloat(), z: raw.add(8).readFloat()};
}

function transformPosition(object) {
    const transform = getter(object, 'get_transform');
    if (transform.isNull()) return null;
    const position = getter(transform, 'get_position');
    return vector3(position);
}

/** Highlight(bool) toggles the background GameObject, not a word-key heuristic. */
function characterHighlighted(cell, cellClass) {
    const background = instance(cell, cellClass, 'background');
    if (background.isNull()) return false;
    const object = getter(background, 'get_gameObject');
    if (object.isNull()) return false;
    const active = getter(object, 'get_activeSelf');
    return !active.isNull() && !!init().unbox(active).readU8();
}

const ROWS = 9, COLS = 24;
const BLOCK_FIELDS = {
    left_title: 'alien_left_title', left_menu: 'alien_left_menu', left_text: 'alien_left_text',
    right_title: 'alien_right_title', right_menu: 'alien_right_menu',
    right_text_up: 'alien_right_text_up', right_text_down: 'alien_right_text_down',
    right_text_grid: 'alien_right_text_grid',
};

function drawSnapshot() {
    const draw = drawObject();
    if (draw.isNull()) throw gameError('DRAW_NOT_FOUND');
    const drawClass = klass('Draw');
    const page = instanceText(draw, drawClass, 'current_page');
    const grid = instance(draw, drawClass, 'alien_slots');
    const cellsRaw = arrayElements(grid);
    const indexOf = new Map();
    cellsRaw.forEach((pointer, index) => { if (!pointer.isNull()) indexOf.set(pointer.toString(), index); });
    const rows = ROWS;
    const cols = COLS;

    const inputs = arrayElements(instance(draw, drawClass, 'txt_slots'));
    const styles = renderedStyleContext(draw);

    const cells = [];
    for (const block of Object.keys(BLOCK_FIELDS)) {
        const list = instance(draw, drawClass, BLOCK_FIELDS[block]);
        for (const pointer of listItems(list)) {
            const index = indexOf.get(pointer.toString());
            if (index === undefined || index < 0) continue;
            const cellClass = init().objectGetClass(pointer);
            const word = text(instance(pointer, cellClass, 'alien_txt'));
            if (!word) continue;
            const gridRow = index % rows;
            cells.push({
                col: Math.floor(index / rows),
                row: rows - 1 - gridRow,
                block,
                word,
                note: inputs[index] && !inputs[index].isNull() ? text(getter(inputs[index], 'get_text')) : null,
                ...renderedCellStyle(draw, pointer, cellClass, styles),
            });
        }
    }

    // Only actual rendered rectangles are boxes; interaction slots may be underlined.
    const boxes = styles.frames.filter(([top, left, bottom, right]) => top === bottom && left === right)
        .map(([row, col]) => [row, col]);

    const result = {
        page,
        rows, cols,
        cells, boxes,
        frames: styles.frames,
        geometry: geometry(draw, drawClass),
    };
    if (page !== instanceText(draw, drawClass, 'current_page')) {
        throw gameError('PAGE_CHANGED');
    }
    return result;
}

/** Read a Vector2Int field (boxed value type: two int32 at +0x10). */
function instanceVector2(object, klassPtr, name) {
    const boxed = instance(object, klassPtr, name);
    if (!boxed || boxed.isNull()) return null;
    const raw = init().unbox(boxed);
    return [raw.readS32(), raw.add(4).readS32()];
}

/** Layout rectangles and the divider column, as plain integers. */
function geometry(draw, drawClass) {
    return {
        center_line: instanceInt(draw, drawClass, 'center_line'),
        right_title: instanceVector2(draw, drawClass, 'right_title_pos'),
        right_message_u: instanceVector2(draw, drawClass, 'right_message_pos_u'),
        right_message_d: instanceVector2(draw, drawClass, 'right_message_pos_d'),
    };
}

/** Read the vocabulary through KeyCollection.CopyTo, without dictionary offsets. */
function glyphWords() {
    const a = init(), table = staticField(klass('Global'), 'alien_text');
    if (table.isNull()) throw gameError('CATALOGUE_UNAVAILABLE');
    const keys = getter(table, 'get_Keys');
    const count = a.unbox(getter(table, 'get_Count')).readS32();
    const stringClass = classInImage(imageByName('mscorlib.dll'), 'String', 'System');
    const array = a.arrayNew(stringClass, count);
    const zero = Memory.alloc(4);
    zero.writeS32(0);
    const args = Memory.alloc(PTR_SIZE * 2);
    args.writePointer(array);
    args.add(PTR_SIZE).writePointer(zero);
    const method = a.methodFromName(a.objectGetClass(keys), Memory.allocUtf8String('CopyTo'), 2);
    checkedInvoke(method, keys, args);
    return arrayElements(array).map(text).filter(word => word !== null);
}

/** Same vector paths used by the game's character renderer. No labels or notes. */
function glyphPaths(word) {
    const a = init(), draw = drawObject();
    if (draw.isNull()) throw gameError('GLYPH_RENDERER_UNAVAILABLE');
    const method = a.methodFromName(klass('Draw'), Memory.allocUtf8String('StringToCharacter'), 1);
    const paths = checkedInvoke(method, draw, stringArgument(word));
    return listItems(paths).map(path => {
        const pathClass = a.objectGetClass(path);
        const items = instance(path, pathClass, '_items');
        const count = instanceInt(path, pathClass, '_size');
        const points = [];
        // Vector2 is an inline value type: each array element is two float32s.
        for (let i = 0; i < count; i++) {
            const point = a.arrayData(items, 8).add(i * 8);
            points.push([point.readFloat(), point.add(4).readFloat()]);
        }
        return points;
    });
}
