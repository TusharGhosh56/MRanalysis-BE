def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_success(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "securepass1"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "user@example.com"
    assert "id" in data
    assert "created_at" in data
    assert "password" not in data
    assert "password_hash" not in data


def test_register_normalizes_email(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "  User@Example.COM  ", "password": "securepass1"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "user@example.com"


def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "securepass1"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


def test_register_weak_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_register_password_without_digit(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "nodigit@example.com", "password": "onlyletters"},
    )
    assert response.status_code == 422
    assert "digit" in response.json()["detail"].lower()


def test_login_success(client):
    email = "login@example.com"
    password = "securepass1"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})

    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 0


def test_login_invalid_credentials(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "auth@example.com", "password": "securepass1"},
    )

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": "auth@example.com", "password": "wrongpassword1"},
    )
    assert wrong_password.status_code == 401
    assert wrong_password.json()["detail"] == "Invalid email or password"

    unknown_user = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": "securepass1"},
    )
    assert unknown_user.status_code == 401
    assert unknown_user.json()["detail"] == "Invalid email or password"


def test_me_authenticated(client):
    email = "me@example.com"
    password = "securepass1"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == email


def test_me_unauthenticated(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_invalid_token(client):
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401
