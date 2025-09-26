#!/usr/bin/env python3
"""
Comprehensive test runner for AWS SAM CLI PR #8272
Runs all test suites and analyzes results for errors
"""

import subprocess
import sys
import os
import re
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import time

class TestRunner:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.results = {}
        self.start_time = datetime.now()
        self.log_dir = Path("test_logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # Color codes for terminal output
        self.COLORS = {
            'GREEN': '\033[92m',
            'YELLOW': '\033[93m',
            'RED': '\033[91m',
            'BLUE': '\033[94m',
            'CYAN': '\033[96m',
            'RESET': '\033[0m',
            'BOLD': '\033[1m'
        }
    
    def print_colored(self, text: str, color: str = 'RESET', bold: bool = False):
        """Print colored text to terminal"""
        color_code = self.COLORS.get(color, self.COLORS['RESET'])
        bold_code = self.COLORS['BOLD'] if bold else ''
        print(f"{bold_code}{color_code}{text}{self.COLORS['RESET']}")
    
    def print_header(self, text: str):
        """Print a section header"""
        self.print_colored(f"\n{'='*80}", 'CYAN')
        self.print_colored(f"  {text}", 'CYAN', bold=True)
        self.print_colored(f"{'='*80}\n", 'CYAN')
    
    def run_command(self, cmd: List[str], description: str, timeout: int = 300) -> Tuple[int, str, str]:
        """Run a command and capture output"""
        self.print_colored(f"Running: {description}", 'BLUE')
        self.print_colored(f"Command: {' '.join(cmd)}", 'YELLOW')
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd()
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self.print_colored(f"Command timed out after {timeout} seconds", 'RED')
            return -1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            self.print_colored(f"Error running command: {e}", 'RED')
            return -1, "", str(e)
    
    def save_log(self, test_name: str, stdout: str, stderr: str):
        """Save test output to log files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"{test_name}_{timestamp}.log"
        
        with open(log_file, 'w') as f:
            f.write(f"Test: {test_name}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"{'='*80}\n\n")
            f.write("STDOUT:\n")
            f.write(stdout)
            f.write("\n\nSTDERR:\n")
            f.write(stderr)
        
        return log_file
    
    def analyze_output(self, stdout: str, stderr: str) -> Dict:
        """Analyze test output for errors and warnings"""
        analysis = {
            'errors': [],
            'warnings': [],
            'failed_tests': [],
            'failed_tests_detailed': [],
            'passed_tests': 0,
            'failed_count': 0,
            'skipped_count': 0,
            'error_patterns': [],
            'coverage_info': {},
            'make_failures': []
        }
        
        # Combine stdout and stderr for analysis
        full_output = stdout + "\n" + stderr
        
        # Look for pytest summary and collection issues
        if "passed" in full_output or "failed" in full_output or "collected" in full_output:
            # Extract pytest statistics
            stats_match = re.search(r'(\d+) passed', full_output)
            if stats_match:
                analysis['passed_tests'] = int(stats_match.group(1))
            
            stats_match = re.search(r'(\d+) failed', full_output)
            if stats_match:
                analysis['failed_count'] = int(stats_match.group(1))
            
            stats_match = re.search(r'(\d+) skipped', full_output)
            if stats_match:
                analysis['skipped_count'] = int(stats_match.group(1))
        
        # Check for collection issues
        if "collected 0 items" in full_output:
            analysis['collection_issue'] = "No tests collected"
            if "no tests ran" in full_output:
                analysis['collection_reason'] = "No tests found to run"
        
        # Check for skip reasons
        skip_patterns = [
            r'SKIPPED.*?(\[.*?\])',
            r'@skipIf.*?(\(.*?\))',
            r'Skip.*?because (.*)',
            r'Skipping.*?due to (.*)'
        ]
        
        for pattern in skip_patterns:
            for match in re.finditer(pattern, full_output, re.IGNORECASE):
                if 'skip_reasons' not in analysis:
                    analysis['skip_reasons'] = []
                analysis['skip_reasons'].append(match.group(1) if match.groups() else match.group(0))
        
        # Find detailed test failures with reasons
        lines = full_output.split('\n')
        current_failure = None
        collecting_failure = False
        
        for i, line in enumerate(lines):
            # Start of a test failure
            if line.startswith('FAILED '):
                match = re.match(r'FAILED (.*?) - (.*)', line)
                if match:
                    test_name = match.group(1)
                    reason = match.group(2) if match.group(2) else "Unknown reason"
                    current_failure = {
                        'test': test_name,
                        'reason': reason,
                        'details': [],
                        'traceback': []
                    }
                    analysis['failed_tests'].append(test_name)
                    collecting_failure = True
            
            # Collect failure details
            elif collecting_failure and current_failure:
                # Look for assertion errors, exceptions, etc.
                if any(keyword in line for keyword in ['AssertionError', 'Exception', 'Error:', 'Traceback']):
                    current_failure['details'].append(line.strip())
                elif line.strip().startswith('E '):
                    current_failure['details'].append(line.strip())
                elif line.strip().startswith('>'):
                    current_failure['traceback'].append(line.strip())
                elif line.startswith('=') or line.startswith('_') or (i < len(lines) - 1 and lines[i+1].startswith('FAILED')):
                    # End of current failure
                    if current_failure:
                        analysis['failed_tests_detailed'].append(current_failure)
                    current_failure = None
                    collecting_failure = False
        
        # Add last failure if we were collecting
        if current_failure:
            analysis['failed_tests_detailed'].append(current_failure)
        
        # Look for coverage information
        coverage_match = re.search(r'TOTAL.*?(\d+)%', full_output)
        if coverage_match:
            analysis['coverage_info']['total'] = coverage_match.group(1)
        
        coverage_fail_match = re.search(r'FAIL Required test coverage of (\d+)% not reached\. Total coverage: ([\d.]+)%', full_output)
        if coverage_fail_match:
            analysis['coverage_info']['required'] = coverage_fail_match.group(1)
            analysis['coverage_info']['actual'] = coverage_fail_match.group(2)
            analysis['coverage_info']['failed'] = True
        
        # Look for make pr specific failures
        make_patterns = [
            r'make: \*\*\* \[(.*?)\] Error (\d+)',
            r'Error: (.*)',
            r'FAIL (.*)',
            r'black.*would reformat (\d+) files?',
            r'flake8.*(\d+) error',
            r'mypy.*error'
        ]
        
        for pattern in make_patterns:
            for match in re.finditer(pattern, full_output, re.IGNORECASE):
                analysis['make_failures'].append({
                    'pattern': pattern,
                    'match': match.group(0),
                    'groups': match.groups()
                })
        
        # Look for warnings
        warning_patterns = [
            r'Warning: (.*)',
            r'WARN: (.*)',
            r'ResourceWarning: (.*)',
            r'DeprecationWarning: (.*)'
        ]
        
        for pattern in warning_patterns:
            for match in re.finditer(pattern, full_output, re.IGNORECASE):
                analysis['warnings'].append({
                    'type': pattern.split(':')[0].replace('r\'', ''),
                    'message': match.group(1) if match.groups() else match.group(0)
                })
        
        # Look for import/module errors
        import_errors = []
        for match in re.finditer(r'(ImportError|ModuleNotFoundError): (.*)', full_output):
            import_errors.append({
                'type': match.group(1),
                'message': match.group(2)
            })
        analysis['import_errors'] = import_errors
        
        return analysis
    
    def run_unit_tests(self):
        """Run unit tests for start-function-urls"""
        self.print_header("UNIT TESTS - start-function-urls")
        
        cmd = [
            "python", "-m", "pytest",
            "tests/unit/commands/local/start_function_urls/",
            "-v", "--tb=short", "--no-header", "--no-summary"
        ]
        
        returncode, stdout, stderr = self.run_command(cmd, "Unit Tests", timeout=120)
        
        log_file = self.save_log("unit_tests", stdout, stderr)
        analysis = self.analyze_output(stdout, stderr)
        
        self.results['unit_tests'] = {
            'returncode': returncode,
            'log_file': str(log_file),
            'analysis': analysis,
            'success': returncode == 0
        }
        
        # Print summary
        if returncode == 0:
            self.print_colored(f"✓ Unit tests passed ({analysis['passed_tests']} tests)", 'GREEN')
        else:
            self.print_colored(f"✗ Unit tests failed ({analysis['failed_count']} failures)", 'RED')
            if analysis['failed_tests_detailed']:
                self.print_colored("Failed tests:", 'YELLOW')
                for failure in analysis['failed_tests_detailed'][:3]:  # Show first 3
                    print(f"  - {failure['test']}: {failure['reason']}")
                if len(analysis['failed_tests_detailed']) > 3:
                    print(f"  ... and {len(analysis['failed_tests_detailed']) - 3} more")
    
    def run_integration_tests(self):
        """Run integration tests for start-function-urls"""
        self.print_header("INTEGRATION TESTS - start-function-urls")
        
        # Run CDK tests
        self.print_colored("\n→ Running CDK integration tests...", 'BLUE')
        cmd = [
            "python", "-m", "pytest",
            "tests/integration/local/start_function_urls/test_start_function_urls_cdk.py",
            "-v", "--tb=short", "--no-header", "-x"  # Stop on first failure
        ]
        
        returncode_cdk, stdout_cdk, stderr_cdk = self.run_command(cmd, "CDK Integration Tests", timeout=600)
        log_file_cdk = self.save_log("integration_tests_cdk", stdout_cdk, stderr_cdk)
        analysis_cdk = self.analyze_output(stdout_cdk, stderr_cdk)
        
        # Run CloudFormation tests (formerly Terraform)
        self.print_colored("\n→ Running CloudFormation integration tests...", 'BLUE')
        cmd = [
            "python", "-m", "pytest",
            "tests/integration/local/start_function_urls/test_start_function_urls_cloudformation.py",
            "-v", "--tb=short", "--no-header", "-x"
        ]
        
        returncode_cf, stdout_cf, stderr_cf = self.run_command(cmd, "CloudFormation Integration Tests", timeout=600)
        log_file_cf = self.save_log("integration_tests_cloudformation", stdout_cf, stderr_cf)
        analysis_cf = self.analyze_output(stdout_cf, stderr_cf)
        
        # Run SAM template tests
        self.print_colored("\n→ Running SAM template integration tests...", 'BLUE')
        cmd = [
            "python", "-m", "pytest",
            "tests/integration/local/start_function_urls/test_start_function_urls_sam_templates.py",
            "-v", "--tb=short", "--no-header", "-x"
        ]
        
        returncode_sam, stdout_sam, stderr_sam = self.run_command(cmd, "SAM Integration Tests", timeout=600)
        log_file_sam = self.save_log("integration_tests_sam", stdout_sam, stderr_sam)
        analysis_sam = self.analyze_output(stdout_sam, stderr_sam)
        
        # Aggregate results
        total_passed = analysis_cdk['passed_tests'] + analysis_cf['passed_tests'] + analysis_sam['passed_tests']
        total_failed = analysis_cdk['failed_count'] + analysis_cf['failed_count'] + analysis_sam['failed_count']
        
        self.results['integration_tests'] = {
            'cdk': {
                'returncode': returncode_cdk,
                'log_file': str(log_file_cdk),
                'analysis': analysis_cdk,
                'success': returncode_cdk == 0
            },
            'cloudformation': {
                'returncode': returncode_cf,
                'log_file': str(log_file_cf),
                'analysis': analysis_cf,
                'success': returncode_cf == 0
            },
            'sam': {
                'returncode': returncode_sam,
                'log_file': str(log_file_sam),
                'analysis': analysis_sam,
                'success': returncode_sam == 0
            },
            'total_passed': total_passed,
            'total_failed': total_failed,
            'success': all([returncode_cdk == 0, returncode_cf == 0, returncode_sam == 0])
        }
        
        # Print summary
        if self.results['integration_tests']['success']:
            self.print_colored(f"✓ All integration tests passed ({total_passed} tests)", 'GREEN')
        else:
            self.print_colored(f"✗ Integration tests failed ({total_failed} failures)", 'RED')
    
    def run_make_pr(self):
        """Run make pr command"""
        self.print_header("MAKE PR - Full PR Validation")
        
        cmd = ["make", "pr"]
        
        returncode, stdout, stderr = self.run_command(cmd, "Make PR", timeout=1800)  # 30 minutes timeout
        
        log_file = self.save_log("make_pr", stdout, stderr)
        analysis = self.analyze_output(stdout, stderr)
        
        # Check for specific make pr checks
        checks = {
            'format': 'black' in stdout or 'formatting' in stdout.lower(),
            'lint': 'flake8' in stdout or 'pylint' in stdout or 'linting' in stdout.lower(),
            'typecheck': 'mypy' in stdout or 'type' in stdout.lower(),
            'tests': 'pytest' in stdout or 'test' in stdout.lower(),
            'coverage': 'coverage' in stdout.lower(),
        }
        
        self.results['make_pr'] = {
            'returncode': returncode,
            'log_file': str(log_file),
            'analysis': analysis,
            'checks': checks,
            'success': returncode == 0
        }
        
        # Print summary
        if returncode == 0:
            self.print_colored("✓ Make PR passed all checks", 'GREEN')
        else:
            self.print_colored("✗ Make PR failed", 'RED')
            self.print_colored("Checks performed:", 'YELLOW')
            for check, found in checks.items():
                status = "✓" if found else "?"
                print(f"  {status} {check}")
            
            # Show specific failures
            if analysis.get('make_failures'):
                self.print_colored("Make failures:", 'YELLOW')
                for failure in analysis['make_failures'][:3]:
                    print(f"  - {failure['match']}")
            
            if analysis.get('coverage_info', {}).get('failed'):
                cov = analysis['coverage_info']
                self.print_colored(f"Coverage issue: {cov['actual']}% < {cov['required']}%", 'YELLOW')
    
    def run_specific_test_file(self, test_file: str):
        """Run a specific test file"""
        self.print_header(f"SPECIFIC TEST - {Path(test_file).name}")
        
        cmd = ["python", "-m", "pytest", test_file, "-v", "--tb=short"]
        
        returncode, stdout, stderr = self.run_command(cmd, f"Specific test: {test_file}", timeout=300)
        
        log_file = self.save_log(f"specific_{Path(test_file).stem}", stdout, stderr)
        analysis = self.analyze_output(stdout, stderr)
        
        return {
            'returncode': returncode,
            'log_file': str(log_file),
            'analysis': analysis,
            'success': returncode == 0
        }
    
    def generate_report(self):
        """Generate a comprehensive test report"""
        self.print_header("TEST REPORT SUMMARY")
        
        report = {
            'timestamp': self.start_time.isoformat(),
            'duration': str(datetime.now() - self.start_time),
            'results': self.results,
            'overall_success': all(r.get('success', False) for r in self.results.values())
        }
        
        # Save JSON report
        report_file = self.log_dir / f"test_report_{self.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Print summary
        self.print_colored("Test Suite Results:", 'CYAN', bold=True)
        print()
        
        for test_suite, result in self.results.items():
            if isinstance(result, dict) and 'success' in result:
                status = "✓ PASS" if result['success'] else "✗ FAIL"
                color = 'GREEN' if result['success'] else 'RED'
                self.print_colored(f"  {test_suite:30} {status}", color)
                
                # Show error count if failed
                if not result['success'] and 'analysis' in result:
                    analysis = result['analysis']
                    if analysis.get('failed_count'):
                        print(f"    → {analysis['failed_count']} test(s) failed")
                    if analysis.get('make_failures'):
                        print(f"    → {len(analysis['make_failures'])} make failure(s)")
                    if analysis.get('coverage_info', {}).get('failed'):
                        cov = analysis['coverage_info']
                        print(f"    → Coverage: {cov['actual']}% (required: {cov['required']}%)")
        
        print()
        self.print_colored(f"Report saved to: {report_file}", 'BLUE')
        self.print_colored(f"Log directory: {self.log_dir}", 'BLUE')
        
        # Overall status
        print()
        if report['overall_success']:
            self.print_colored("✓ ALL TESTS PASSED!", 'GREEN', bold=True)
        else:
            self.print_colored("✗ SOME TESTS FAILED - Review logs for details", 'RED', bold=True)
            self.print_detailed_failures()
        
        return report
    
    def print_detailed_failures(self):
        """Print detailed failure information"""
        self.print_colored("\n" + "="*80, 'RED')
        self.print_colored("DETAILED FAILURE ANALYSIS", 'RED', bold=True)
        self.print_colored("="*80, 'RED')
        
        failure_count = 0
        
        for test_suite, result in self.results.items():
            if isinstance(result, dict) and not result.get('success', True):
                failure_count += 1
                self.print_colored(f"\n{failure_count}. {test_suite.upper()}", 'RED', bold=True)
                
                if 'analysis' not in result:
                    continue
                    
                analysis = result['analysis']
                
                # Print failed tests with detailed reasons
                if analysis.get('failed_tests_detailed'):
                    self.print_colored("\n   Failed Tests:", 'YELLOW')
                    for i, failure in enumerate(analysis['failed_tests_detailed'][:10], 1):  # Show up to 10
                        print(f"\n   {i}. {failure['test']}")
                        print(f"      Reason: {failure['reason']}")
                        
                        if failure['details']:
                            print(f"      Details:")
                            for detail in failure['details'][:3]:  # Show first 3 details
                                print(f"        {detail}")
                        
                        if failure['traceback']:
                            print(f"      Traceback:")
                            for tb in failure['traceback'][:2]:  # Show first 2 traceback lines
                                print(f"        {tb}")
                
                # Print make failures
                if analysis.get('make_failures'):
                    self.print_colored("\n   Make Failures:", 'YELLOW')
                    for i, failure in enumerate(analysis['make_failures'][:5], 1):
                        print(f"   {i}. {failure['match']}")
                
                # Print coverage issues
                if analysis.get('coverage_info', {}).get('failed'):
                    cov = analysis['coverage_info']
                    self.print_colored("\n   Coverage Issue:", 'YELLOW')
                    print(f"      Required: {cov['required']}%")
                    print(f"      Actual: {cov['actual']}%")
                    print(f"      Gap: {float(cov['required']) - float(cov['actual']):.2f}%")
                
                # Print collection issues
                if analysis.get('collection_issue'):
                    self.print_colored("\n   Collection Issue:", 'YELLOW')
                    print(f"      Issue: {analysis['collection_issue']}")
                    if analysis.get('collection_reason'):
                        print(f"      Reason: {analysis['collection_reason']}")
                
                # Print skip reasons
                if analysis.get('skip_reasons'):
                    self.print_colored("\n   Skip Reasons:", 'YELLOW')
                    for i, reason in enumerate(analysis['skip_reasons'][:3], 1):
                        print(f"   {i}. {reason}")
                
                # Print import errors
                if analysis.get('import_errors'):
                    self.print_colored("\n   Import Errors:", 'YELLOW')
                    for i, error in enumerate(analysis['import_errors'][:3], 1):
                        print(f"   {i}. {error['type']}: {error['message']}")
                
                # Print warnings (first few)
                if analysis.get('warnings'):
                    self.print_colored("\n   Warnings:", 'YELLOW')
                    for i, warning in enumerate(analysis['warnings'][:3], 1):
                        if isinstance(warning, dict):
                            print(f"   {i}. {warning['type']}: {warning['message']}")
                        else:
                            print(f"   {i}. {warning}")
        
        if failure_count == 0:
            self.print_colored("\nNo detailed failure information available.", 'YELLOW')

def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run comprehensive tests for AWS SAM CLI PR #8272')
    parser.add_argument('--unit', action='store_true', help='Run unit tests only')
    parser.add_argument('--integration', action='store_true', help='Run integration tests only')
    parser.add_argument('--make-pr', action='store_true', help='Run make pr only')
    parser.add_argument('--specific', type=str, help='Run specific test file')
    parser.add_argument('--all', action='store_true', help='Run all tests (default)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Default to running all tests if no specific option is given
    if not any([args.unit, args.integration, args.make_pr, args.specific]):
        args.all = True
    
    runner = TestRunner(verbose=args.verbose)
    
    try:
        if args.all or args.unit:
            runner.run_unit_tests()
        
        if args.all or args.integration:
            runner.run_integration_tests()
        
        if args.all or args.make_pr:
            runner.run_make_pr()
        
        if args.specific:
            result = runner.run_specific_test_file(args.specific)
            runner.results['specific_test'] = result
        
        # Generate report
        report = runner.generate_report()
        
        # Exit with appropriate code
        sys.exit(0 if report['overall_success'] else 1)
        
    except KeyboardInterrupt:
        runner.print_colored("\n\nTests interrupted by user", 'YELLOW')
        sys.exit(1)
    except Exception as e:
        runner.print_colored(f"\n\nUnexpected error: {e}", 'RED')
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
