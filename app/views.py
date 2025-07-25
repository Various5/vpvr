from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request):
    return templates.TemplateResponse("channels.html", {"request": request})

@router.get("/epg", response_class=HTMLResponse)
async def epg_page(request: Request):
    return templates.TemplateResponse("epg.html", {"request": request})

@router.get("/recordings", response_class=HTMLResponse)
async def recordings_page(request: Request):
    return templates.TemplateResponse("recordings.html", {"request": request})

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    return templates.TemplateResponse("profile.html", {"request": request})

@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    return templates.TemplateResponse("admin/users.html", {"request": request})

@router.get("/admin/playlists", response_class=HTMLResponse)
async def admin_playlists_page(request: Request):
    return templates.TemplateResponse("admin/playlists.html", {"request": request})

@router.get("/admin/system", response_class=HTMLResponse)
async def admin_system_page(request: Request):
    return templates.TemplateResponse("admin/system.html", {"request": request})


@router.get("/admin/epg-manager", response_class=HTMLResponse)
async def admin_epg_manager(request: Request):
    return templates.TemplateResponse("admin/epg-manager.html", {"request": request})

@router.get("/livetv", response_class=HTMLResponse)
async def livetv_page(request: Request):
    return templates.TemplateResponse("livetv.html", {"request": request})

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@router.get("/themes", response_class=HTMLResponse)
async def themes_page(request: Request):
    return templates.TemplateResponse("themes-v3.html", {"request": request})

@router.get("/credits", response_class=HTMLResponse)
async def credits_page(request: Request):
    return templates.TemplateResponse("credits.html", {"request": request})

@router.get("/admin/imports", response_class=HTMLResponse)
async def admin_imports_page(request: Request):
    return templates.TemplateResponse("admin/imports.html", {"request": request})

@router.get("/admin/imports/legacy", response_class=HTMLResponse)
async def admin_imports_legacy_page(request: Request):
    return templates.TemplateResponse("admin/imports.html", {"request": request})

@router.get("/admin/database-cleanup", response_class=HTMLResponse)
async def admin_database_cleanup_page(request: Request):
    return templates.TemplateResponse("admin/database-cleanup.html", {"request": request})

@router.get("/system", response_class=HTMLResponse)
async def system_page(request: Request):
    return templates.TemplateResponse("system.html", {"request": request})

@router.get("/admin/channel-manager", response_class=HTMLResponse)
async def channel_manager_page(request: Request):
    return templates.TemplateResponse("admin/channel-manager-v2.html", {"request": request})

@router.get("/admin/channel-manager/legacy", response_class=HTMLResponse)
async def channel_manager_legacy_page(request: Request):
    return templates.TemplateResponse("admin/channel-manager.html", {"request": request})

@router.get("/admin/import-monitor", response_class=HTMLResponse)
async def import_monitor_page(request: Request):
    return templates.TemplateResponse("admin/import-monitor.html", {"request": request})

@router.get("/server-settings", response_class=HTMLResponse)
async def server_settings_page(request: Request):
    return templates.TemplateResponse("server-settings.html", {"request": request})