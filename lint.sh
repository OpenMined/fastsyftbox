#!/bin/bash

# FastSyftBox Linting and Code Quality Script
# Ensures consistent code quality checks across local development and CI

set -e

# Default values
CHECK_ONLY=false
FIX=false
VERBOSE=false
FAIL_FAST=false
MYPY_STRICT=false

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_color() {
    printf "${1}${2}${NC}\n"
}

# Function to show usage
show_usage() {
    cat << EOF
FastSyftBox Linting and Code Quality Script

Usage: $0 [OPTIONS]

Options:
  -c, --check          Check mode only (don't fix issues)
  -f, --fix            Fix mode (auto-fix issues where possible)
  -v, --verbose        Verbose output
  -x, --fail-fast      Exit on first failure
  -s, --strict         Enable strict mypy checking
  -h, --help           Show this help message

Examples:
  $0                   # Run all checks with auto-fix
  $0 --check           # Check only, don't fix
  $0 --fix --verbose   # Fix with verbose output
  $0 --check --strict  # Check with strict mypy

Default behavior: Runs all checks and auto-fixes issues where possible.
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--check)
            CHECK_ONLY=true
            shift
            ;;
        -f|--fix)
            FIX=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -x|--fail-fast)
            FAIL_FAST=true
            shift
            ;;
        -s|--strict)
            MYPY_STRICT=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_color $RED "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# If neither check nor fix is specified, default to fix mode
if [[ "$CHECK_ONLY" == false && "$FIX" == false ]]; then
    FIX=true
fi

# Track overall exit status
EXIT_STATUS=0

# Function to run a command and handle errors
run_check() {
    local name=$1
    local check_cmd=$2
    local fix_cmd=$3
    
    print_color $BLUE "🔍 Running $name..."
    
    if [[ "$VERBOSE" == true ]]; then
        echo "Command: $check_cmd"
    fi
    
    # Run the check command
    if [[ "$CHECK_ONLY" == true ]] || [[ -z "$fix_cmd" ]]; then
        if eval "$check_cmd"; then
            print_color $GREEN "✅ $name passed"
        else
            print_color $RED "❌ $name failed"
            EXIT_STATUS=1
            if [[ "$FAIL_FAST" == true ]]; then
                exit $EXIT_STATUS
            fi
        fi
    else
        # Try to fix
        if [[ "$VERBOSE" == true ]]; then
            echo "Fix command: $fix_cmd"
        fi
        if eval "$fix_cmd"; then
            print_color $GREEN "✅ $name fixed/passed"
        else
            # If fix fails, run check to see the errors
            print_color $YELLOW "⚠️  $name auto-fix failed, showing errors:"
            eval "$check_cmd" || true
            EXIT_STATUS=1
            if [[ "$FAIL_FAST" == true ]]; then
                exit $EXIT_STATUS
            fi
        fi
    fi
    echo
}

# Header
print_color $PURPLE "FastSyftBox Code Quality Check"
print_color $PURPLE "=============================="
echo

# Check if uv is available
if ! command -v uv &> /dev/null; then
    print_color $RED "❌ uv is not installed. Please install it first."
    print_color $YELLOW "Visit: https://github.com/astral-sh/uv"
    exit 1
fi

# Ensure we're in a virtual environment with dev dependencies
if [[ "$VERBOSE" == true ]]; then
    print_color $CYAN "📦 Checking dependencies..."
fi

if ! uv run python -c "import ruff" &> /dev/null; then
    print_color $YELLOW "📦 Installing dev dependencies..."
    uv sync --extra dev
fi

# 1. Ruff Format Check
if [[ "$CHECK_ONLY" == true ]]; then
    run_check "Ruff Format" \
        "uv run ruff format --check ." \
        ""
else
    run_check "Ruff Format" \
        "uv run ruff format --check ." \
        "uv run ruff format ."
fi

# 2. Ruff Linter
if [[ "$CHECK_ONLY" == true ]]; then
    run_check "Ruff Linter" \
        "uv run ruff check ." \
        ""
else
    run_check "Ruff Linter" \
        "uv run ruff check ." \
        "uv run ruff check . --fix"
fi

# 3. MyPy Type Checking
MYPY_CMD="uv run mypy fastsyftbox/"
if [[ "$MYPY_STRICT" == true ]]; then
    MYPY_CMD="$MYPY_CMD --strict"
fi

# MyPy doesn't have auto-fix, so we just check
run_check "MyPy Type Check" \
    "$MYPY_CMD" \
    ""

# 4. Import sorting (via ruff)
# This is already handled by ruff check above, but we can be explicit
if [[ "$VERBOSE" == true ]]; then
    print_color $CYAN "ℹ️  Import sorting is handled by Ruff linter (I rules)"
fi

# Summary
print_color $PURPLE "=============================="
if [[ $EXIT_STATUS -eq 0 ]]; then
    print_color $GREEN "✅ All checks passed!"
    if [[ "$CHECK_ONLY" == false ]]; then
        print_color $CYAN "💡 Code has been auto-formatted where possible."
    fi
else
    print_color $RED "❌ Some checks failed!"
    if [[ "$CHECK_ONLY" == true ]]; then
        print_color $YELLOW "💡 Run '$0 --fix' to auto-fix issues where possible."
    else
        print_color $YELLOW "💡 Some issues require manual fixes."
    fi
fi

# Show next steps for common issues
if [[ $EXIT_STATUS -ne 0 ]]; then
    echo
    print_color $YELLOW "Common fixes:"
    print_color $YELLOW "- Format issues: Run 'ruff format .'"
    print_color $YELLOW "- Linting issues: Run 'ruff check . --fix'"
    print_color $YELLOW "- Type issues: Fix manually based on mypy output"
fi

exit $EXIT_STATUS