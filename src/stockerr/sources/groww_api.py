"""Groww Trading API source (LATER / optional).

This is a stub. v1 uses the free CSV route (`groww_csv.py`) because the paid
Trading API (~Rs.499/mo) has no read-only credential and omits mutual funds.

If you decide the tradeoff is worth it for hands-off *stock* pulls:

  1.  `pip install "stockerr[groww-api]"`  (adds growwapi + pyotp)
  2.  Subscribe + create API key/secret at https://groww.in/trade-api/api-keys
  3.  Prefer the TOTP flow so scheduled runs need no daily manual login.
  4.  Store the credentials as extra keyring secrets and implement fetch_holdings()
      below using:

          from growwapi import GrowwAPI
          import pyotp
          access_token = GrowwAPI.get_access_token(api_key=..., secret=...)  # or TOTP flow
          groww = GrowwAPI(access_token)
          data = groww.get_holdings_for_user()   # equity delivery holdings

      Map each holding to models.Holding(category=CATEGORY_STOCK, currency="INR").

SECURITY NOTE: any growwapi credential can also place/cancel orders — there is no
read-only scope. Keep the secret in the OS keyring, do NOT grant DDPI (blocks
API-initiated sells of holdings), and never call order methods from this tool.
"""

from __future__ import annotations

from .base import Source


class GrowwApiSource(Source):
    name = "groww_api"

    def fetch_holdings(self):  # pragma: no cover - intentionally unimplemented in v1
        raise NotImplementedError(
            "Groww Trading API source is not enabled in v1. Use the CSV route "
            "(STOCKERR_GROWW_CSV), or implement this adapter — see the module docstring."
        )
