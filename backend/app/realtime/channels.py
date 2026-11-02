"""Section 6: 'every subscription authorised with the same policy module
as REST.' A principal doesn't choose its channels — they're derived
server-side from role/institution, exactly like `can()` derives
permissions from role. No client input decides what it can subscribe to.
"""


def allowed_channels_for(*, role: str, institution_id: str | None) -> list[str]:
    if role in ("super_admin", "aicte_officer", "auditor"):
        return ["alerts:admin", "role:aicte_officer"]
    if role in ("institution_admin", "institution_staff") and institution_id:
        return [f"inst:{institution_id}"]
    if role == "student" and institution_id:
        return [f"inst:{institution_id}:student-visible"]
    return []
