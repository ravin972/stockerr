from stockerr.logging_setup import redact


def test_redacts_signature_in_signed_url():
    url = ("https://api.binance.com/api/v3/account?"
           "timestamp=123&recvWindow=5000&signature=deadbeefcafe1234")
    out = redact(url)
    assert "deadbeefcafe1234" not in out      # signature value gone
    assert "signature=***" in out
    assert "timestamp=123" in out             # non-secret query preserved


def test_redacts_common_secret_keys():
    assert "abc123" not in redact("api_key=abc123")
    assert "s3cr3t" not in redact('"secret": "s3cr3t"')
    out = redact("token: mytokenvalue99")
    assert "mytokenvalue99" not in out
    assert "token: ***" in out


def test_redacts_telegram_bot_token_in_url():
    # Fully fake token (bot id + secret) — never a real one.
    msg = ("Telegram send failed: 403 Client Error: Forbidden for url: "
           "https://api.telegram.org/bot123456789:AAFakeSecret_Token-abcXYZ0123456/sendMessage")
    out = redact(msg)
    assert "AAFakeSecret_Token-abcXYZ0123456" not in out
    assert "123456789" not in out
    assert "bot***" in out
