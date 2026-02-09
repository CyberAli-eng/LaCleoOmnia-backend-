"""
Test suite for LaCleoOmnia API
"""
import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from app.database import get_db, Base
from app.models import User, UserRole
from app.auth import create_access_token, get_password_hash

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="session")
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(setup_database):
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def test_user(db_session):
    user = User(
        name="Test User",
        email="test@example.com",
        password_hash=get_password_hash("testpassword"),
        role=UserRole.ADMIN
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture
def auth_token(test_user):
    return create_access_token(data={"sub": test_user.email})

@pytest.fixture
def client():
    return TestClient(app)

class TestAuth:
    def test_login_success(self, client, test_user):
        response = client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword"
        })
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"

    def test_login_invalid_credentials(self, client):
        response = client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401

    def test_get_current_user(self, client, auth_token):
        response = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        assert response.json()["email"] == "test@example.com"

class TestOrders:
    def test_list_orders(self, client, auth_token):
        response = client.get("/api/orders", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        assert isinstance(response.json(), list)

class TestHealth:
    def test_health_check(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

class TestIntegrations:
    def test_get_catalog(self, client, auth_token):
        response = client.get("/api/integrations/catalog", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        assert isinstance(response.json(), list)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
