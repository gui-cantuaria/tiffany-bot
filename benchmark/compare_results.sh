#!/bin/bash
# compare_results.sh - Compare Benchmark Results

DIR1=$1
DIR2=$2

if [ -z "$DIR1" ] || [ -z "$DIR2" ]; then
    echo "Usage: $0 <hostinger_results_dir> <hetzner_results_dir>"
    exit 1
fi

echo "# Benchmark Comparison Report"
echo "Comparing $DIR1 vs $DIR2"
echo ""

for type in hardware network failure deploy; do
    f1=$(ls $DIR1/${type}_*.json 2>/dev/null | head -n 1)
    f2=$(ls $DIR2/${type}_*.json 2>/dev/null | head -n 1)
    
    if [ -f "$f1" ] && [ -f "$f2" ]; then
        echo "## $type Results"
        echo "Found results for $type in both providers."
        echo '```json'
        # Basic diff/jq output - for a real environment this could use a python parser
        jq -s '.[0] as $h1 | .[1] as $h2 | {provider1: $h1.provider, provider2: $h2.provider}' "$f1" "$f2"
        echo '```'
    fi
done

echo "Comparison complete."
