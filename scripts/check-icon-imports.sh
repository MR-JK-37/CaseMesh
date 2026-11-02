#!/bin/sh
# Section 9.5: mobile code may only import icons through
# packages/ui-tokens (the AppIcon semantic table). This fails the build on
# any import from another icon library or an emoji used as an icon.
set -eu

fail=0
banned_pattern="(react-native-vector-icons|@expo/vector-icons|ionicons|font-?awesome|lucide-react-native|react-native-feather)"

echo "Checking apps/mobile for banned icon library imports ..."
if grep -rnEi "$banned_pattern" --include="*.ts" --include="*.tsx" apps/mobile 2>/dev/null; then
    echo "FAIL: mobile code imports a non-approved icon library. Use @icm/ui-tokens (AppIcon) instead."
    fail=1
fi

echo "Checking apps/web for the same banned icon libraries ..."
if grep -rnEi "$banned_pattern" --include="*.ts" --include="*.tsx" apps/web 2>/dev/null; then
    echo "FAIL: web code imports a non-approved icon library. Use @icm/ui-tokens / Material Symbols instead."
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "OK: no banned icon-library imports found."
fi
exit "$fail"
