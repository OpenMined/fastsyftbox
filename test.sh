#!/bin/bash

# FastSyftBox Enhanced Test Runner
# Comprehensive test execution with multiple options and configurations

set -e

# Default values
MARKERS=""
PARALLEL=""
COVERAGE_ENABLED=true
VERBOSE=""
OUTPUT_FORMAT="term"
REPORT_DIR="htmlcov"
BENCHMARK=""
TIMEOUT=""
FAIL_FAST=""
MAX_WORKERS=""
DRY_RUN=""

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
FastSyftBox Test Runner - Enhanced Edition

Usage: $0 [OPTIONS]

Test Selection Options:
  -m, --markers MARKERS      Run tests with specific markers (e.g., "unit", "integration", "not slow")
  -k EXPRESSION             Run tests matching given substring expression
  -x, --exitfirst           Stop on first failure
  --maxfail=NUM             Stop after NUM failures (default: 10)
  --lf, --last-failed       Run only tests that failed in the last run
  --ff, --failed-first      Run failed tests first, then the rest

Performance Options:
  -n, --parallel NUM        Run tests in parallel with NUM processes (auto for CPU count)
  --benchmark               Enable performance benchmarking
  --timeout SECONDS         Set test timeout (default: 300 seconds)

Coverage Options:
  --no-coverage            Disable coverage reporting
  --coverage-format FORMAT Coverage report format: term, html, xml, json, all (default: term)
  --coverage-fail-under N  Fail if coverage is under N percent (default: 80)

Output Options:
  -v, --verbose            Verbose output
  -q, --quiet              Quiet output
  --tb=STYLE               Traceback style: auto, long, short, line, native, no (default: short)
  --html FILENAME          Generate HTML report
  --json FILENAME          Generate JSON report

Test Types:
  --unit                   Run only unit tests
  --integration            Run only integration tests
  --performance            Run only performance tests
  --smoke                  Run only smoke tests
  --slow                   Run only slow tests
  --quick                  Run tests excluding slow ones
  --api                    Run only API tests
  --cli                    Run only CLI tests

Development Options:
  --dry-run                Show what would be executed without running
  --install-deps           Force reinstall dev dependencies
  --clean                  Clean previous test artifacts
  --debug                  Enable debug mode with extra logging

Examples:
  $0                       # Run all tests with coverage
  $0 --unit                # Run only unit tests
  $0 -m "not slow"         # Run all tests except slow ones
  $0 --parallel auto       # Run tests in parallel
  $0 --no-coverage -v      # Run tests without coverage, verbose
  $0 --benchmark           # Run with performance benchmarking
  $0 --smoke --quick       # Run smoke tests, excluding slow tests
  $0 --coverage-format all # Generate all coverage report formats

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -m|--markers)
            MARKERS="$2"
            shift 2
            ;;
        -k)
            EXPRESSION="-k $2"
            shift 2
            ;;
        -x|--exitfirst)
            FAIL_FAST="--exitfirst"
            shift
            ;;
        --maxfail)
            MAX_FAIL="--maxfail=$2"
            shift 2
            ;;
        --lf|--last-failed)
            LAST_FAILED="--lf"
            shift
            ;;
        --ff|--failed-first)
            FAILED_FIRST="--ff"
            shift
            ;;
        -n|--parallel)
            PARALLEL="-n $2"
            shift 2
            ;;
        --benchmark)
            BENCHMARK="--benchmark-only --benchmark-sort=mean"
            shift
            ;;
        --timeout)
            TIMEOUT="--timeout=$2"
            shift 2
            ;;
        --no-coverage)
            COVERAGE_ENABLED=false
            shift
            ;;
        --coverage-format)
            OUTPUT_FORMAT="$2"
            shift 2
            ;;
        --coverage-fail-under)
            COVERAGE_FAIL_UNDER="--cov-fail-under=$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        -q|--quiet)
            VERBOSE="-q"
            shift
            ;;
        --tb)
            TRACEBACK="--tb=$2"
            shift 2
            ;;
        --html)
            HTML_REPORT="--html=$2"
            shift 2
            ;;
        --json)
            JSON_REPORT="--json-report --json-report-file=$2"
            shift 2
            ;;
        --unit)
            MARKERS="${MARKERS:+$MARKERS and }unit"
            shift
            ;;
        --integration)
            MARKERS="${MARKERS:+$MARKERS and }integration"
            shift
            ;;
        --performance)
            MARKERS="${MARKERS:+$MARKERS and }performance"
            shift
            ;;
        --smoke)
            MARKERS="${MARKERS:+$MARKERS and }smoke"
            shift
            ;;
        --slow)
            MARKERS="${MARKERS:+$MARKERS and }slow"
            shift
            ;;
        --quick)
            MARKERS="${MARKERS:+$MARKERS and }not slow"
            shift
            ;;
        --api)
            MARKERS="${MARKERS:+$MARKERS and }api"
            shift
            ;;
        --cli)
            MARKERS="${MARKERS:+$MARKERS and }cli"
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --install-deps)
            INSTALL_DEPS=true
            shift
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        --debug)
            DEBUG=true
            shift
            ;;
        *)
            print_color $RED "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Clean previous artifacts if requested
if [[ "$CLEAN" == "true" ]]; then
    print_color $YELLOW "🧹 Cleaning previous test artifacts..."
    rm -rf htmlcov/ .coverage coverage.xml coverage.json .pytest_cache/ test-results/
