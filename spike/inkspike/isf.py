"""Ink Serialized Format (ISF) <-> stroke lists, via the WinRT ink APIs.

OneNote stores each ink stroke as base64 ISF. Decoded points are in DIPs
(1/96 inch) in page coordinates, so strokes from different elements on the
same page line up without further offsets.
"""
import asyncio

from winrt.windows.foundation import Point
from winrt.windows.storage.streams import DataReader, DataWriter, InMemoryRandomAccessStream
from winrt.windows.ui.input.inking import InkStrokeBuilder, InkStrokeContainer

Stroke = list[tuple[float, float]]


async def _decode(data: bytes) -> list[Stroke]:
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(data)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    container = InkStrokeContainer()
    await container.load_async(stream)
    return [[(p.position.x, p.position.y) for p in s.get_ink_points()] for s in container.get_strokes()]


async def _encode(strokes: list[Stroke]) -> bytes:
    container = InkStrokeContainer()
    builder = InkStrokeBuilder()
    for s in strokes:
        container.add_stroke(builder.create_stroke([Point(x, y) for x, y in s]))
    stream = InMemoryRandomAccessStream()
    await container.save_async(stream)
    size = stream.size
    stream.seek(0)
    reader = DataReader(stream.get_input_stream_at(0))
    await reader.load_async(size)
    buf = bytearray(size)
    reader.read_bytes(buf)
    return bytes(buf)


def decode_isf(data: bytes) -> list[Stroke]:
    return asyncio.run(_decode(data))


def encode_isf(strokes: list[Stroke]) -> bytes:
    return asyncio.run(_encode(strokes))
