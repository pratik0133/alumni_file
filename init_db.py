#!/usr/bin/env python3
"""
Database initialization script for production deployment
"""
import os
import sys
from app import app, db, User
from werkzeug.security import generate_password_hash

def init_database():
    """Initialize the database and create admin user"""
    with app.app_context():
        try:
            # Create all tables
            db.create_all()
            print("✅ Database tables created successfully!")
            
            # Create admin user if not exists
            admin = User.query.filter_by(email='pratik@gmail.com').first()
            if not admin:
                admin = User(
                    email='pratik@gmail.com',
                    password_hash=generate_password_hash('admin123'),
                    role='admin',
                    is_approved=True,
                    first_name='Admin',
                    last_name='User'
                )
                db.session.add(admin)
                db.session.commit()
                print("✅ Admin user created successfully!")
                print("   Email: pratik@gmail.com")
                print("   Password: admin123")
            else:
                print("✅ Admin user already exists!")
                
            print("✅ Database initialization completed!")
            
        except Exception as e:
            print(f"❌ Error initializing database: {e}")
            sys.exit(1)

if __name__ == '__main__':
    init_database() 