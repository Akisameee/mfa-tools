// Exercise the actual runtime adapter with a small native-API stand-in.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const scenario = process.argv[3];
const calls = [];
const pointer = value => ({
    value,
    isNull() { return this.value === 0; },
    toString() { return String(this.value); },
    add(offset) { return pointer(this.value + offset); },
    readPointer() { return pointer(this.value + 1); },
    readU32() { return this.count; },
});
const nativeExports = {
    mono_field_set_value: (object, field, value) => {
        assert.equal(object.value, 100);
        assert.equal(field.value, 300);
        assert.equal(value.value, 500);
    },
    il2cpp_field_set_value_object: (object, field, value) => {
        assert.equal(object.value, 100);
        assert.equal(field.value, 300);
        assert.equal(value.value, 500);
    },
    mono_get_root_domain: () => pointer(10),
    il2cpp_domain_get: () => pointer(10),
    mono_thread_attach: () => pointer(20),
    il2cpp_thread_attach: () => pointer(20),
    mono_class_get_parent: klass => pointer(klass.value === 100 ? 101 : 0),
    mono_class_get_method_from_name: klass => pointer(klass.value === 101 ? 200 : 0),
    mono_class_get_field_from_name: klass => pointer(klass.value === 101 ? 300 : 0),
    mono_field_get_parent: () => pointer(101),
    mono_class_vtable: (domain, klass) => {
        assert.equal(domain.value, 10);
        assert.equal(klass.value, 101);
        return pointer(400);
    },
    mono_field_static_get_value: (vtable, field) => {
        assert.equal(vtable.value, 400);
        assert.equal(field.value, 300);
    },
    mono_array_addr_with_size: (array, size, index) => {
        assert.equal(size, 8);
        assert.equal(index, 0);
        return pointer(array.value + 80);
    },
    mono_array_new: (domain, klass, length) => {
        assert.equal(domain.value, 10);
        assert.equal(length, 3);
        return pointer(500);
    },
    mono_compile_method: method => pointer(method.value + 1000),
    mono_assembly_foreach: visit => visit(pointer(600), pointer(0)),
    mono_assembly_get_image: () => pointer(700),
    mono_image_get_name: () => ({readUtf8String: () => 'Assembly-CSharp'}),
    il2cpp_domain_get_assemblies: (domain, count) => {
        count.count = 1;
        return pointer(600);
    },
    il2cpp_assembly_get_image: () => pointer(700),
    il2cpp_image_get_name: () => ({readUtf8String: () => 'Assembly-CSharp.dll'}),
};
const context = vm.createContext({
    ptr: pointer,
    Process: {
        pointerSize: 8,
        findModuleByName(name) {
            const expected = scenario === 'mono' ? 'mono-2.0-bdwgc.dll' : 'GameAssembly.dll';
            return scenario !== 'unsupported' && name === expected ? {getExportByName: name => name} : null;
        },
    },
    Memory: {alloc: () => pointer(800), allocUtf8String: value => value},
    NativeFunction: function(name) {
        return (...args) => {
            calls.push(name);
            assert.ok(nativeExports[name], `Unexpected native call: ${name}`);
            return nativeExports[name](...args);
        };
    },
    NativeCallback: function(callback) { return callback; },
});
vm.runInContext(fs.readFileSync(require('node:path').join(require('node:path').dirname(process.argv[2]), 'protocol.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);
if (scenario === 'unsupported') {
    assert.throws(() => vm.runInContext('init()', context), /RUNTIME_UNSUPPORTED/);
} else {
    const api = vm.runInContext('init()', context);
    assert.equal(api.runtime, scenario);
    api.fieldSetReference(pointer(100), pointer(300), pointer(500));
    assert.equal(vm.runInContext("imageByName('Assembly-CSharp.dll')", context).value, 700);
    if (scenario === 'mono') {
        assert.equal(api.methodFromName(pointer(100), 'get_transform', 0).value, 200);
        assert.equal(api.fieldFromName(pointer(100), 'field').value, 300);
        api.fieldStaticGet(pointer(300), pointer(900));
        assert.equal(api.arrayData(pointer(1000), 8).value, 1080);
        assert.equal(api.arrayNew(pointer(100), 3).value, 500);
        assert.equal(api.methodAddress(pointer(200)).value, 1200);
        assert.equal(api.methodAddress(pointer(200)).value, 1200);
        assert.equal(calls.filter(name => name === 'mono_compile_method').length, 1);
    } else {
        assert.equal(api.methodAddress(pointer(200)).value, 201);
        assert.equal(api.arrayData(pointer(1000), 8).value, 1032);
        assert.ok(!calls.some(name => name.startsWith('mono_')));
    }
}
