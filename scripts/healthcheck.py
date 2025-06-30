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
import subprocess  # Added for RCON support
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum


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
        from ..config_loader import get_config
        config = get_config()
        
        self.rest_api_host = config.rest_api.host
        self.rest_api_port = config.rest_api.port
        self.rcon_host = config.rcon.host
        self.rcon_port = config.rcon.port
        self.rcon_password = config.server.admin_password
        self.timeout = 10
        
        # Health check results
        self.results: List[HealthCheckResult] = []
    
    async def check_rest_api_health(self) -> HealthCheckResult:
        """Check REST API health with detailed response"""
        start_time = time.time()
        component = "rest_api"
        
        try:
            async with aiohttp.ClientSession() as session:
                # Try different endpoints
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
                                    # API responded but not with JSON
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
                
                # All endpoints failed
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.UNHEALTHY,
                    message="REST API not responding",
                    details={"tested_endpoints": endpoints},
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
    
    async def check_server_process(self) -> HealthCheckResult:
        """Check if Palworld server process is running"""
        start_time = time.time()
        component = "server_process"
        
        try:
            import psutil
            
            server_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info']):
                try:
                    proc_info = proc.info
                    if ('PalServer' in proc_info.get('name', '') or 
                        (proc_info.get('cmdline') and 
                         any('PalServer' in str(cmd) for cmd in proc_info.get('cmdline', [])))):
                        
                        # Get additional process information
                        with proc.oneshot():
                            server_processes.append({
                                "pid": proc_info['pid'],
                                "name": proc_info['name'],
                                "cpu_percent": proc.cpu_percent(),
                                "memory_mb": proc.memory_info().rss / (1024 * 1024),
                                "status": proc.status(),
                                "create_time": proc.create_time()
                            })
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            response_time = (time.time() - start_time) * 1000
            
            if server_processes:
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.HEALTHY,
                    message=f"Found {len(server_processes)} Palworld server process(es)",
                    details={"processes": server_processes},
                    response_time_ms=response_time,
                    timestamp=time.time()
                )
            else:
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.UNHEALTHY,
                    message="No Palworld server processes found",
                    details={"processes": []},
                    response_time_ms=response_time,
                    timestamp=time.time()
                )
                
        except ImportError:
            # Fallback to port checking if psutil not available
            return await self._check_port_listening()
        except Exception as e:
            return HealthCheckResult(
                component=component,
                status=HealthStatus.CRITICAL,
                message=f"Process check failed: {str(e)}",
                details={"error": str(e)},
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=time.time()
            )
    
    async def _check_port_listening(self) -> HealthCheckResult:
        """Fallback port listening check"""
        start_time = time.time()
        component = "server_port"
        
        try:
            import socket
            
            # Check if server port is listening
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            result = sock.connect_ex(('localhost', self.server_port))
            sock.close()
            
            response_time = (time.time() - start_time) * 1000
            
            if result == 0:
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.HEALTHY,
                    message=f"Server port {self.server_port} is listening",
                    details={"port": self.server_port, "protocol": "UDP"},
                    response_time_ms=response_time,
                    timestamp=time.time()
                )
            else:
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Server port {self.server_port} not listening",
                    details={"port": self.server_port, "protocol": "UDP"},
                    response_time_ms=response_time,
                    timestamp=time.time()
                )
                
        except Exception as e:
            return HealthCheckResult(
                component=component,
                status=HealthStatus.CRITICAL,
                message=f"Port check failed: {str(e)}",
                details={"error": str(e)},
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=time.time()
            )
    
    async def check_system_resources(self) -> HealthCheckResult:
        """Check system resource usage"""
        start_time = time.time()
        component = "system_resources"
        
        try:
            import psutil
            
            # Collect system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Determine status based on thresholds
            status = HealthStatus.HEALTHY
            warnings = []
            
            if cpu_percent > 90:
                status = HealthStatus.CRITICAL
                warnings.append(f"Critical CPU usage: {cpu_percent}%")
            elif cpu_percent > 80:
                status = HealthStatus.WARNING
                warnings.append(f"High CPU usage: {cpu_percent}%")
            
            if memory.percent > 95:
                status = HealthStatus.CRITICAL
                warnings.append(f"Critical memory usage: {memory.percent}%")
            elif memory.percent > 85:
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.WARNING
                warnings.append(f"High memory usage: {memory.percent}%")
            
            if disk.percent > 95:
                status = HealthStatus.CRITICAL
                warnings.append(f"Critical disk usage: {disk.percent}%")
            elif disk.percent > 90:
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.WARNING
                warnings.append(f"High disk usage: {disk.percent}%")
            
            message = "System resources normal" if not warnings else "; ".join(warnings)
            
            return HealthCheckResult(
                component=component,
                status=status,
                message=message,
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": memory.available / (1024**3),
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free / (1024**3)
                },
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=time.time()
            )
            
        except Exception as e:
            return HealthCheckResult(
                component=component,
                status=HealthStatus.CRITICAL,
                message=f"System resource check failed: {str(e)}",
                details={"error": str(e)},
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=time.time()
            )
    
    async def check_rcon_health(self) -> HealthCheckResult:
        """Check RCON server health with comprehensive testing"""
        start_time = time.time()
        component = "rcon"
        
        try:
            # Step 1: Check if RCON port is listening
            port_check = await self._check_rcon_port()
            if not port_check['success']:
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.UNHEALTHY,
                    message=f"RCON port {self.rcon_port} not accessible",
                    details={
                        "port": self.rcon_port,
                        "error": port_check['error']
                    },
                    response_time_ms=(time.time() - start_time) * 1000,
                    timestamp=time.time()
                )
            
            # Step 2: Test RCON command execution
            rcon_test = await self._test_rcon_command()
            
            response_time = (time.time() - start_time) * 1000
            
            if rcon_test['success']:
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.HEALTHY,
                    message="RCON responding normally",
                    details={
                        "port": self.rcon_port,
                        "test_command": "Info",
                        "response_preview": rcon_test['response'][:100] if rcon_test['response'] else "OK"
                    },
                    response_time_ms=response_time,
                    timestamp=time.time()
                )
            else:
                return HealthCheckResult(
                    component=component,
                    status=HealthStatus.WARNING,
                    message="RCON port open but command failed",
                    details={
                        "port": self.rcon_port,
                        "error": rcon_test['error']
                    },
                    response_time_ms=response_time,
                    timestamp=time.time()
                )
                
        except Exception as e:
            return HealthCheckResult(
                component=component,
                status=HealthStatus.CRITICAL,
                message=f"RCON check failed: {str(e)}",
                details={"error": str(e)},
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=time.time()
            )
    
    async def _check_rcon_port(self) -> Dict[str, Any]:
        """Check if RCON port is listening"""
        try:
            # TCP connection test for RCON port
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.rcon_host, self.rcon_port),
                timeout=5
            )
            writer.close()
            await writer.wait_closed()
            
            return {"success": True, "error": None}
            
        except asyncio.TimeoutError:
            return {"success": False, "error": "Connection timeout"}
        except ConnectionRefusedError:
            return {"success": False, "error": "Connection refused"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _test_rcon_command(self) -> Dict[str, Any]:
        """Test RCON command execution using rcon-cli"""
        try:
            # Execute RCON command using rcon-cli
            cmd = [
                'rcon-cli',
                '--host', 'localhost',
                '--port', str(self.rcon_port),
                '--password', self.rcon_password,
                'Info'  # Simple info command for testing
            ]
            
            # Run command with timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=10
                )
                
                if process.returncode == 0:
                    response = stdout.decode('utf-8').strip()
                    return {
                        "success": True, 
                        "response": response,
                        "error": None
                    }
                else:
                    error_msg = stderr.decode('utf-8').strip()
                    return {
                        "success": False,
                        "response": None,
                        "error": f"Command failed: {error_msg}"
                    }
                    
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "response": None,
                    "error": "RCON command timeout"
                }
                
        except FileNotFoundError:
            # rcon-cli not found, fallback to port-only check
            return {
                "success": True,
                "response": "rcon-cli not available, port check only",
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "response": None,
                "error": f"RCON test error: {str(e)}"
            }
    
    async def run_all_checks(self) -> List[HealthCheckResult]:
        """Run all health checks concurrently"""
        checks = [
            self.check_rest_api_health(),
            self.check_server_process(),
            self.check_system_resources(),
            self.check_rcon_health()  # RCON health check added
        ]
        
        self.results = await asyncio.gather(*checks, return_exceptions=True)
        
        # Handle any exceptions that occurred during checks
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
    
    def generate_report(self, format_type: str = "text") -> str:
        """Generate health check report"""
        if format_type == "json":
            return json.dumps({
                "timestamp": time.time(),
                "overall_status": self.get_overall_status().value,
                "checks": [
                    {
                        "component": result.component,
                        "status": result.status.value,
                        "message": result.message,
                        "details": result.details,
                        "response_time_ms": result.response_time_ms,
                        "timestamp": result.timestamp
                    }
                    for result in self.results
                ]
            }, indent=2)
        else:
            # Text format
            overall_status = self.get_overall_status()
            status_emoji = {
                HealthStatus.HEALTHY: "✅",
                HealthStatus.WARNING: "⚠️",
                HealthStatus.UNHEALTHY: "❌",
                HealthStatus.CRITICAL: "🚨"
            }
            
            report = f"{status_emoji[overall_status]} Overall Status: {overall_status.value.upper()}\n\n"
            
            for result in self.results:
                emoji = status_emoji[result.status]
                report += f"{emoji} {result.component}: {result.message}\n"
                if result.response_time_ms > 0:
                    report += f"   Response time: {result.response_time_ms:.1f}ms\n"
                
                # Add key details
                if result.details:
                    for key, value in result.details.items():
                        if key not in ['error', 'processes']:  # Skip complex data
                            report += f"   {key}: {value}\n"
                report += "\n"
            
            return report


async def main():
    """Main health check function"""
    # Parse command line arguments
    format_json = "--json" in sys.argv
    verbose = "--verbose" in sys.argv
    
    checker = HealthChecker()
    
    try:
        # Run all health checks
        results = await checker.run_all_checks()
        overall_status = checker.get_overall_status()
        
        # Generate and print report
        if format_json:
            print(checker.generate_report("json"))
        else:
            print(checker.generate_report("text"))
        
        # Exit with appropriate code
        if overall_status in [HealthStatus.HEALTHY, HealthStatus.WARNING]:
            return 0
        else:
            return 1
            
    except Exception as e:
        if format_json:
            print(json.dumps({
                "error": f"Health check failed: {str(e)}",
                "timestamp": time.time()
            }))
        else:
            print(f"🚨 Health check failed: {e}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Health check critical failure: {e}")
        sys.exit(1)
