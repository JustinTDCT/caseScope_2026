#!/usr/bin/env python3
"""
CaseScope 2026 v1.0.0 - Main Application (Refactored)
Minimal bootstrap - routes in separate blueprint files
"""

import os
import logging
from flask import Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash
from opensearchpy import OpenSearch

# Import config and models
from config import Config
from models import db, User
from celery_app import celery_app

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# Initialize OpenSearch
opensearch_client = OpenSearch(
    hosts=[{'host': app.config['OPENSEARCH_HOST'], 'port': app.config['OPENSEARCH_PORT']}],
    http_compress=True,
    use_ssl=app.config['OPENSEARCH_USE_SSL'],
    verify_certs=False,
    ssl_assert_hostname=False,
    ssl_show_warn=False
)

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ============================================================================
# REGISTER BLUEPRINTS
# ============================================================================

from routes.auth import auth_bp
from routes.api import api_bp
# TODO: Import other blueprints when created
# from routes.dashboard import dashboard_bp
# from routes.cases import cases_bp
# from routes.files import files_bp

app.register_blueprint(auth_bp)
app.register_blueprint(api_bp)
# TODO: Register other blueprints
# app.register_blueprint(dashboard_bp)
# app.register_blueprint(cases_bp)
# app.register_blueprint(files_bp)


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

@app.cli.command('init-db')
def init_db():
    """Initialize database and create default admin user"""
    db.create_all()
    
    # Create default admin user
    admin = db.session.query(User).filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@casescope.local',
            password_hash=generate_password_hash('admin'),
            full_name='Administrator',
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print("✓ Default admin user created (admin/admin)")
    else:
        print("✓ Admin user already exists")
    
    print("✓ Database initialized successfully!")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
