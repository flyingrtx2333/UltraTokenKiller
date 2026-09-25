import base64
import io
import asyncio

from PIL import Image, ImageDraw, ImageChops, ImageStat

from ultratokenkiller.compression import compress_content
from ultratokenkiller.image_compression import compress_data_url, compress_data_url_with_reason
from ultratokenkiller.recovery import RecoveryVault
from ultratokenkiller.proxy import compress_inline_images


def data_url(image, format="PNG"):
    output = io.BytesIO()
    image.save(output, format=format)
    return "data:image/" + format.lower() + ";base64," + base64.b64encode(output.getvalue()).decode()


def test_large_photo_like_image_shrinks_and_recovers_original():
    image = Image.effect_noise((2600, 2200), 18).convert("RGB")
    original = data_url(image)
    vault = RecoveryVault(capacity=64 * 1024 * 1024)
    result = compress_content(original, session="image", vault=vault, hint="image", query="describe the scene")
    assert result.recovery_id and result.content.startswith("data:image/jpeg;base64,")
    assert len(result.content) < len(original)
    assert len(result.content) / len(original) < .85
    assert result.fallback is None
    assert vault.retrieve("image", result.recovery_id, limit=64000)["content"] == original[:64000]
    encoded = base64.b64decode(result.content.split(",", 1)[1])
    with Image.open(io.BytesIO(encoded)) as decoded:
        assert max(decoded.size) <= 1600
        reference = image.copy()
        reference.thumbnail(decoded.size)
        difference = ImageChops.difference(reference, decoded.convert("RGB"))
        assert max(ImageStat.Stat(difference).mean) < 40


def test_detail_task_and_text_dense_image_pass_through():
    image = Image.new("RGB", (2400, 2200), "white")
    draw = ImageDraw.Draw(image)
    for y in range(20, 2100, 25):
        draw.text((20, y), "CODE identifier_73 must not change " * 5, fill="black")
    original = data_url(image)
    assert compress_data_url(original, "OCR every word") == original
    assert compress_data_url(original, "summarize") == original
    assert compress_data_url_with_reason(original, "OCR every word") == (original, "detail_task")
    assert compress_data_url_with_reason(original, "summarize") == (original, "text_dense_or_diagram")


def test_corrupt_unsupported_and_small_images_pass_through():
    for original in (
        "data:image/gif;base64,R0lGODlh",
        "data:image/png;base64,A===",
        "data:image/png;base64," + base64.b64encode(b"not an image").decode(),
        data_url(Image.new("RGB", (800, 600), "blue")),
    ):
        assert compress_data_url(original, "describe") == original
    assert compress_data_url_with_reason("https://example.invalid/image.png", "describe")[1] == "unsupported_format_or_url"
    assert compress_data_url_with_reason("data:image/png;base64,A===", "describe")[1] == "invalid_base64"


def test_protocol_image_replacement_adds_recovery_marker_and_preserves_order():
    class Broker:
        def compress(self, value, session, hint=None, query=""):
            assert session == "bound" and hint == "image"
            return {"content": "data:image/jpeg;base64,c21hbGw=", "recovery_id": "handle-1"}
    items = [{"role": "user", "content": [
        {"type": "input_text", "text": "describe"},
        {"type": "input_image", "image_url": "data:image/png;base64,bGFyZ2U="},
    ]}]
    changed = asyncio.run(compress_inline_images(items, Broker(), "bound", "describe"))
    assert changed == 1
    assert items[0]["content"][0]["text"] == "describe"
    assert items[0]["content"][1]["image_url"].startswith("data:image/jpeg")
    assert items[0]["content"][2] == {"type": "input_text", "text": "UTK original image: handle-1; use utk_retrieve"}


def test_anthropic_image_source_keeps_other_modalities_and_media_type():
    class Broker:
        def compress(self, value, session, hint=None, query=""):
            return {"content": "data:image/jpeg;base64,c21hbGw=", "recovery_id": "handle-2"}

    audio = {"type": "input_audio", "data": "opaque"}
    items = [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "bGFyZ2U="}},
        audio,
    ]}]
    changed = asyncio.run(compress_inline_images(items, Broker(), "bound", "describe"))
    assert changed == 1
    assert items[0]["content"][0]["source"] == {
        "type": "base64", "media_type": "image/jpeg", "data": "c21hbGw="
    }
    assert items[0]["content"][1] == audio
    assert items[0]["content"][2]["text"].endswith("handle-2; use utk_retrieve")


def test_inline_image_skip_reason_is_counted_separately_from_tool_skips():
    class Broker:
        def compress(self, value, session, hint=None, query=""):
            return {"content": value, "fallback": "text_dense_or_diagram"}

    items = [{"role": "user", "content": [{"type": "input_image", "image_url": "data:image/png;base64,bGFyZ2U="}]}]
    image_reasons = {}
    changed = asyncio.run(compress_inline_images(items, Broker(), "bound", "describe", image_reasons))

    assert changed == 0
    assert image_reasons == {"text_dense_or_diagram": 1}
