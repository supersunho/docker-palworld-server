#!/usr/bin/env python3
"""Stage 1 validation script with English comments"""

import sys
import os
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_config_loading():
    """Test configuration loading"""
    try:
        from config_loader import get_config
        config = get_config()
        print("✅ Configuration loading success")
        print(f"   Server name: {config.server.name}")
        print(f"   Max players: {config.server.max_players}")
        print(f"   Monitoring mode: {config.monitoring.mode}")
        return True
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        return False

def test_logging():
    """Test logging system"""
    try:
        from logging_setup import setup_logging, get_logger, log_server_event
        
        setup_logging(
            log_level="INFO",
            enable_console=True,
            enable_file=False
        )
        
        logger = get_logger("test")
        log_server_event(logger, "server_start", "Test server start", port=8211)
        
        print("✅ Logging system success")
        return True
    except Exception as e:
        print(f"❌ Logging system failed: {e}")
        return False

def test_environment():
    """Test environment variable substitution"""
    try:
        # Set test environment variables
        os.environ["TEST_SERVER_NAME"] = "Test Server from ENV"
        os.environ["TEST_MAX_PLAYERS"] = "16"
        
        from config_loader import ConfigLoader
        
        # Create temporary config file
        test_config = """
server:
  name: "${TEST_SERVER_NAME:Default Name}"
  max_players: ${TEST_MAX_PLAYERS:32}
"""
        
        config_path = Path("/tmp/test_config.yaml")
        config_path.write_text(test_config)
        
        loader = ConfigLoader(config_path)
        config = loader.load_config()
        
        assert config.server.name == "Test Server from ENV"
        assert config.server.max_players == 16
        
        print("✅ Environment variable substitution success")
        config_path.unlink()  # Delete temporary file
        return True
    except Exception as e:
        print(f"❌ Environment variable substitution failed: {e}")
        return False

def main():
    """Main validation function"""
    print("🚀 Stage 1 validation start\n")
    
    tests = [
        ("Configuration loading", test_config_loading),
        ("Logging system", test_logging),
        ("Environment variable substitution", test_environment),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"🔍 Testing {test_name}...")
        result = test_func()
        results.append(result)
        print()
    
    # Result summary
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"📊 Stage 1 validation result: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 Stage 1 complete! Ready to proceed to next stage.")
        return 0
    else:
        print("❌ Some tests failed. Please fix issues and retry.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
