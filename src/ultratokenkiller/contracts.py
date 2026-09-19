"""Versioned internal contracts; all token counts here are estimates."""
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class CompressionResult:
    content: str
    content_type: str
    before_tokens: int
    after_tokens: int
    strategy: str = "native-v2"
    estimator: str = "utf8_bytes_div_4"
    recovery_id: str | None = None
    fallback: str | None = None
    preserved: tuple[str, ...] = ()

    @property
    def saved_tokens(self):
        return max(0, self.before_tokens - self.after_tokens)

    def metadata(self):
        result = asdict(self)
        result.pop("content")
        result["saved_tokens"] = self.saved_tokens
        return result
