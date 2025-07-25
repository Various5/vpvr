"""HDHomeRun SSDP Discovery Service"""
import socket
import struct
import threading
import time
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SSDP_ADDR = '239.255.255.250'
SSDP_PORT = 1900
SSDP_MX = 2
SSDP_ST = 'urn:schemas-upnp-org:device:MediaServer:1'

def get_local_ip():
    """Get the local IP address"""
    try:
        # Create a socket to an external address to find our local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

class HDHomeRunDiscovery:
    def __init__(self):
        self.running = False
        self.thread = None
        self.sock = None
        self.local_ip = get_local_ip()
        
    def start(self):
        """Start the SSDP discovery service"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run_discovery)
        self.thread.daemon = True
        self.thread.start()
        logger.info(f"HDHomeRun SSDP discovery started on {self.local_ip}")
        
    def stop(self):
        """Stop the SSDP discovery service"""
        self.running = False
        if self.sock:
            self.sock.close()
        if self.thread:
            self.thread.join()
        logger.info("HDHomeRun SSDP discovery stopped")
        
    def _run_discovery(self):
        """Run the SSDP discovery loop"""
        try:
            # Create UDP socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to SSDP port
            self.sock.bind(('', SSDP_PORT))
            
            # Join multicast group
            mreq = struct.pack("4sl", socket.inet_aton(SSDP_ADDR), socket.INADDR_ANY)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            
            # Set timeout for socket operations
            self.sock.settimeout(1.0)
            
            logger.info(f"SSDP discovery listening on {SSDP_ADDR}:{SSDP_PORT}")
            
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    self._handle_ssdp_request(data, addr)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"SSDP error: {e}")
                        
        except Exception as e:
            logger.error(f"Failed to start SSDP discovery: {e}")
            
    def _handle_ssdp_request(self, data, addr):
        """Handle SSDP M-SEARCH requests"""
        try:
            message = data.decode('utf-8')
            
            # Check if this is an M-SEARCH request
            if 'M-SEARCH' not in message:
                return
                
            # Check if searching for HDHomeRun or MediaServer devices
            if 'ssdp:all' in message or 'MediaServer' in message or 'HDHomeRun' in message:
                logger.info(f"SSDP M-SEARCH from {addr[0]}:{addr[1]}")
                self._send_ssdp_response(addr)
                
        except Exception as e:
            logger.error(f"Error handling SSDP request: {e}")
            
    def _send_ssdp_response(self, addr):
        """Send SSDP response"""
        location = f"http://{self.local_ip}:{settings.server_port}/device.xml"
        
        response = (
            "HTTP/1.1 200 OK\r\n"
            "CACHE-CONTROL: max-age=1800\r\n"
            f"LOCATION: {location}\r\n"
            "ST: urn:schemas-upnp-org:device:MediaServer:1\r\n"
            f"USN: uuid:{settings.hdhr_device_uuid}::urn:schemas-upnp-org:device:MediaServer:1\r\n"
            "SERVER: HDHomeRun/1.0 UPnP/1.0\r\n"
            "EXT:\r\n"
            "\r\n"
        )
        
        try:
            self.sock.sendto(response.encode('utf-8'), addr)
            logger.info(f"Sent SSDP response to {addr[0]}:{addr[1]} - Location: {location}")
        except Exception as e:
            logger.error(f"Failed to send SSDP response: {e}")
            
    def send_ssdp_notify(self):
        """Send SSDP NOTIFY message (advertisement)"""
        location = f"http://{self.local_ip}:{settings.server_port}/device.xml"
        
        notify = (
            "NOTIFY * HTTP/1.1\r\n"
            f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
            "CACHE-CONTROL: max-age=1800\r\n"
            f"LOCATION: {location}\r\n"
            "NT: urn:schemas-upnp-org:device:MediaServer:1\r\n"
            "NTS: ssdp:alive\r\n"
            "SERVER: HDHomeRun/1.0 UPnP/1.0\r\n"
            f"USN: uuid:{settings.hdhr_device_uuid}::urn:schemas-upnp-org:device:MediaServer:1\r\n"
            "\r\n"
        )
        
        try:
            # Send to multicast group
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.sendto(notify.encode('utf-8'), (SSDP_ADDR, SSDP_PORT))
            sock.close()
            logger.info("Sent SSDP NOTIFY advertisement")
        except Exception as e:
            logger.error(f"Failed to send SSDP NOTIFY: {e}")

# Global instance
discovery_service = HDHomeRunDiscovery()

def start_discovery():
    """Start the HDHomeRun discovery service"""
    discovery_service.start()
    
    # Send initial advertisements
    for i in range(3):
        discovery_service.send_ssdp_notify()
        time.sleep(1)
        
    # Set up periodic advertisements (every 30 seconds)
    def advertise():
        while discovery_service.running:
            discovery_service.send_ssdp_notify()
            time.sleep(30)
            
    adv_thread = threading.Thread(target=advertise)
    adv_thread.daemon = True
    adv_thread.start()
    
def stop_discovery():
    """Stop the HDHomeRun discovery service"""
    discovery_service.stop()