fi

# Install or sync dev dependencies
if [[ "$INSTALL_DEPS" == "true" ]] || ! uv show pytest &>/dev/null; then
    print_color $BLUE "🔧 Installing dev dependencies..."
    uv sync --extra dev
else
    print_color $CYAN "📦 Dev dependencies already installed, skipping..."
fi

# Build pytest command
PYTEST_CMD="uv run pytest tests/"

# Add verbose/quiet options
if [[ -n "$VERBOSE" ]]; then
    PYTEST_CMD="$PYTEST_CMD $VERBOSE"
fi

# Add traceback style
if [[ -n "$TRACEBACK" ]]; then
    PYTEST_CMD="$PYTEST_CMD $TRACEBACK"
else
    PYTEST_CMD="$PYTEST_CMD --tb=short"
fi

# Add markers
if [[ -n "$MARKERS" ]]; then
    PYTEST_CMD="$PYTEST_CMD -m \"$MARKERS\""
fi

# Add expression filter
if [[ -n "$EXPRESSION" ]]; then
    PYTEST_CMD="$PYTEST_CMD $EXPRESSION"
fi

# Add failure handling options
if [[ -n "$FAIL_FAST" ]]; then
    PYTEST_CMD="$PYTEST_CMD $FAIL_FAST"
fi

if [[ -n "$MAX_FAIL" ]]; then
    PYTEST_CMD="$PYTEST_CMD $MAX_FAIL"
fi

if [[ -n "$LAST_FAILED" ]]; then
    PYTEST_CMD="$PYTEST_CMD $LAST_FAILED"
fi

if [[ -n "$FAILED_FIRST" ]]; then
    PYTEST_CMD="$PYTEST_CMD $FAILED_FIRST"
fi

# Add parallel execution
if [[ -n "$PARALLEL" ]]; then
    PYTEST_CMD="$PYTEST_CMD $PARALLEL"
fi

# Add timeout
if [[ -n "$TIMEOUT" ]]; then
    PYTEST_CMD="$PYTEST_CMD $TIMEOUT"
fi

# Add benchmark
if [[ -n "$BENCHMARK" ]]; then
    PYTEST_CMD="$PYTEST_CMD $BENCHMARK"
fi

# Add coverage options
if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    PYTEST_CMD="$PYTEST_CMD --cov=fastsyftbox --cov-branch"
    
    case "$OUTPUT_FORMAT" in
        term)
            PYTEST_CMD="$PYTEST_CMD --cov-report=term-missing"
            ;;
        html)
            PYTEST_CMD="$PYTEST_CMD --cov-report=html:$REPORT_DIR"
            ;;
        xml)
            PYTEST_CMD="$PYTEST_CMD --cov-report=xml"
            ;;
        json)
            PYTEST_CMD="$PYTEST_CMD --cov-report=json"
            ;;
        all)
            PYTEST_CMD="$PYTEST_CMD --cov-report=term-missing --cov-report=html:$REPORT_DIR --cov-report=xml --cov-report=json"
            ;;
    esac
    
    if [[ -n "$COVERAGE_FAIL_UNDER" ]]; then
        PYTEST_CMD="$PYTEST_CMD $COVERAGE_FAIL_UNDER"
    fi
fi

# Add HTML report
if [[ -n "$HTML_REPORT" ]]; then
    PYTEST_CMD="$PYTEST_CMD $HTML_REPORT"
fi

# Add JSON report
if [[ -n "$JSON_REPORT" ]]; then
    PYTEST_CMD="$PYTEST_CMD $JSON_REPORT"
fi

# Add debug options
if [[ "$DEBUG" == "true" ]]; then
    PYTEST_CMD="$PYTEST_CMD --capture=no --log-cli-level=DEBUG"
fi

# Show command if dry run
if [[ "$DRY_RUN" == "true" ]]; then
    print_color $PURPLE "🔍 Dry run - would execute:"
    echo "$PYTEST_CMD"
    exit 0
fi

# Show what we're running
print_color $GREEN "🧪 Running tests..."
if [[ -n "$MARKERS" ]]; then
    print_color $CYAN "   📋 Markers: $MARKERS"
fi
if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    print_color $CYAN "   📊 Coverage: $OUTPUT_FORMAT format"
fi
if [[ -n "$PARALLEL" ]]; then
    print_color $CYAN "   ⚡ Parallel: $PARALLEL"
fi

# Execute the test command
eval $PYTEST_CMD
TEST_EXIT_CODE=$?

# Show results
if [[ $TEST_EXIT_CODE -eq 0 ]]; then
    print_color $GREEN "✅ All tests passed!"
    if [[ "$COVERAGE_ENABLED" == "true" && ("$OUTPUT_FORMAT" == "html" || "$OUTPUT_FORMAT" == "all") ]]; then
        print_color $CYAN "📊 Coverage report generated in $REPORT_DIR/"
    fi
else
    print_color $RED "❌ Some tests failed (exit code: $TEST_EXIT_CODE)"
fi

# Show additional reports generated
if [[ -f "coverage.xml" ]]; then
    print_color $CYAN "📄 XML coverage report: coverage.xml"
fi
if [[ -f "coverage.json" ]]; then
    print_color $CYAN "📄 JSON coverage report: coverage.json"
fi

exit $TEST_EXIT_CODE