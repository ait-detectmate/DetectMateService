#!/bin/bash

# Ensure we are in the project root
cd "$(dirname "$0")/.."

echo "--- Starting Manual Demo Scenario ---"

# Cleanup previous runs
echo "[1] Cleanup old sockets..."
rm -f /tmp/sender.engine.ipc /tmp/receiver.engine.ipc /tmp/sender.cmd.ipc /tmp/receiver.cmd.ipc

# Ensure logs directory exists
mkdir -p logs

# Start Sender
echo "[2] Starting Sender service (Receiver is DOWN)..."
# start background process
uv run detectmate start --settings scripts/config/sender.yaml > logs/sender.log 2>&1 &
SENDER_PID=$!
echo "    Sender started with PID $SENDER_PID. Logging to logs/sender.log"

# Wait for sender to initialize
sleep 2

# Send message 1
echo "[3] Sending Message 1 (should be accepted but dropped/queued by Sender)..."
uv run python scripts/client.py "Message 1 - Receiver Down"

# Start Receiver
echo "[4] Starting Receiver service..."
uv run detectmate start --settings scripts/config/receiver.yaml > logs/receiver.log 2>&1 &
RECEIVER_PID=$!
echo "    Receiver started with PID $RECEIVER_PID. Logging to logs/receiver.log"

# Wait for receiver to initialize and sender to connect
echo "    Waiting for connection..."
sleep 3

# Send message 2
echo "[5] Sending Message 2 (should be forwarded to Receiver)..."
uv run python scripts/client.py "Message 2 - Receiver UP"

echo "    Waiting a moment for logs to flush..."
sleep 1

echo "--- Logs Check ---"
echo ">>> Sender Log (tail):"
tail -n 5 logs/sender.log
echo ""
echo ">>> Receiver Log (tail):"
tail -n 5 logs/receiver.log

echo ""
echo "[6] Stopping services..."
kill $SENDER_PID
kill $RECEIVER_PID
wait $SENDER_PID 2>/dev/null
wait $RECEIVER_PID 2>/dev/null

echo "--- Demo Finished ---"
