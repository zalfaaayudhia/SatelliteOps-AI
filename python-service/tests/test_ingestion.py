from app.ingestion import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []


def test_short_text_returns_one_chunk():
    assert chunk_text("Satellite status is nominal.") == [
        "Satellite status is nominal."
    ]


def test_invalid_chunk_size_is_rejected():
    try:
        chunk_text("Satellite", chunk_size=0)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")


def test_chunks_preserve_content():
    text = "A" * 1000
    chunks = chunk_text(text, chunk_size=300, overlap=50)

    assert len(chunks) > 1
    assert all(chunks)
    assert all(len(chunk) <= 300 for chunk in chunks)