# 📺 VPVR - Virtual Personal Video Recorder

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status](https://img.shields.io/badge/Status-Active%20Development-orange.svg)

**A modern, web-based IPTV Personal Video Recorder system with advanced channel management and recording capabilities**

[Features](#-features) • [Installation](#-installation) • [Usage](#-usage) • [API Documentation](#-api-documentation) • [Contributing](#-contributing)

</div>

---

## 🌟 Features

### Core Functionality
- 📺 **IPTV Channel Management** - Import and manage M3U playlists with thousands of channels
- 🎥 **Advanced Recording** - Schedule and manage recordings with smart conflict resolution
- 📅 **EPG Integration** - Full Electronic Program Guide support with auto-mapping
- 👥 **Multi-User System** - Role-based access control (Admin, Manager, User)
- 💳 **Credit System** - Built-in credit management for recording quotas
- 🏠 **HDHomeRun Emulation** - Compatible with Plex, Emby, and other HDHomeRun clients

### Technical Highlights
- ⚡ **High Performance** - Asynchronous architecture with FastAPI
- 🔄 **Real-time Updates** - WebSocket support for live progress monitoring
- 🎨 **Modern UI** - Responsive Bootstrap 5 interface with multiple themes
- 🔐 **Secure** - JWT authentication and role-based permissions
- 📊 **Scalable** - PostgreSQL/SQLite backend with SQLAlchemy ORM
- 🎬 **FFmpeg Integration** - Professional-grade recording and transcoding

### Key Features
- ✅ Import large M3U playlists (tested with 1M+ channels)
- ✅ Smart EPG channel matching with fuzzy logic
- ✅ Concurrent recording support with FFmpeg
- ✅ Automatic recording space management
- ✅ Real-time import progress monitoring
- ✅ Custom channel groups and playlists
- ✅ Recording transcoding options
- ✅ Mobile-responsive interface
- ✅ Built-in HTML5 video player with pop-up support

## 🚀 Installation

### Prerequisites
- Python 3.12 or higher
- PostgreSQL 12+ (or SQLite for development)
- FFmpeg (for recording functionality)
- 4GB+ RAM recommended
- 50GB+ storage for recordings

### 🐳 Docker Installation (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/vpvr.git
cd vpvr/iptv_pvr

# Start with Docker Compose
docker-compose up -d

# Access at http://localhost:8000
```

### 📦 Manual Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/vpvr.git
cd vpvr/iptv_pvr
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Initialize database**
```bash
alembic upgrade head  # Run migrations
python3 init_db.py    # Create default users
```

6. **Run the application**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 📖 Usage

### Default Login
- **URL**: `http://localhost:8000`
- **Admin**: `admin` / `admin123`
- **Manager**: `manager1` / `password123`
- **User**: `user1` / `password123`

> ⚠️ **Important**: Change these passwords after first login!

### 🎯 Basic Workflow

1. **Import Channels**
   - Navigate to Admin → Import Sources
   - Add M3U URL or upload M3U file
   - Monitor import progress in real-time

2. **Configure EPG**
   - Add EPG source URL
   - Auto-map channels or manually match

3. **Schedule Recordings**
   - Browse channel guide
   - Click on programs to schedule
   - Manage recordings in the dashboard

### ⚙️ Configuration

#### Environment Variables
```env
# Database
DATABASE_URL=postgresql://user:password@localhost/vpvr
# For SQLite: DATABASE_URL=sqlite:///./iptv_pvr.db

# Security
SECRET_KEY=your-secret-key-change-this
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Recording
RECORDING_PATH=./recordings
MAX_CONCURRENT_RECORDINGS=4

# HDHomeRun Emulation
HDHR_DEVICE_ID=IPTV-PVR
HDHR_PORT=5004

# Server
HOST=0.0.0.0
PORT=8000
```

### 📡 HDHomeRun Setup

The system emulates an HDHomeRun device:

- **Plex**: Add network tuner at `http://your-ip:5004`
- **Emby**: Add HDHomeRun device at `http://your-ip:5004`
- **Other apps**: Use discovery or manually add

## 🔧 API Documentation

FastAPI provides automatic interactive API documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | User authentication |
| `/api/channels` | GET | List channels |
| `/api/recordings` | GET/POST | Manage recordings |
| `/api/import-sources` | GET/POST | Manage M3U sources |
| `/api/epg` | GET/POST | EPG operations |
| `/discover.json` | GET | HDHomeRun discovery |
| `/lineup.json` | GET | Channel lineup |

## 🛠️ Development

### Project Structure
```
iptv_pvr/
├── app/
│   ├── api/            # API endpoints
│   ├── auth/           # Authentication
│   ├── models/         # Database models
│   ├── services/       # Business logic
│   ├── templates/      # HTML templates
│   └── utils/          # Utilities
├── alembic/            # Database migrations
├── static/             # CSS, JS, images
├── tests/              # Test suite
├── recordings/         # Recording storage
└── main.py             # Application entry
```

### Running Tests
```bash
pytest tests/
```

### Code Style
```bash
black .           # Format code
flake8           # Lint code
mypy app/        # Type checking
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Development Guidelines
- Write tests for new features
- Follow PEP 8 style guide
- Add docstrings to functions
- Update documentation

## 📊 Performance

- **Channel Capacity**: Handles 1M+ channels efficiently
- **Recording**: 4+ concurrent streams (configurable)
- **Import Speed**: ~130k channels/second parsing
- **WebSocket**: Real-time updates with minimal latency
- **Database**: Optimized queries with proper indexing

## 🔒 Security

- 🔐 JWT-based authentication
- 👮 Role-based access control (RBAC)
- 🔑 Secure password hashing (bcrypt)
- 🛡️ SQL injection protection
- 🚫 XSS prevention
- 📝 Activity logging

### Security Best Practices
1. Change default passwords immediately
2. Use HTTPS in production
3. Set strong SECRET_KEY
4. Enable firewall rules
5. Regular security updates
6. Monitor access logs

## 🐛 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Playback not working | Check CORS settings and stream URLs |
| Recording fails | Verify FFmpeg installation and permissions |
| Import stuck | Check server logs and network connectivity |
| HDHomeRun not detected | Verify port 5004 is open |

### Logs
```bash
# Docker logs
docker-compose logs -f vpvr

# Manual installation
tail -f server.log
```

## 📈 Roadmap

- [ ] Mobile apps (iOS/Android)
- [ ] Cloud storage support
- [ ] Advanced transcoding profiles
- [ ] AI-powered content recommendations
- [ ] Multi-language support
- [ ] DVR series management
- [ ] Chromecast support

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- UI powered by [Bootstrap 5](https://getbootstrap.com/)
- Icons by [Bootstrap Icons](https://icons.getbootstrap.com/)
- Database ORM by [SQLAlchemy](https://www.sqlalchemy.org/)
- Media handling by [FFmpeg](https://ffmpeg.org/)
- HDHomeRun protocol documentation

## 📞 Support

- 📧 Email: support@vpvr.example.com
- 💬 Discord: [Join our server](https://discord.gg/vpvr)
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/vpvr/issues)
- 📖 Wiki: [Documentation](https://github.com/yourusername/vpvr/wiki)

---

<div align="center">

**⭐ Star this repository if you find it helpful!**

Made with ❤️ by the VPVR Team

[Back to top](#-vpvr---virtual-personal-video-recorder)

</div>