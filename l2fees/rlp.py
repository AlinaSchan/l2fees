"""rlp, the encoding every ethereum transaction is serialised in: enough of it to take a signed
transaction apart and put the unsigned part back together. items are bytes or lists of items."""
from __future__ import annotations


def _length(n: int, offset: int) -> bytes:
    if n < 56:
        return bytes([offset + n])
    size = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([offset + 55 + len(size)]) + size


def encode(item) -> bytes:
    if isinstance(item, (bytes, bytearray)):
        data = bytes(item)
        if len(data) == 1 and data[0] < 0x80:
            return data
        return _length(len(data), 0x80) + data
    if isinstance(item, int):
        return encode(b"" if item == 0 else item.to_bytes((item.bit_length() + 7) // 8, "big"))
    body = b"".join(encode(x) for x in item)
    return _length(len(body), 0xC0) + body


def _decode_at(data: bytes, i: int):
    """(item, next index) for the item that starts at data[i]."""
    first = data[i]
    if first < 0x80:
        return data[i:i + 1], i + 1
    if first <= 0xB7:
        n = first - 0x80
        return data[i + 1:i + 1 + n], i + 1 + n
    if first <= 0xBF:
        size = first - 0xB7
        n = int.from_bytes(data[i + 1:i + 1 + size], "big")
        start = i + 1 + size
        return data[start:start + n], start + n
    if first <= 0xF7:
        n = first - 0xC0
        start = i + 1
    else:
        size = first - 0xF7
        n = int.from_bytes(data[i + 1:i + 1 + size], "big")
        start = i + 1 + size
    end = start + n
    items = []
    j = start
    while j < end:
        item, j = _decode_at(data, j)
        items.append(item)
    if j != end:
        raise ValueError("rlp list does not add up")
    return items, end


def decode(data: bytes):
    item, end = _decode_at(data, 0)
    if end != len(data):
        raise ValueError(f"{len(data) - end} trailing bytes after the rlp item")
    return item


def to_int(item: bytes) -> int:
    return int.from_bytes(item, "big") if item else 0
