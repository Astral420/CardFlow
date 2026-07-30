import io
import zipfile

from app.api.batches import _FlushableZipStream


def test_flushable_zip_stream_produces_a_valid_archive():
    stream = _FlushableZipStream()
    chunks = []
    with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(5):
            zf.writestr(f"file_{i}.txt", f"contents {i} " * 500)
            chunk = stream.take()
            if chunk:
                chunks.append(chunk)
    trailing = stream.take()
    if trailing:
        chunks.append(trailing)

    archive_bytes = b"".join(chunks)
    zf = zipfile.ZipFile(io.BytesIO(archive_bytes))
    assert zf.testzip() is None  # None means every entry's CRC checks out
    assert sorted(zf.namelist()) == [f"file_{i}.txt" for i in range(5)]
    for i in range(5):
        assert zf.read(f"file_{i}.txt").decode() == f"contents {i} " * 500


def test_flushable_zip_stream_yields_more_than_one_chunk():
    """The whole point of the fix: bytes are available before the archive
    is fully built, not just at the very end."""
    stream = _FlushableZipStream()
    chunk_count = 0
    with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(10):
            zf.writestr(f"file_{i}.txt", "x" * 10_000)
            if stream.take():
                chunk_count += 1
    assert chunk_count >= 5  # flushed well before the archive was complete


def test_flushable_zip_stream_has_no_seek_attribute():
    """zipfile detects non-seekable streams via AttributeError on .seek;
    if this ever grows a .seek method, zipfile will try to patch local
    file headers in place instead of using data descriptors, which breaks
    true streaming."""
    stream = _FlushableZipStream()
    assert not hasattr(stream, "seek")
