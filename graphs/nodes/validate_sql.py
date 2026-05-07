"""
检查sql语法是否正确
验证结点：语法检查、安全检查、控制系统流程（should_retry_sql）
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from graphs.state import NL2SQLState
from graphs.utils.performance import monitor_performance

try:
    import sqlglot
    # sqlglot为验证sql语法正确性
    SQLGLOT_AVAILABLE = True
except ImportError:
    SQLGLOT_AVAILABLE = False
    print("⚠️  sqlglot not available, SQL validation will be skipped")


@monitor_performance
def validate_sql_node(state: NL2SQLState) -> NL2SQLState:
    """
    Validate SQL syntax using sqlglot.

    Args:
        state: Current NL2SQL state
        
    Returns:
        Updated state with validation results
    """
    candidate_sql = state.get("candidate_sql")
    
    print(f"\n=== Validate SQL Node (M4) ===")
    print(f"SQL: {candidate_sql}")
    
    # Initialize validation result
    validation_result = {
        "valid": False,
        "errors": [],
        "warnings": [],
        "parsed": False
    }
    
    # 检测sql是否存在
    if not candidate_sql:
        validation_result["errors"].append("No SQL query provided")
        print("✗ Validation failed: No SQL to validate")
        return {
            **state,
            "validation_result": validation_result,
            "validation_errors": validation_result["errors"],
            "validation_passed": False
        }
    
    # Check if sqlglot is available
    if not SQLGLOT_AVAILABLE:
        print("⚠️  sqlglot not available, skipping validation")
        validation_result["valid"] = True  # Assume valid if can't validate
        validation_result["warnings"].append("sqlglot not available, validation skipped")
        return {
            **state,
            "validation_result": validation_result,
            "validation_errors": [],
            "validation_passed": True
        }
    
    try:
        # Parse SQL using sqlglot
        # Try to parse as MySQL dialect
        parsed = sqlglot.parse(candidate_sql, dialect="mysql")
        
        if not parsed or len(parsed) == 0:
            validation_result["errors"].append("Failed to parse SQL: Empty result")
            print("✗ Validation failed: Empty parse result")
        else:
            # Check for parse errors
            errors = []
            for statement in parsed:
                # sqlglot returns errors in the statement object
                if hasattr(statement, 'errors') and statement.errors:
                    errors.extend(statement.errors)
            
            if errors:
                validation_result["errors"].extend([str(e) for e in errors])
                print(f"✗ Validation failed: {len(errors)} error(s) found")
                for error in errors:
                    print(f"  - {error}")
            else:
                validation_result["valid"] = True
                validation_result["parsed"] = True
                print("✓ Validation passed: SQL syntax is valid")
                
                # Additional checks
                # Check if it's a SELECT statement (safety check)
                first_stmt = parsed[0]
                if hasattr(first_stmt, 'kind'):
                    # 安全检查 如果不是select 可以防止删库
                    if first_stmt.kind.upper() != 'SELECT':
                        validation_result["warnings"].append(
                            f"Non-SELECT statement detected: {first_stmt.kind}"
                        )
                        print(f"Warning: {validation_result['warnings'][-1]}")
    
    except sqlglot.errors.ParseError as e:
        error_msg = f"SQL parse error: {str(e)}"
        validation_result["errors"].append(error_msg)
        print(f"✗ Validation failed: {error_msg}")
    
    except Exception as e:
        error_msg = f"Unexpected validation error: {str(e)}"
        validation_result["errors"].append(error_msg)
        print(f"✗ Validation failed: {error_msg}")

    # 复制旧state
    return {
        **state,
        "validation_result": validation_result,
        "validation_errors": validation_result["errors"],
        "validation_passed": validation_result["valid"]
    }


def should_retry_sql(state: NL2SQLState) -> str:
    """
    Conditional function to determine if SQL should be retried.
    
    Returns:
        "retry" 错误但可以重试
        "execute" sql正确
        "fail" if max retries exceeded 最大重试次数
    """
    validation_passed = state.get("validation_passed", False)
    regeneration_count = state.get("regeneration_count", 0)
    max_regenerations = state.get("max_regenerations", 3)
    
    if validation_passed:
        return "execute"
    
    if regeneration_count >= max_regenerations:
        print(f"✗ Max regenerations ({max_regenerations}) exceeded, stopping")
        return "fail"
    
    return "retry"
