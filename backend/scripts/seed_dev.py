"""Local-dev-only bootstrap: creates the first super_admin (otherwise
nobody could create any other user — a real chicken-and-egg every
admin console has) plus a couple of real Bureau/Cell and Regional
Office rows seeded from AICTE's public bureaus page with provenance
(Section 1.2/1.3), so the system doesn't start with zero navigable
reference data as well as zero cases.

This is explicitly NOT run automatically (no auto-seed on startup,
Section 0 rule 2's "no fake data" extends to not silently bootstrapping
a privileged account) — a human runs this once, locally, and is told
the generated password.
"""

import asyncio
import datetime as dt
import secrets

import pyotp
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models import Bureau, RegionalOffice, SlaPolicy, User

# Runs as the migration (owner) role, not the icm_app runtime role: this
# is a one-time local bootstrap, not a request path, and icm_app
# deliberately has no INSERT grant on bureaus/regional_offices yet (no
# Phase 1 endpoint writes them — Section 12's least-privilege grants).
_engine = create_async_engine(settings.migration_database_url)
_SeedSession = async_sessionmaker(_engine, expire_on_commit=False)


async def main() -> None:
    async with _SeedSession() as session, session.begin():
        # RLS on `users` (Phase 1 migration) rejects an INSERT with no
        # app.role context at all — this bootstrap script has no
        # authenticated principal yet (that's exactly the problem it
        # solves), so it sets the same privileged context
        # core/db.py's get_privileged_session uses. (icm_owner is the
        # table owner and bypasses RLS regardless, but setting this
        # keeps the script's behavior consistent if it's ever pointed
        # at a non-owner connection.)
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        existing = (
            await session.execute(select(User).where(User.role == "super_admin"))
        ).scalar_one_or_none()
        if existing is None:
            # super_admin requires TOTP (Section 4.1), but TOTP
            # enrollment itself requires being logged in — a real
            # chicken-and-egg for the very first account. Real systems
            # solve this by pre-provisioning a break-glass account's
            # TOTP secret out-of-band; this script does the same thing
            # locally: it generates and activates the secret directly
            # (bypassing the normal start/confirm enrollment dance,
            # which is only reachable from an authenticated session)
            # and prints the provisioning URI for the admin to add to
            # an authenticator app before their first login.
            password = secrets.token_urlsafe(18)
            totp_secret = pyotp.random_base32()
            admin = User(
                email="admin@icm.local",
                password_hash=hash_password(password),
                display_name="Local Dev Admin",
                role="super_admin",
                is_active=True,
                totp_secret=totp_secret,
            )
            admin.totp_enrolled_at = dt.datetime.now(dt.UTC)
            session.add(admin)
            uri = pyotp.TOTP(totp_secret).provisioning_uri(
                name=admin.email, issuer_name=settings.totp_issuer
            )
            print(f"Created super_admin admin@icm.local / {password}")
            print(f"TOTP provisioning URI (add to an authenticator app before first login): {uri}")
            print(f"TOTP secret (if entering manually): {totp_secret}")
        else:
            print(f"super_admin already exists: {existing.email}")

        bureau_count = (await session.execute(select(Bureau))).scalars().all()
        if not bureau_count:
            # Source: aicte.gov.in/bureaus (Section 15 — the two public
            # sources disagree, this list is admin-editable, not treated
            # as a single source of truth).
            session.add_all(
                [
                    Bureau(
                        name="Approvals Bureau (Regulation)",
                        kind="bureau",
                        data_origin="public_import",
                        source_name="AICTE bureaus page",
                        source_url="https://www.aicte-india.org/bureaus",
                    ),
                    Bureau(
                        name="Public Grievance Redressal Cell",
                        kind="cell",
                        data_origin="public_import",
                        source_name="AICTE PGRC page",
                        source_url="https://www.aicte-india.org/node/422",
                    ),
                ]
            )
            session.add(
                RegionalOffice(
                    name="Regional Office — Chennai",
                    data_origin="public_import",
                    source_name="Wikipedia (AICTE regional offices list) — open item, see docs/decision-log.md",
                    source_url="https://en.wikipedia.org/wiki/All_India_Council_for_Technical_Education",
                )
            )
            print("Seeded 2 bureaus + 1 regional office with provenance.")
        else:
            print(f"{len(bureau_count)} bureau(s) already exist, not reseeding.")

        policy_count = (await session.execute(select(SlaPolicy))).scalars().all()
        if not policy_count:
            # Section 7.2: "Seed only what is verified" — DARPG OM
            # 23.08.2024's CPGRAMS numbers, nothing else. Every other
            # (source, matter_type, priority) combination stays absent
            # on purpose; the case shows "SLA policy not set" and a
            # SLA_POLICY_MISSING alert fires (Section 7.3), rather than
            # a guessed number ever being seeded.
            source_citation = "DARPG Comprehensive Guidelines, OM dated 23.08.2024"
            session.add_all(
                [
                    SlaPolicy(
                        source_channel="cpgrams",
                        matter_type=None,
                        priority="standard",
                        days=21,
                        warn_at=[5, 2],
                        version=1,
                        source_name=source_citation,
                    ),
                    SlaPolicy(
                        source_channel="cpgrams",
                        matter_type=None,
                        priority="priority",
                        days=3,
                        warn_at=[1],
                        version=1,
                        source_name=source_citation,
                    ),
                ]
            )
            print("Seeded 2 CPGRAMS SLA policies (standard=21d, priority=3d) with provenance.")
        else:
            print(f"{len(policy_count)} SLA policy row(s) already exist, not reseeding.")


if __name__ == "__main__":
    asyncio.run(main())
