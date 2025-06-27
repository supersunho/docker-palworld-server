#!/usr/bin/env python3
"""
Simple web dashboard
Lightweight dashboard reflecting user's workflow optimization preferences
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from aiohttp import web, WSMsgType
from aiohttp.web_request import Request
from aiohttp.web_response import Response

from config_loader import PalworldConfig
from logging_setup import get_logger
from monitoring.metrics_collector import get_metrics_collector


class PalworldDashboard:
    """Palworld dashboard server"""
    
    def __init__(self, config: PalworldConfig):
        self.config = config
        self.logger = get_logger("palworld.dashboard")
        self.metrics_collector = get_metrics_collector(config)
        
        # Web app setup
        self.app = web.Application()
        self._setup_routes()
        
        # Real-time connection management
        self.websockets = set()
    
    def _setup_routes(self):
        """Setup routes"""
        # Static files (CSS, JS)
        self.app.router.add_static('/static/', path='templates/static', name='static')
        
        # Main page
        self.app.router.add_get('/', self.index_handler)
        
        # API endpoints
        self.app.router.add_get('/api/status', self.status_api)
        self.app.router.add_get('/api/metrics', self.metrics_api)
        self.app.router.add_get('/api/players', self.players_api)
        
        # WebSocket (real-time updates)
        self.app.router.add_get('/ws', self.websocket_handler)
    
    async def index_handler(self, request: Request) -> Response:
        """Main dashboard page"""
        template_path = Path(__file__).parent.parent.parent / "templates" / "dashboard.html"
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Basic variable substitution
            html_content = html_content.replace('{{SERVER_NAME}}', self.config.server.name)
            html_content = html_content.replace('{{MAX_PLAYERS}}', str(self.config.server.max_players))
            
            return web.Response(text=html_content, content_type='text/html')
            
        except FileNotFoundError:
            # Return simple HTML if template file not found
            html = self._generate_simple_dashboard()
            return web.Response(text=html, content_type='text/html')
    
    def _generate_simple_dashboard(self) -> str:
        """Generate simple dashboard HTML"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎮 {self.config.server.name} - Dashboard</title>
    <style>
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 20px; background: #1a1a1a; color: #fff;
        }}
        .header {{ 
            text-align: center; margin-bottom: 30px; 
            border-bottom: 2px solid #333; padding-bottom: 20px;
        }}
        .metrics-grid {{ 
            display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
            gap: 20px; margin-bottom: 30px; 
        }}
        .metric-card {{ 
            background: #2a2a2a; border-radius: 10px; padding: 20px; 
            border-left: 4px solid #4CAF50; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }}
        .metric-title {{ font-size: 14px; color: #bbb; margin-bottom: 10px; }}
        .metric-value {{ font-size: 28px; font-weight: bold; color: #4CAF50; }}
        .metric-unit {{ font-size: 16px; color: #888; }}
        .status-online {{ color: #4CAF50; }}
        .status-offline {{ color: #f44336; }}
        .refresh-btn {{ 
            background: #4CAF50; color: white; border: none; padding: 10px 20px; 
            border-radius: 5px; cursor: pointer; font-size: 16px;
        }}
        .logs {{ 
            background: #2a2a2a; border-radius: 10px; padding: 20px; 
            max-height: 400px; overflow-y: auto; font-family: monospace;
        }}
        .log-entry {{ margin-bottom: 5px; }}
        .footer {{ 
            text-align: center; margin-top: 30px; padding-top: 20px; 
            border-top: 1px solid #333; color: #888; 
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎮 {self.config.server.name}</h1>
        <p>Real-time Server Monitoring Dashboard</p>
        <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
    </div>
    
    <div class="metrics-grid">
        <div class="metric-card">
            <div class="metric-title">👥 Online Players</div>
            <div class="metric-value" id="players-online">-</div>
            <div class="metric-unit">/ {self.config.server.max_players} players</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-title">🖥️ CPU Usage</div>
            <div class="metric-value" id="cpu-usage">-</div>
            <div class="metric-unit">%</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-title">💾 Memory Usage</div>
            <div class="metric-value" id="memory-usage">-</div>
            <div class="metric-unit">GB</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-title">⏱️ Server Uptime</div>
            <div class="metric-value" id="uptime">-</div>
            <div class="metric-unit">hours</div>
        </div>
    </div>
    
    <div class="logs">
        <h3>📝 Recent Logs</h3>
        <div id="log-container">
            <div class="log-entry">🚀 Dashboard loaded - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
    </div>
    
    <div class="footer">
        <p>🐳 Docker + 🎮 Palworld + 🚀 FEX Emulation</p>
        <p>Last updated: <span id="last-update">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span></p>
    </div>
    
    <script>
        // Real-time update WebSocket
        const ws = new WebSocket('ws://localhost:{self.config.monitoring.dashboard_port}/ws');
        
        ws.onmessage = function(event) {{
            const data = JSON.parse(event.data);
            
            if (data.players_online !== undefined) {{
                document.getElementById('players-online').textContent = data.players_online;
            }}
            if (data.cpu_percent !== undefined) {{
                document.getElementById('cpu-usage').textContent = data.cpu_percent.toFixed(1);
            }}
            if (data.memory_gb !== undefined) {{
                document.getElementById('memory-usage').textContent = data.memory_gb.toFixed(2);
            }}
            if (data.uptime_hours !== undefined) {{
                document.getElementById('uptime').textContent = data.uptime_hours.toFixed(1);
            }}
            
            document.getElementById('last-update').textContent = new Date().toLocaleString();
        }};
        
        // API call every 5 seconds (WebSocket backup)
        setInterval(async () => {{
            try {{
                const response = await fetch('/api/metrics');
                const data = await response.json();
                
                // Metrics update logic
                if (data.system) {{
                    document.getElementById('cpu-usage').textContent = data.system.cpu_percent.toFixed(1);
                    document.getElementById('memory-usage').textContent = data.system.memory_gb.toFixed(2);
                }}
                
                if (data.game) {{
                    document.getElementById('players-online').textContent = data.game.players_online;
                    document.getElementById('uptime').textContent = data.game.uptime_hours.toFixed(1);
                }}
                
            }} catch (error) {{
                console.error('Metrics update failed:', error);
            }}
        }}, 5000);
    </script>
</body>
</html>
        """
    
    async def status_api(self, request: Request) -> Response:
        """Server status API"""
        # Query actual server status from server_manager in real implementation
        status = {
            "server_running": True,  # Check from server_manager in actual implementation
            "timestamp": datetime.now().isoformat(),
            "config": {
                "server_name": self.config.server.name,
                "max_players": self.config.server.max_players,
                "monitoring_mode": self.config.monitoring.mode,
            }
        }
        
        return web.json_response(status)
    
    async def metrics_api(self, request: Request) -> Response:
        """Metrics API"""
        try:
            # Collect system metrics
            system_metrics = await self.metrics_collector._collect_system_metrics()
            
            # Game metrics (dummy data, actual implementation from server_manager)
            game_metrics = self.metrics_collector.collect_game_metrics_sync()
            
            response_data = {
                "timestamp": datetime.now().isoformat(),
                "system": {
                    "cpu_percent": system_metrics.cpu_percent,
                    "memory_gb": system_metrics.memory_usage_gb,
                    "memory_percent": system_metrics.memory_percent,
                    "disk_gb": system_metrics.disk_usage_gb,
                    "disk_percent": system_metrics.disk_percent,
                },
                "game": {
                    "players_online": game_metrics.players_online,
                    "max_players": game_metrics.max_players,
                    "uptime_hours": game_metrics.server_uptime_seconds / 3600,
                    "tps": game_metrics.tps,
                    "world_size_mb": game_metrics.world_save_size_mb,
                }
            }
            
            return web.json_response(response_data)
            
        except Exception as e:
            self.logger.error("Metrics API error", error=str(e))
            return web.json_response({"error": str(e)}, status=500)
    
    async def players_api(self, request: Request) -> Response:
        """Players API (to be integrated with server_manager later)"""
        # Dummy data
        players_data = {
            "players": [],
            "count": 0,
            "max_players": self.config.server.max_players
        }
        
        return web.json_response(players_data)
    
    async def websocket_handler(self, request: Request) -> web.WebSocketResponse:
        """WebSocket handler (real-time updates)"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.websockets.add(ws)
        self.logger.info("WebSocket connection created", client_count=len(self.websockets))
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    # Handle client requests (if needed)
                    pass
                elif msg.type == WSMsgType.ERROR:
                    self.logger.error('WebSocket error', error=ws.exception())
                    break
        except Exception as e:
            self.logger.error("WebSocket processing error", error=str(e))
        finally:
            self.websockets.discard(ws)
            self.logger.info("WebSocket connection closed", client_count=len(self.websockets))
        
        return ws
    
    async def broadcast_metrics(self, metrics_data: Dict[str, Any]):
        """Broadcast metrics to all WebSocket clients"""
        if not self.websockets:
            return
        
        message = json.dumps(metrics_data)
        dead_connections = set()
        
        for ws in self.websockets:
            try:
                await ws.send_str(message)
            except Exception:
                dead_connections.add(ws)
        
        # Clean up dead connections
        self.websockets -= dead_connections
    
    async def start_server(self):
        """Start dashboard server"""
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(
                runner, 
                self.config.rest_api.host, 
                self.config.monitoring.dashboard_port
            )
            await site.start()
            
            self.logger.info(
                "🎨 Dashboard server started",
                host=self.config.rest_api.host,
                port=self.config.monitoring.dashboard_port,
                url=f"http://{self.config.rest_api.host}:{self.config.monitoring.dashboard_port}"
            )
            
        except Exception as e:
            self.logger.error("Failed to start dashboard server", error=str(e))
            raise


async def main():
    """Test run"""
    from config_loader import get_config
    
    config = get_config()
    dashboard = PalworldDashboard(config)
    
    print(f"🎨 Starting dashboard: http://localhost:{config.monitoring.dashboard_port}")
    
    await dashboard.start_server()
    
    # Keep server running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Dashboard shutdown")


if __name__ == "__main__":
    asyncio.run(main())
