# Application Stage Fail-safe Behavior

Browser setup or application-site failures must not erase or invalidate successful discovery/resume output. Setup failures preserve `READY_TO_APPLY` for a later retry; confirmed submissions become terminal; ambiguous submissions are preserved for verification and must not be double-submitted.
