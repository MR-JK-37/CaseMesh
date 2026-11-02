#!/bin/sh
# Section 1.3 / SC-41: CI fails the build if application code imports a
# fixture/synthetic-data generator, or if a non-test Alembic migration
# inserts business data. Synthetic data may exist only under tests/.
set -eu

fail=0

echo "Checking for fixture-generator imports outside tests/ ..."
if grep -rnE "(^|[^.])\b(faker|Faker|fixtures?_generator|generate_fake|seed_fake)\b" \
    --include="*.py" --include="*.ts" --include="*.tsx" \
    backend/app rules/rules apps packages 2>/dev/null \
    | grep -v -E "(^|/)(tests?)/" ; then
    echo "FAIL: application code references a fixture/fake-data generator outside tests/."
    fail=1
fi

echo "Checking Alembic migrations for hand-inserted business data ..."
if [ -d backend/alembic/versions ]; then
    if grep -rnE "(op\.bulk_insert|op\.execute\(.*INSERT INTO)" backend/alembic/versions 2>/dev/null; then
        echo "FAIL: a migration inserts data directly. Reference-data import must go"
        echo "      through the provenance-tracked import pipeline (Section 1.5), not a migration."
        fail=1
    fi
fi

if [ "$fail" -eq 0 ]; then
    echo "OK: no fixture imports or seeded business data found outside tests/."
fi
exit "$fail"
