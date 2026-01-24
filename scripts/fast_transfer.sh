#!/bin/bash

# ===================== Core Configuration =====================

# 1. Select data source mode: "docker" or "host"
SOURCE_MODE="host"

# 2. If docker mode, specify container ID or name (ignored in host mode)
CONTAINER_ID="your_container_id"

# 3. Source file/folder path
#    - docker mode: absolute path inside container
#    - host mode: absolute path on host machine
SOURCE_PATH="/C20545/math/wangzi/GenesisGeo/src/newclid/generation/datasets/0123/imgs_png/"

# 4. Remote server information
REMOTE_USER="wangzi"
REMOTE_IP="172.20.48.11"  # Target IP
REMOTE_PORT="22"          # SSH port, default 22

# 5. Remote destination directory
REMOTE_DEST_DIR="/c23474/home/wangzi/myNewclid/datasets/0123/imgs_png_a8004cards"

# 6. Compression thread configuration
#    - 0 means auto-detect and use all available CPU cores
#    - Positive integer specifies thread count (e.g., 4, 8, 16)
#    Note: zstd decompression does not support multi-threading, only compression does
COMPRESS_THREADS=50    # Local compression threads

# 7. tar packaging options
#    - "preserve": Preserve full path structure
#    - "strip": Package folder itself (imgs_png/ -> target/imgs_png/)
#    - "content": Package folder content only (imgs_png/* -> target/)
TAR_MODE="content"

# ==============================================================

# --- Color Definitions ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- Dependency Check ---
echo -e "${BLUE}=== Checking Dependencies ===${NC}"

if ! command -v pv &> /dev/null; then
    echo -e "${RED}Error: pv command not found. Please install: apt-get install pv${NC}"
    exit 1
fi
if ! command -v zstd &> /dev/null; then
    echo -e "${RED}Error: zstd command not found. Please install: apt-get install zstd${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Dependency check passed${NC}\n"

echo -e "${BLUE}=== Starting Fast Transfer Task ===${NC}"
echo -e "Mode: ${GREEN}$SOURCE_MODE${NC}"
echo -e "Source Path: $SOURCE_PATH"
echo -e "Target: $REMOTE_USER@$REMOTE_IP:$REMOTE_DEST_DIR"
echo -e "Packaging Mode: ${GREEN}$TAR_MODE${NC}"
echo -e "Compression Threads: ${GREEN}$COMPRESS_THREADS${NC} (0=auto)"

# --- Logic Branch Processing ---
if [ "$SOURCE_MODE" == "docker" ]; then
    # Docker mode check
    if [ -z "$CONTAINER_ID" ] || [ "$CONTAINER_ID" == "your_container_id" ]; then
        echo -e "${RED}Error: Docker mode requires a valid CONTAINER_ID${NC}"
        exit 1
    fi
    
    # Check if container exists
    if ! docker ps -a --format '{{.ID}} {{.Names}}' | grep -q "$CONTAINER_ID"; then
        echo -e "${RED}Error: Container $CONTAINER_ID not found${NC}"
        exit 1
    fi
    
    echo -e "Calculating file size in container [$CONTAINER_ID]..."
    
    # Construct size query command
    SIZE_CMD="docker exec $CONTAINER_ID du -sb $SOURCE_PATH"
    
    # Construct tar command based on TAR_MODE
    if [ "$TAR_MODE" == "strip" ]; then
        # Package folder itself
        SOURCE_DIR=$(dirname "$SOURCE_PATH")
        SOURCE_BASE=$(basename "$SOURCE_PATH")
        TAR_CMD="docker exec $CONTAINER_ID tar -cf - -C $SOURCE_DIR $SOURCE_BASE"
    elif [ "$TAR_MODE" == "content" ]; then
        # Package folder content only
        TAR_CMD="docker exec $CONTAINER_ID tar -cf - -C $SOURCE_PATH ."
    else
        # preserve mode: keep full path structure
        TAR_CMD="docker exec $CONTAINER_ID tar -cf - $SOURCE_PATH"
    fi

