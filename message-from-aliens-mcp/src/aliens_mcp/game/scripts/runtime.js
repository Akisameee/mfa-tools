/* Runtime bindings shared by Mono and IL2CPP game builds. */
'use strict';

let api = null;

function init() {
    if (api) return api;
    const il2cpp = Process.findModuleByName('GameAssembly.dll');
    const mono = Process.findModuleByName('mono-2.0-bdwgc.dll');
    const module = il2cpp || mono;
    if (!module) throw gameError('RUNTIME_UNSUPPORTED');
    const f = (name, ret, args) => new NativeFunction(module.getExportByName(name), ret, args);
    if (il2cpp) {
        api = {
            runtime: 'il2cpp',
            domainGet: f('il2cpp_domain_get', 'pointer', []),
            threadAttach: f('il2cpp_thread_attach', 'pointer', ['pointer']),
            assemblyImage: f('il2cpp_assembly_get_image', 'pointer', ['pointer']),
            imageName: f('il2cpp_image_get_name', 'pointer', ['pointer']),
            classFromName: f('il2cpp_class_from_name', 'pointer', ['pointer', 'pointer', 'pointer']),
            objectGetClass: f('il2cpp_object_get_class', 'pointer', ['pointer']),
            fieldFromName: f('il2cpp_class_get_field_from_name', 'pointer', ['pointer', 'pointer']),
            methodFromName: f('il2cpp_class_get_method_from_name', 'pointer', ['pointer', 'pointer', 'int']),
            fieldStaticGet: f('il2cpp_field_static_get_value', 'void', ['pointer', 'pointer']),
            fieldGetObject: f('il2cpp_field_get_value_object', 'pointer', ['pointer', 'pointer']),
            fieldSetReference: f('il2cpp_field_set_value_object', 'void', ['pointer', 'pointer', 'pointer']),
            unbox: f('il2cpp_object_unbox', 'pointer', ['pointer']),
            invoke: f('il2cpp_runtime_invoke', 'pointer', ['pointer', 'pointer', 'pointer', 'pointer']),
            arrayLength: f('il2cpp_array_length', 'size_t', ['pointer']),
            arrayNew: f('il2cpp_array_new', 'pointer', ['pointer', 'size_t']),
            stringNewUtf16: f('il2cpp_string_new_utf16', 'pointer', ['pointer', 'int']),
            stringLength: f('il2cpp_string_length', 'int', ['pointer']),
            stringChars: f('il2cpp_string_chars', 'pointer', ['pointer']),
            methodAddress: method => method.isNull() ? ptr(0) : method.readPointer(),
            arrayData: array => array.add(Process.pointerSize * 4),
        };
        const assemblies = f('il2cpp_domain_get_assemblies', 'pointer', ['pointer', 'pointer']);
        api.images = () => {
            const count = Memory.alloc(Process.pointerSize);
            const list = assemblies(api.domainGet(), count);
            const result = [];
            for (let i = 0; i < count.readU32(); i++) {
                result.push(api.assemblyImage(list.add(i * Process.pointerSize).readPointer()));
            }
            return result;
        };
        const resolve = f('il2cpp_resolve_icall', 'pointer', ['pointer']);
        api.resolveIcall = name => resolve(Memory.allocUtf8String(name));
    } else {
        const domainGet = f('mono_get_root_domain', 'pointer', []);
        const domain = domainGet();
        const fieldParent = f('mono_field_get_parent', 'pointer', ['pointer']);
        const vtable = f('mono_class_vtable', 'pointer', ['pointer', 'pointer']);
        const staticGet = f('mono_field_static_get_value', 'void', ['pointer', 'pointer', 'pointer']);
        const fieldGet = f('mono_field_get_value_object', 'pointer', ['pointer', 'pointer', 'pointer']);
        const arrayNew = f('mono_array_new', 'pointer', ['pointer', 'pointer', 'size_t']);
        const arrayAddress = f('mono_array_addr_with_size', 'pointer', ['pointer', 'int', 'size_t']);
        const stringNew = f('mono_string_new_utf16', 'pointer', ['pointer', 'pointer', 'int']);
        const compile = f('mono_compile_method', 'pointer', ['pointer']);
        const foreach = f('mono_assembly_foreach', 'void', ['pointer', 'pointer']);
        const parent = f('mono_class_get_parent', 'pointer', ['pointer']);
        const getField = f('mono_class_get_field_from_name', 'pointer', ['pointer', 'pointer']);
        const getMethod = f('mono_class_get_method_from_name', 'pointer', ['pointer', 'pointer', 'int']);
        const inherited = (lookup, klass, ...args) => {
            for (let current = klass; !current.isNull(); current = parent(current)) {
                const result = lookup(current, ...args);
                if (!result.isNull()) return result;
            }
            return ptr(0);
        };
        const addresses = new Map();
        api = {
            runtime: 'mono',
            domainGet,
            threadAttach: f('mono_thread_attach', 'pointer', ['pointer']),
            threadDetach: f('mono_thread_detach', 'void', ['pointer']),
            assemblyImage: f('mono_assembly_get_image', 'pointer', ['pointer']),
            imageName: f('mono_image_get_name', 'pointer', ['pointer']),
            classFromName: f('mono_class_from_name', 'pointer', ['pointer', 'pointer', 'pointer']),
            objectGetClass: f('mono_object_get_class', 'pointer', ['pointer']),
            fieldFromName: (klass, name) => inherited(getField, klass, name),
            methodFromName: (klass, name, argc) => inherited(getMethod, klass, name, argc),
            fieldStaticGet: (field, value) => staticGet(vtable(domain, fieldParent(field)), field, value),
            fieldGetObject: (field, object) => fieldGet(domain, field, object),
            fieldSetReference: f('mono_field_set_value', 'void', ['pointer', 'pointer', 'pointer']),
            unbox: f('mono_object_unbox', 'pointer', ['pointer']),
            invoke: f('mono_runtime_invoke', 'pointer', ['pointer', 'pointer', 'pointer', 'pointer']),
            arrayLength: f('mono_array_length', 'size_t', ['pointer']),
            arrayNew: (klass, length) => arrayNew(domain, klass, length),
            arrayData: (array, size) => arrayAddress(array, size, 0),
            stringNewUtf16: (value, length) => stringNew(domain, value, length),
            stringLength: f('mono_string_length', 'int', ['pointer']),
            stringChars: f('mono_string_chars', 'pointer', ['pointer']),
            internalCall: f('mono_lookup_internal_call', 'pointer', ['pointer']),
            methodAddress: method => {
                if (method.isNull()) return ptr(0);
                const key = method.toString();
                if (!addresses.has(key)) addresses.set(key, compile(method));
                return addresses.get(key);
            },
            images: () => {
                const result = [];
                const visit = new NativeCallback(assembly => result.push(api.assemblyImage(assembly)),
                                                 'void', ['pointer', 'pointer']);
                foreach(visit, ptr(0));
                return result;
            },
        };
        api.resolveIcall = name => {
            const [type, signature] = name.split('::');
            const [methodName, parameters] = signature.split('(');
            const argc = parameters === undefined ? (methodName.startsWith('set_') ? 1 : 0) :
                         parameters === ')' ? 0 : parameters.split(',').length;
            const separator = type.lastIndexOf('.');
            const image = imageByName(type === 'UnityEngine.Input' ?
                'UnityEngine.InputLegacyModule.dll' : 'UnityEngine.CoreModule.dll');
            const klass = api.classFromName(image, Memory.allocUtf8String(type.slice(0, separator)),
                                            Memory.allocUtf8String(type.slice(separator + 1)));
            if (klass.isNull()) return ptr(0);
            const method = api.methodFromName(klass, Memory.allocUtf8String(methodName), argc);
            return method.isNull() ? ptr(0) : api.internalCall(method);
        };
    }
    const domain = api.domainGet();
    if (domain.isNull()) {
        api = null;
        throw gameError('RUNTIME_NOT_READY');
    }
    api.attachedThread = api.threadAttach(domain);
    return api;
}

function imageByName(name) {
    const a = init(), normalized = name.replace(/\.dll$/i, '').toLowerCase();
    for (const image of a.images()) {
        if (!image.isNull() && a.imageName(image).readUtf8String().replace(/\.dll$/i, '').toLowerCase() === normalized) {
            return image;
        }
    }
    return ptr(0);
}
