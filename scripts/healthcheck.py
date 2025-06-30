#!/usr/bin/env python3
"""
Advanced health check script for Palworld server
Comprehensive server health monitoring with multiple check layers
"""

import sys
import asyncio
import aiohttp
import os
import time
import json
import subprocess
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


current_dir = Path(__file__).parent  # /app/scripts
project_root = current_dir.parent    # /app
src_dir = project_root / "src"       # /app/src

sys.path.insert(0, str(src_dir))


try:
    from config_loader import get_config
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    print("Warning: config_loader not available, using defaults")


class HealthStatus(Enum):
    """Health check status levels"""
    HEALTHY = "healthy"
    WARNING = "warning"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


@dataclass
class HealthCheckResult:
    """Health check result data structure"""
    component: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    response_time_ms: float
    timestamp: float


class HealthChecker:
    """Advanced health checker for Palworld server"""
    
    def __init__(self):
        
        if CONFIG_AVAILABLE:
            try:
                config = get_config()
                self.rest_api_host = config.rest_api.host
                self.rest_api_port = config.rest_api.port
                self.rcon_host = config.rcon.host
                self.rcon_port = config.rcon.port
                self.rcon_password = config.server.admin_password
            except Exception as e:
                print(f"Config load error: {e}, using defaults")
                self._use_defaults()
        else:
            self._use_defaults()
        
        self.timeout = 10
        self.results: List[HealthCheckResult] = []
    
    def _use_defaults(self):
        """Use default values when config is not available"""
        self.rest_api_host = os.getenv('REST_API_HOST', 'host.docker.internal')
        self.rest_api_port = int(os.getenv('REST_API_PORT', '8212'))
        self.rcon_host = os.getenv('RCON_HOST', 'host.docker.internal')
        self.rcon_port = int(os.getenv('RCON_PORT', '25575'))
        self.rcon_password = os.getenv('ADMIN_PASSWORD', 'admin123')
    
    async def check_rest_api_health(self) -> HealthCheckResult:
        """Check REST API health with configurable host"""
        start_time = time.time()
        component = "rest_api"
        
        try:
            async with aiohttp.ClientSession() as session:
                
                endpoints = [
                    f'http://{self.rest_api_host}:{self.rest_api_port}/v1/api/info',
                    f'http://{self.rest_api_host}:{self.rest_api_port}/health'
                ]
                
                for url in endpoints:
                    try:
                        async with session.get(url, timeout=self.timeout) as resp:
                            response_time = (time.time() - start_time) * 1000
                            
                            if resp.status == 200:
                                try:
                                    data = await resp.json()
                                    return HealthCheckResult(
                                        component=component,
                                        status=HealthStatus.HEALTHY,
                                        message="REST API responding normally",
                                        details={
                                            "endpoint": url,
                                            "status_code": resp.status,
                                            "response_data": data
                                        },
                                        response_time_ms=response_time,
                                        timestamp=time.time()
                                    )
                                except:
                                    return HealthCheckResult(
                                        component=component,
                                        status=HealthStatus.WARNING,
                                        message="REST API responding but invalid JSON",
                                        details={
                                            "endpoint": url,
                                            "status_code": resp.status
                                        },
                                        response_time_ms=response_time,
                                        timestamp=time.time()
                                    )
                            else:
                                return HealthCheckResult(
                                    component=component,
                                    status=HealthStatus.WARNING,
                                    message=f"REST API returned status {resp.status}",
                                    details={
                                        "endpoint": url,
                                        "status_code": resp.status
                                    },
                                    response_time_ms=response_time,
                                    timestamp=time.time()
                                )
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        continue
                
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.UNHEALTHY,
                    message="REST API not responding",
                    details={
                        "tested_endpoints": endpoints,
                        "host_used": self.rest_api_host
                    },
                    response_time_ms=(time.time() - start_time) * 1000,
                    timestamp=time.time()
                )
                
        except Exception as e:
            return HealthCheckResult(
                component=component,
                status=HealthStatus.CRITICAL,
                message=f"REST API check failed: {str(e)}",
                details={"error": str(e)},
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=time.time()
            )
    
    async def check_rcon_health(self) -> HealthCheckResult:
        """Check RCON server health"""
        start_time = time.time()
        component = "rcon"
        
        try:
            
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.rcon_host, self.rcon_port),
                timeout=5
            )
            writer.close()
            await writer.wait_closed()
            
            response_time = (time.time() - start_time) * 1000
            
            return HealthCheckResult(
                component=component,
                status=HealthStatus.HEALTHY,
                message="RCON port accessible",
                details={
                    "host": self.rcon_host,
                    "port": self.rcon_port
                },
                response_time_ms=response_time,
                timestamp=time.time()
            )
            
        except Exception as e:
            return HealthCheckResult(
                component=component,
                status=HealthStatus.UNHEALTHY,
                message=f"RCON port {self.rcon_port} not accessible",
                details={
                    "host": self.rcon_host,
                    "port": self.rcon_port,
                    "error": str(e)
                },
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=time.time()
            )
    
    async def run_all_checks(self) -> List[HealthCheckResult]:
        """Run all health checks"""
        checks = [
            self.check_rest_api_health(),
            self.check_rcon_health()
        ]
        
        self.results = await asyncio.gather(*checks, return_exceptions=True)
        
        # Handle exceptions
        final_results = []
        for i, result in enumerate(self.results):
            if isinstance(result, Exception):
                final_results.append(HealthCheckResult(
                    component=f"check_{i}",
                    status=HealthStatus.CRITICAL,
                    message=f"Health check failed: {str(result)}",
                    details={"error": str(result)},
                    response_time_ms=0,
                    timestamp=time.time()
                ))
            else:
                final_results.append(result)
        
        self.results = final_results
        return self.results
    
    def get_overall_status(self) -> HealthStatus:
        """Determine overall health status"""
        if not self.results:
            return HealthStatus.CRITICAL
        
        statuses = [result.status for result in self.results]
        
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        elif HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY


async def main():
    """Main health check function"""
    format_json = "--json" in sys.argv
    
    checker = HealthChecker()
    
    try:
        results = await checker.run_all_checks()
        overall_status = checker.get_overall_status()
        
        if format_json:
            print(json.dumps({
                "timestamp": time.time(),
                "overall_status": overall_status.value,
                "checks": [
                    {
                        "component": result.component,
                        "status": result.status.value,
                        "message": result.message,
                        "details": result.details,
                        "response_time_ms": result.response_time_ms
                    }
                    for result in results
                ]
            }, indent=2))
        else:
            status_emoji = {
                HealthStatus.HEALTHY: "✅",
                HealthStatus.WARNING: "⚠️",
                HealthStatus.UNHEALTHY: "❌",
                HealthStatus.CRITICAL: "🚨"
            }
            
            overall_emoji = status_emoji[overall_status]
            print(f"{overall_emoji} Overall Status: {overall_status.value.upper()}\n")
            
            for result in results:
                emoji = status_emoji[result.status]
                print(f"{emoji} {result.component}: {result.message}")
                if result.response_time_ms > 0:
                    print(f"   Response time: {result.response_time_ms:.1f}ms")
                
                # Show key details
                if result.details:
                    for key, value in result.details.items():
                        if key not in ['error', 'response_data']:
                            print(f"   {key}: {value}")
                print()
        
        return 0 if overall_status in [HealthStatus.HEALTHY, HealthStatus.WARNING] else 1
            
    except Exception as e:
        if format_json:
            print(json.dumps({"error": f"Health check failed: {str(e)}"}))
        else:
            print(f"🚨 Health check critical failure: {e}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Health check critical failure: {e}")
        sys.exit(1)
