"""Compatibility shim for Unity 6000.5 SerializedFile format 23.

UnityPy 1.25.x predates extracted type trees. Format 23 prefixes every type
tree with its xxh3-128 hash and byte size; inline trees then carry a ``tthm``
header and their own format version. Keep those bytes so UnityPy can also save
the containing assets file without corrupting its metadata.
"""


def enable():
    from UnityPy.files.SerializedFile import SerializedType
    from UnityPy.helpers.TypeTreeNode import TypeTreeNode

    if getattr(SerializedType, "_format23_compat", False):
        return

    original_init = SerializedType.__init__
    original_write = SerializedType.write
    original_parse_blob = TypeTreeNode.parse_blob.__func__
    original_dump_blob = TypeTreeNode.dump_blob

    def parse_blob(cls, reader, version):
        if version < 23:
            return original_parse_blob(cls, reader, version)
        tree_hash = bytes(reader.read_bytes(16))
        tree_size = reader.read_u_int()
        state = (tree_hash, tree_size, None)
        if tree_size == 0:
            _pending.append(state)
            return None
        start = reader.Position
        magic = reader.read_u_int()
        tree_version = reader.read_int()
        if magic != 0x7474686D:
            raise ValueError(f"invalid format 23 type tree magic: 0x{magic:08x}")
        node = original_parse_blob(cls, reader, tree_version)
        consumed = reader.Position - start
        if consumed != tree_size:
            raise ValueError(f"format 23 type tree size {tree_size}, read {consumed}")
        _pending.append((tree_hash, tree_size, tree_version))
        return node

    def init(self, reader, serialized_file, is_ref_type):
        before = len(_pending)
        original_init(self, reader, serialized_file, is_ref_type)
        if serialized_file.header.version >= 23 and serialized_file._enable_type_tree:
            if len(_pending) != before + 1:
                raise ValueError("missing format 23 type tree metadata")
            _tree_info[id(self)] = _pending.pop()

    def write(self, serialized_file, writer, is_ref_type):
        if serialized_file.header.version < 23 or not serialized_file._enable_type_tree:
            return original_write(self, serialized_file, writer, is_ref_type)

        # Serialize the fixed prefix exactly as UnityPy does, then write the
        # format-23 wrapper around the optional tree.
        version = serialized_file.header.version
        writer.write_int(self.class_id)
        if version >= 16:
            writer.write_boolean(self.is_stripped_type)
        if version >= 17:
            writer.write_short(self.script_type_index)
        if version >= 13:
            if ((is_ref_type and self.script_type_index >= 0)
                    or (version < 16 and self.class_id < 0)
                    or (version >= 16 and self.class_id == 114)):
                writer.write_bytes(self.script_id)
            writer.write_bytes(self.old_type_hash)

        tree_hash, tree_size, tree_version = _tree_info[id(self)]
        writer.write_bytes(tree_hash)
        writer.write_u_int(tree_size)
        if tree_size:
            start = writer.Position
            writer.write_u_int(0x7474686D)
            writer.write_int(tree_version)
            original_dump_blob(self.node, writer, tree_version)
            if writer.Position - start != tree_size:
                raise ValueError("modified format 23 inline type tree size")

        if version >= 21:
            if is_ref_type:
                writer.write_string_to_null(self.m_ClassName)
                writer.write_string_to_null(self.m_NameSpace)
                writer.write_string_to_null(self.m_AssemblyName)
            else:
                writer.write_int_array(self.type_dependencies, True)

    _pending = []
    _tree_info = {}
    TypeTreeNode.parse_blob = classmethod(parse_blob)
    SerializedType.__init__ = init
    SerializedType.write = write
    SerializedType._format23_compat = True
