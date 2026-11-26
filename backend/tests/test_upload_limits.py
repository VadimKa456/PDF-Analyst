"""Request-level limits for batches of uploaded PDFs."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.documents import MAX_FILES_PER_UPLOAD, _validate_upload_count


def test_upload_batch_at_limit_is_allowed() -> None:
    _validate_upload_count(MAX_FILES_PER_UPLOAD)


def test_upload_batch_over_limit_is_rejected_with_413() -> None:
    with pytest.raises(HTTPException) as error:
        _validate_upload_count(MAX_FILES_PER_UPLOAD + 1)

    assert error.value.status_code == 413
    assert str(MAX_FILES_PER_UPLOAD) in error.value.detail
