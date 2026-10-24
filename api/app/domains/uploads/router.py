"""Upload endpoint for stage plot element images.

Accepts a single image file and stores it under the configured upload directory.
Returns the URL path that the client can use as a stage plot element's image_url.
"""

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.domains.auth.deps import get_current_user
from app.domains.auth.models import User

router = APIRouter(tags=["uploads"])


def _safe_ext(filename: str | None) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in get_settings().upload_extensions:
        ext = ".png"
    return ext


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    _user: User = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only image files are accepted")

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File is larger than {settings.max_upload_bytes} bytes",
        )

    os.makedirs(settings.upload_dir, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{_safe_ext(file.filename)}"
    dest = os.path.join(settings.upload_dir, stored)
    with open(dest, "wb") as fh:
        fh.write(data)

    return {"url": f"/static/{stored}", "filename": stored}
