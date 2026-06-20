#!/bin/bash

# SOME/IP Multi-Publisher Demo Launcher
# This script helps you run the multi-publisher example in separate terminals

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Function to print section headers
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# Function to print instructions
print_instructions() {
    echo ""
    echo -e "${YELLOW}📋 Multi-Publisher Demo Setup Instructions${NC}"
    echo ""
    echo -e "${GREEN}This demo shows 3 independent publishers and 1 subscriber${NC}"
    echo ""
    echo -e "${BLUE}Option 1: Manual Terminal Setup (Recommended for visibility)${NC}"
    echo "  Each process runs in its own terminal window"
    echo ""
    echo -e "${YELLOW}  Terminal 1 - Temperature Publisher:${NC}"
    echo "    cd $SCRIPT_DIR"
    echo "    python publisher1_temperature.py"
    echo ""
    echo -e "${YELLOW}  Terminal 2 - Humidity Publisher:${NC}"
    echo "    cd $SCRIPT_DIR"
    echo "    python publisher2_humidity.py"
    echo ""
    echo -e "${YELLOW}  Terminal 3 - Pressure Publisher:${NC}"
    echo "    cd $SCRIPT_DIR"
    echo "    python publisher3_pressure.py"
    echo ""
    echo -e "${YELLOW}  Terminal 4 - Subscriber Aggregator:${NC}"
    echo "    cd $SCRIPT_DIR"
    echo "    python subscriber_aggregator.py"
    echo ""
    echo ""
    echo -e "${BLUE}Option 2: Quick Demo (All in one terminal)${NC}"
    echo "    bash run_demo.sh start"
    echo ""
    echo ""
}

# Function to start all processes
start_demo() {
    print_header "🚀 Starting SOME/IP Multi-Publisher Demo"
    
    echo -e "${GREEN}Starting publishers in background...${NC}"
    
    # Start publishers in background
    python publisher1_temperature.py > /tmp/pub1.log 2>&1 &
    PUB1_PID=$!
    echo -e "${GREEN}✓ Temperature Publisher started (PID: $PUB1_PID)${NC}"
    sleep 1
    
    python publisher2_humidity.py > /tmp/pub2.log 2>&1 &
    PUB2_PID=$!
    echo -e "${GREEN}✓ Humidity Publisher started (PID: $PUB2_PID)${NC}"
    sleep 1
    
    python publisher3_pressure.py > /tmp/pub3.log 2>&1 &
    PUB3_PID=$!
    echo -e "${GREEN}✓ Pressure Publisher started (PID: $PUB3_PID)${NC}"
    sleep 2
    
    echo ""
    echo -e "${YELLOW}Starting subscriber aggregator...${NC}"
    echo ""
    
    # Start subscriber in foreground
    python subscriber_aggregator.py &
    SUB_PID=$!
    
    # Wait for subscriber
    wait $SUB_PID
    
    # Cleanup
    echo ""
    echo -e "${YELLOW}Cleaning up...${NC}"
    kill $PUB1_PID 2>/dev/null || true
    kill $PUB2_PID 2>/dev/null || true
    kill $PUB3_PID 2>/dev/null || true
    
    echo -e "${GREEN}✓ Demo completed${NC}"
}

# Function to show status
show_status() {
    print_header "📊 Demo Process Status"
    
    echo -e "${YELLOW}Configuration:${NC}"
    echo "  Publisher 1 (Temperature): Service 0x1001"
    echo "  Publisher 2 (Humidity):    Service 0x1002"
    echo "  Publisher 3 (Pressure):    Service 0x1003"
    echo "  Subscriber (Aggregator):   Listens to all 3 topics"
    echo ""
    echo -e "${YELLOW}Expected Architecture:${NC}"
    echo ""
    echo "   Publisher 1        Publisher 2        Publisher 3"
    echo "      (Temp)             (Humid)           (Pressure)"
    echo "        |                  |                  |"
    echo "        └──────────────────┼──────────────────┘"
    echo "                           |"
    echo "                    SOME/IP Network"
    echo "                    224.224.224.245"
    echo "                           |"
    echo "                   Subscriber/Aggregator"
    echo ""
}

# Main menu
if [ $# -eq 0 ]; then
    print_header "SOME/IP Multi-Publisher Demo"
    print_instructions
    show_status
    
    echo -e "${YELLOW}To start the demo, use:${NC}"
    echo "  ${GREEN}bash run_demo.sh start${NC}  - Run all processes together"
    echo ""
    echo -e "${YELLOW}Or follow the manual setup instructions above for better visibility${NC}"
    echo ""
elif [ "$1" = "start" ]; then
    start_demo
elif [ "$1" = "help" ]; then
    print_instructions
    show_status
else
    echo -e "${RED}Unknown option: $1${NC}"
    echo "Usage: bash run_demo.sh [start|help]"
    exit 1
fi
