# STEP 5b — replace the one marked line inside request_discount:
#
#         # ---- STEP 5b: hand the AI's limit to the service here ----
#
# with everything below the line. It goes inside the call to the service, at
# the same indent as requested_via="ai" — keep the leading spaces, and check
# your editor did not add any of its own.
# ---------------------------------------------------------------------------


        # ---- STEP 5b: hand the AI's limit to the service ----
        # The service applies it alongside the normal approval rules and
        # assigns the status. The limit is enforced there, not here.
        max_auto_approve_pct=MAX_AI_AUTO_APPROVE_PCT,
