#!/usr/bin/env python3
"""
Standalone HDHomeRun Server for IPTV PVR
Runs independently on configurable port for better discovery
"""
import asyncio
import aiohttp
from aiohttp import web
import argparse
import socket
import struct
import logging
import json
import os
from datetime import datetime
import sys

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('hdhr_server')

class HDHomeRunServer:
    def __init__(self, hdhr_port=5004, main_server='http://localhost:8000', device_id=None):
        self.hdhr_port = hdhr_port
        self.main_server = main_server.rstrip('/')
        self.device_id = device_id or f'IPTV-PVR-{hdhr_port}'
        self.device_uuid = f'12345678-{hdhr_port:04d}-1234-1234-123456789012'
        self.app = web.Application()
        self.setup_routes()
        self.local_ip = self.get_local_ip()
        self.ssdp_task = None
        
    def get_local_ip(self):
        """Get the local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
            
    def setup_routes(self):
        """Setup web routes"""
        self.app.router.add_get('/', self.root)
        self.app.router.add_get('/discover.json', self.discover)
        self.app.router.add_get('/device.xml', self.device_xml)
        self.app.router.add_get('/lineup.json', self.lineup)
        self.app.router.add_get('/lineup.xml', self.lineup_xml)
        self.app.router.add_get('/lineup_status.json', self.lineup_status)
        self.app.router.add_get('/auto/v{channel}', self.stream_channel)
        
    async def root(self, request):
        """Root endpoint"""
        return web.Response(text=f"HDHomeRun Server (Port {self.hdhr_port})")
        
    async def discover(self, request):
        """HDHomeRun discovery endpoint"""
        base_url = f"http://{self.local_ip}:{self.hdhr_port}"
        
        device_info = {
            "FriendlyName": f"IPTV PVR HDHomeRun (Port {self.hdhr_port})",
            "Manufacturer": "IPTV PVR",
            "ManufacturerURL": "https://github.com/iptv-pvr",
            "ModelNumber": "HDTC-2US",
            "FirmwareVersion": "20250125",
            "DeviceID": self.device_id,
            "DeviceAuth": "iptv-pvr",
            "BaseURL": base_url,
            "LineupURL": f"{base_url}/lineup.json",
            "TunerCount": 4
        }
        
        logger.info(f"Discover request from {request.remote} - BaseURL: {base_url}")
        return web.json_response(device_info)
        
    async def device_xml(self, request):
        """UPnP device description"""
        base_url = f"http://{self.local_ip}:{self.hdhr_port}"
        
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
    <specVersion>
        <major>1</major>
        <minor>0</minor>
    </specVersion>
    <device>
        <deviceType>urn:schemas-upnp-org:device:MediaServer:1</deviceType>
        <friendlyName>IPTV PVR HDHomeRun (Port {self.hdhr_port})</friendlyName>
        <manufacturer>IPTV PVR</manufacturer>
        <manufacturerURL>https://github.com/iptv-pvr</manufacturerURL>
        <modelDescription>IPTV PVR HDHomeRun Emulator</modelDescription>
        <modelName>HDTC-2US</modelName>
        <modelNumber>HDTC-2US</modelNumber>
        <modelURL>{base_url}</modelURL>
        <serialNumber>{self.device_id}</serialNumber>
        <UDN>uuid:{self.device_uuid}</UDN>
        <presentationURL>{base_url}</presentationURL>
    </device>
</root>"""
        
        return web.Response(text=xml_content, content_type='application/xml')
        
    async def lineup_status(self, request):
        """Lineup status"""
        return web.json_response({
            "ScanInProgress": False,
            "ScanPossible": True,
            "Source": "IPTV",
            "SourceList": ["IPTV"]
        })
        
    async def lineup(self, request):
        """Get channel lineup from main server"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.main_server}/api/channels?limit=1000") as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to get channels: {resp.status}")
                        return web.json_response([])
                        
                    channels = await resp.json()
                    
            lineup = []
            for idx, channel in enumerate(channels):
                if channel.get('is_active', True):
                    channel_num = channel.get('number') or str(idx + 1)
                    lineup.append({
                        "GuideNumber": channel_num,
                        "GuideName": channel['name'],
                        "URL": f"http://{self.local_ip}:{self.hdhr_port}/auto/v{channel_num}",
                        "HD": 1
                    })
                    
            logger.info(f"Returning {len(lineup)} channels in lineup")
            return web.json_response(lineup)
            
        except Exception as e:
            logger.error(f"Error getting lineup: {e}")
            return web.json_response([])
            
    async def lineup_xml(self, request):
        """Get channel lineup in XML format"""
        try:
            # Get JSON lineup first
            lineup_response = await self.lineup(request)
            lineup_data = json.loads(lineup_response.text)
            
            xml_items = []
            for channel in lineup_data:
                xml_items.append(f"""
        <Program>
            <GuideNumber>{channel['GuideNumber']}</GuideNumber>
            <GuideName>{channel['GuideName']}</GuideName>
            <URL>{channel['URL']}</URL>
        </Program>""")
                
            xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Lineup>
    {''.join(xml_items)}
</Lineup>"""
            
            return web.Response(text=xml_content, content_type='application/xml')
            
        except Exception as e:
            logger.error(f"Error generating lineup XML: {e}")
            return web.Response(text='<Lineup></Lineup>', content_type='application/xml')
            
    async def stream_channel(self, request):
        """Stream a channel by proxying to main server"""
        channel_number = request.match_info['channel']
        
        # Proxy the stream request to the main server
        stream_url = f"{self.main_server}/api/stream-proxy/channels/v{channel_number}/stream"
        
        logger.info(f"Streaming channel {channel_number} via {stream_url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(stream_url) as resp:
                    if resp.status != 200:
                        return web.Response(status=resp.status)
                        
                    # Stream the response
                    response = web.StreamResponse(
                        status=200,
                        headers={
                            'Content-Type': resp.headers.get('Content-Type', 'video/mpeg'),
                            'Cache-Control': 'no-cache',
                            'Connection': 'keep-alive'
                        }
                    )
                    await response.prepare(request)
                    
                    async for chunk in resp.content.iter_chunked(8192):
                        await response.write(chunk)
                        
                    await response.write_eof()
                    return response
                    
        except Exception as e:
            logger.error(f"Stream error: {e}")
            return web.Response(status=500)
            
    async def start_ssdp(self):
        """Start SSDP discovery service"""
        logger.info(f"Starting SSDP discovery on port {self.hdhr_port}")
        
        # Create UDP socket for SSDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Bind to SSDP multicast port
        sock.bind(('', 1900))
        
        # Join multicast group
        mreq = struct.pack("4sl", socket.inet_aton('239.255.255.250'), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(1.0)
        
        # Send initial announcements
        await self.send_ssdp_notify()
        
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                if b'M-SEARCH' in data:
                    if b'ssdp:all' in data or b'MediaServer' in data or b'HDHomeRun' in data:
                        logger.info(f"SSDP M-SEARCH from {addr[0]}:{addr[1]}")
                        await self.send_ssdp_response(sock, addr)
                        
            except socket.timeout:
                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SSDP error: {e}")
                
            await asyncio.sleep(0.1)
            
        sock.close()
        
    async def send_ssdp_response(self, sock, addr):
        """Send SSDP response"""
        location = f"http://{self.local_ip}:{self.hdhr_port}/device.xml"
        
        response = (
            "HTTP/1.1 200 OK\r\n"
            "CACHE-CONTROL: max-age=1800\r\n"
            f"LOCATION: {location}\r\n"
            "ST: urn:schemas-upnp-org:device:MediaServer:1\r\n"
            f"USN: uuid:{self.device_uuid}::urn:schemas-upnp-org:device:MediaServer:1\r\n"
            "SERVER: HDHomeRun/1.0 UPnP/1.0\r\n"
            "EXT:\r\n"
            "\r\n"
        )
        
        try:
            sock.sendto(response.encode('utf-8'), addr)
            logger.info(f"Sent SSDP response to {addr[0]}:{addr[1]}")
        except Exception as e:
            logger.error(f"Failed to send SSDP response: {e}")
            
    async def send_ssdp_notify(self):
        """Send SSDP NOTIFY (advertisement)"""
        location = f"http://{self.local_ip}:{self.hdhr_port}/device.xml"
        
        notify = (
            "NOTIFY * HTTP/1.1\r\n"
            "HOST: 239.255.255.250:1900\r\n"
            "CACHE-CONTROL: max-age=1800\r\n"
            f"LOCATION: {location}\r\n"
            "NT: urn:schemas-upnp-org:device:MediaServer:1\r\n"
            "NTS: ssdp:alive\r\n"
            "SERVER: HDHomeRun/1.0 UPnP/1.0\r\n"
            f"USN: uuid:{self.device_uuid}::urn:schemas-upnp-org:device:MediaServer:1\r\n"
            "\r\n"
        )
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.sendto(notify.encode('utf-8'), ('239.255.255.250', 1900))
            sock.close()
            logger.info("Sent SSDP NOTIFY advertisement")
        except Exception as e:
            logger.error(f"Failed to send SSDP NOTIFY: {e}")
            
    async def periodic_announce(self):
        """Send periodic SSDP announcements"""
        while True:
            await asyncio.sleep(30)
            await self.send_ssdp_notify()
            
    async def start(self):
        """Start the HDHomeRun server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.hdhr_port)
        await site.start()
        
        logger.info(f"HDHomeRun server started on port {self.hdhr_port}")
        logger.info(f"Web interface: http://{self.local_ip}:{self.hdhr_port}")
        logger.info(f"Main server: {self.main_server}")
        
        # Start SSDP discovery
        self.ssdp_task = asyncio.create_task(self.start_ssdp())
        announce_task = asyncio.create_task(self.periodic_announce())
        
        try:
            await asyncio.gather(self.ssdp_task, announce_task)
        except asyncio.CancelledError:
            pass

async def main():
    parser = argparse.ArgumentParser(description='HDHomeRun Server for IPTV PVR')
    parser.add_argument('--port', type=int, default=5004, help='HDHomeRun server port (default: 5004)')
    parser.add_argument('--main-server', default='http://localhost:8000', help='Main IPTV PVR server URL')
    parser.add_argument('--device-id', help='Device ID (default: IPTV-PVR-{port})')
    
    args = parser.parse_args()
    
    server = HDHomeRunServer(
        hdhr_port=args.port,
        main_server=args.main_server,
        device_id=args.device_id
    )
    
    print(f"\nHDHomeRun Server for IPTV PVR")
    print(f"=============================")
    print(f"Port: {args.port}")
    print(f"Main Server: {args.main_server}")
    print(f"Device ID: {server.device_id}")
    print(f"\nPress CTRL+C to stop\n")
    
    try:
        await server.start()
    except KeyboardInterrupt:
        print("\nShutting down...")

if __name__ == '__main__':
    asyncio.run(main())