elif [ "$SOURCE_MODE" == "host" ]; then
    # Host mode check
    if [ ! -e "$SOURCE_PATH" ]; then
        echo -e "${RED}Error: Local path does not exist: $SOURCE_PATH${NC}"
        exit 1
    fi
    echo -e "Calculating file size locally..."
    
    # Construct size query command
    SIZE_CMD="du -sb $SOURCE_PATH"
    
    # Construct tar command based on TAR_MODE
    if [ "$TAR_MODE" == "strip" ]; then
        # Package folder itself
        SOURCE_DIR=$(dirname "$SOURCE_PATH")
        SOURCE_BASE=$(basename "$SOURCE_PATH")
        TAR_CMD="tar -cf - -C $SOURCE_DIR $SOURCE_BASE"
        echo -e "${YELLOW}Note: Will create $REMOTE_DEST_DIR/$SOURCE_BASE/${NC}"
    elif [ "$TAR_MODE" == "content" ]; then
        # Package folder content only
        TAR_CMD="tar -cf - -C $SOURCE_PATH ."
        echo -e "${YELLOW}Note: Files will be extracted directly to $REMOTE_DEST_DIR/${NC}"
    else
        # preserve mode: keep full path structure
        TAR_CMD="tar -cf - $SOURCE_PATH"
    fi

else
    echo -e "${RED}Configuration Error: SOURCE_MODE must be 'docker' or 'host'${NC}"
    exit 1
fi

# --- Get Total Size (for progress bar) ---
TOTAL_SIZE_BYTES=$($SIZE_CMD | awk '{print $1}')

if [ -z "$TOTAL_SIZE_BYTES" ] || [ "$TOTAL_SIZE_BYTES" -eq 0 ]; then
    echo -e "${RED}Error: Unable to get file size. Please check path permissions or container status.${NC}"
    exit 1
fi

HUMAN_SIZE=$(numfmt --to=iec-i --suffix=B "$TOTAL_SIZE_BYTES" 2>/dev/null || echo "$TOTAL_SIZE_BYTES bytes")
echo -e "Total Data Size: ${GREEN}$HUMAN_SIZE${NC}"
echo "---------------------------------------------------"

# User confirmation
read -p "Start transfer? [y/N]: " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Transfer cancelled${NC}"
    exit 0
fi

# --- Execute Core Transfer Pipeline ---
# Logic explanation:
# $TAR_CMD  -> Generate tar data stream (source can be local or container)
# pv        -> Monitor throughput and display progress based on TOTAL_SIZE_BYTES
# zstd      -> Fast compression (-1 fast mode) using specified threads (-T)
# ssh       -> Transfer and invoke remote decompression (Note: zstd decompression doesn't support multi-threading)

echo -e "${BLUE}Starting transfer...${NC}"
echo -e "${YELLOW}Note: Please enter SSH password for $REMOTE_USER@$REMOTE_IP${NC}"

$TAR_CMD | \
pv -s "$TOTAL_SIZE_BYTES" -p -t -e -r -b | \
zstd -1 -T"$COMPRESS_THREADS" | \
ssh -p "$REMOTE_PORT" "$REMOTE_USER@$REMOTE_IP" \
"mkdir -p '$REMOTE_DEST_DIR' && zstd -d | tar -xf - -C '$REMOTE_DEST_DIR'"

# --- Finish ---
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}✓ Transfer successful!${NC}"
    if [ "$TAR_MODE" == "strip" ]; then
        echo -e "Files saved to: ${GREEN}$REMOTE_USER@$REMOTE_IP:$REMOTE_DEST_DIR/$(basename "$SOURCE_PATH")${NC}"
    else
        echo -e "Files saved to: ${GREEN}$REMOTE_USER@$REMOTE_IP:$REMOTE_DEST_DIR${NC}"
    fi
else
    echo -e "\n${RED}✗ Transfer failed (exit code: $EXIT_CODE)${NC}"
    echo -e "${YELLOW}Possible causes:${NC}"
    echo "  1. Incorrect SSH password"
    echo "  2. Network connection interrupted"
    echo "  3. Insufficient remote disk space"
    echo "  4. Permission issues"
    exit $EXIT_CODE
fi