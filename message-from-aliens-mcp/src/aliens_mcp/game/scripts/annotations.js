function annotationCells() {
    const draw = drawObject();
    if (draw.isNull()) throw gameError('PAGE_UNAVAILABLE');
    return arrayElements(instance(draw, klass('Draw'), 'alien_slots')).filter(cell => !cell.isNull());
}

function readAnnotation(word) {
    const read = init().methodFromName(klass('Global'), Memory.allocUtf8String('GetDict'), 1);
    return text(checkedInvoke(read, NIL, stringArgument(word))) || '';
}

function setAnnotationWord(cell, word) {
    // Use the runtime reference setter (including its GC write barrier).
    const a = init(), field = fieldOf(a.objectGetClass(cell), 'alien_txt');
    if (field.isNull()) throw gameError('IDENTITY_FIELD_UNAVAILABLE');
    const value = word === null ? NIL : stringArgument(word).readPointer();
    a.fieldSetReference(cell, field, value);
}

function refreshAnnotation(word) {
    const a = init();
    for (const cell of annotationCells()) {
        const type = a.objectGetClass(cell);
        if (instanceText(cell, type, 'alien_txt') === word) {
            checkedInvoke(a.methodFromName(type, Memory.allocUtf8String('UpdateEarthText'), 0), cell);
        }
    }
}

function editNote(word, value) {
    const a = init();
    // Reuse an unfocused component only for the synchronous EndEdit call. Its
    // identity is restored before Update continues, even on failure. This keeps
    // the native achievement, special-page refresh, and SaveGame behavior for
    // characters absent from this page, without navigating or changing focus.
    const candidates = annotationCells().filter(cell => {
        const input = instance(cell, a.objectGetClass(cell), 'txt');
        return !input.isNull() && !a.unbox(getter(input, 'get_isFocused')).readU8();
    });
    const cell = candidates.find(cell => instanceText(cell, a.objectGetClass(cell), 'alien_txt') === word)
                 || candidates[0];
    if (!cell) throw gameError('ANNOTATION_FIELD_UNAVAILABLE');
    const type = a.objectGetClass(cell), input = instance(cell, type, 'txt');
    const limit = instanceInt(input, a.objectGetClass(input), 'm_CharacterLimit');
    if (value.length > 49 || (limit > 0 && value.length > limit)) {
        throw gameError('ANNOTATION_TOO_LONG');
    }
    const original = instanceText(cell, type, 'alien_txt');
    const submit = a.methodFromName(type, Memory.allocUtf8String('EndEdit'), 1);
    const previous = readAnnotation(word);
    function commit(value) {
        try {
            if (original !== word) setAnnotationWord(cell, word);
            checkedInvoke(submit, cell, stringArgument(value));
        } finally {
            if (original !== word) setAnnotationWord(cell, original);
        }
    }
    try {
        commit(value);
        if (readAnnotation(word) !== value) {
            throw gameError('ANNOTATION_NOT_COMMITTED');
        }
    } catch (error) {
        try {
            commit(previous);
        } catch (restoreError) {
            throw gameError('ANNOTATION_RESTORE_FAILED', {cause: error.code || 'INTERNAL_ERROR', restore: restoreError.code || 'INTERNAL_ERROR'}, error);
        }
        throw error;
    }
    return {ok: true, text: value};
}

rpc.exports.note = function (word, value, thread, window) {
    if (typeof word !== 'string' || !word) throw gameError('CHARACTER_UNAVAILABLE');
    if (typeof value !== 'string' || /[\r\n\0]/.test(value) || value.length > 49) {
        throw gameError('INVALID_NATIVE_ANNOTATION');
    }
    return queueInput({kind: 'note', word, value}, thread, window);
};

operations.note = {
    enter(request) { request.result = editNote(request.word, request.value); },
    leave(request, finish) {
        try {
            refreshAnnotation(request.word);
            const stored = readAnnotation(request.word);
            if (stored !== request.value && !(request.value === '' && stored === '?')) {
                throw gameError('ANNOTATION_LOST');
            }
            finish(request);
        } catch (error) { finish(request, error); }

    },
};
