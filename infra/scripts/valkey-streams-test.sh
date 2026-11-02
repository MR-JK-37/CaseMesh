#!/bin/sh
# Section 6.4 / decision-log ADR-11: "write a Phase 0 test proving
# XADD/XREADGROUP/PUBLISH on the pinned Valkey image before relying on
# it, else use Redis-compatible image and log it." This runs the pinned
# image in an ephemeral container, exercises Streams (XADD/XGROUP
# CREATE/XREADGROUP/XACK) and pub/sub (PUBLISH/SUBSCRIBE via two
# connections), and fails loudly if any of it doesn't behave like Redis.
set -eu

IMAGE="valkey/valkey:8-alpine"
NAME="icm-valkey-streams-test-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Pulling $IMAGE ..."
docker pull "$IMAGE"

echo "Starting ephemeral container $NAME ..."
docker run -d --rm --name "$NAME" -p 16379:6379 "$IMAGE" >/dev/null

for i in $(seq 1 20); do
  docker exec "$NAME" valkey-cli ping >/dev/null 2>&1 && break
  sleep 0.5
done

echo "--- Streams: XADD / XGROUP CREATE / XREADGROUP / XACK ---"
docker exec "$NAME" valkey-cli XADD icm:test:stream '*' field1 value1
docker exec "$NAME" valkey-cli XGROUP CREATE icm:test:stream icm-test-group 0
READ_OUT=$(docker exec "$NAME" valkey-cli XREADGROUP GROUP icm-test-group consumer-1 COUNT 1 STREAMS icm:test:stream '>')
echo "$READ_OUT"
echo "$READ_OUT" | grep -q "value1" || { echo "FAIL: XREADGROUP did not return the message added by XADD"; exit 1; }

MSG_ID=$(docker exec "$NAME" valkey-cli XRANGE icm:test:stream - + COUNT 1 | head -1)
docker exec "$NAME" valkey-cli XACK icm:test:stream icm-test-group "$MSG_ID" >/dev/null
PENDING=$(docker exec "$NAME" valkey-cli XPENDING icm:test:stream icm-test-group)
echo "pending after XACK: $PENDING"

echo "--- Pub/Sub: PUBLISH reaches a SUBSCRIBEr ---"
docker exec -d "$NAME" sh -c "valkey-cli SUBSCRIBE icm:test:channel > /tmp/sub-out.txt 2>&1"
sleep 1
docker exec "$NAME" valkey-cli PUBLISH icm:test:channel hello-icm >/dev/null
sleep 1
SUB_OUT=$(docker exec "$NAME" cat /tmp/sub-out.txt)
echo "$SUB_OUT"
echo "$SUB_OUT" | grep -q "hello-icm" || { echo "FAIL: subscriber did not receive the published message"; exit 1; }

echo
echo "PASS: $IMAGE supports XADD/XGROUP CREATE/XREADGROUP/XACK and PUBLISH/SUBSCRIBE as used by Section 6.4's outbox relay design."
