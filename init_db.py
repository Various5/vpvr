from app.database import SessionLocal, engine, Base
from app.models.user import User, UserRole
from app.models.credit import UserQuota
from app.auth.security import get_password_hash
from app.config import get_settings

settings = get_settings()

def init_db():
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    # Check if admin exists
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        # Create admin user
        admin = User(
            username="admin",
            email="admin@iptvpvr.local",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.ADMIN,
            credits=1000
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        
        # Create unlimited quota for admin
        admin_quota = UserQuota(
            user_id=admin.id,
            max_recordings=999,
            max_recurring_shows=999,
            max_movies=999
        )
        db.add(admin_quota)
        db.commit()
        
        print("Admin user created:")
        print("Username: admin")
        print("Password: admin123")
        print("Please change the password after first login!")
    
    # Create test users
    test_users = [
        {"username": "manager1", "email": "manager1@test.com", "role": UserRole.MANAGER, "credits": 50},
        {"username": "user1", "email": "user1@test.com", "role": UserRole.USER, "credits": 10},
        {"username": "user2", "email": "user2@test.com", "role": UserRole.USER, "credits": 5}
    ]
    
    for user_data in test_users:
        if not db.query(User).filter(User.username == user_data["username"]).first():
            user = User(
                username=user_data["username"],
                email=user_data["email"],
                hashed_password=get_password_hash("password123"),
                role=user_data["role"],
                credits=user_data["credits"]
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Create quota
            if user_data["role"] == UserRole.MANAGER:
                quota = UserQuota(
                    user_id=user.id,
                    max_recordings=10,
                    max_recurring_shows=10,
                    max_movies=10
                )
            else:
                quota = UserQuota(user_id=user.id)
            
            db.add(quota)
            db.commit()
            
            print(f"Created test user: {user_data['username']} (password: password123)")
    
    db.close()

if __name__ == "__main__":
    init_db()