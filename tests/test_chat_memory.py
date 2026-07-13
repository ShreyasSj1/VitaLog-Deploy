import pytest
from datetime import datetime, timedelta, timezone
from tests.conftest import make_user, login
from models import ChatMessage, User

# ---------------------------------------------------------------------------
# Mocks for Groq API
# ---------------------------------------------------------------------------

class MockMessage:
    content = "This is a mock AI response from the coach."

class MockChoice:
    message = MockMessage()

class MockChatCompletion:
    choices = [MockChoice()]

class MockCompletions:
    def create(self, *args, **kwargs):
        return MockChatCompletion()

class MockGroq:
    chat = None
    def __init__(self):
        self.chat = self
        self.completions = MockCompletions()

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChatMemory:
    def test_chat_routes_require_login(self, client):
        # GET /chat/history should redirect or fail
        resp = client.get("/chat/history")
        assert resp.status_code in (302, 401)

        # POST /chat should redirect or fail
        resp = client.post("/chat", json={"message": "hello"})
        assert resp.status_code in (302, 401)

    def test_chat_history_empty_for_new_user(self, client, db):
        make_user(db, email="newchat@example.com")
        login(client, email="newchat@example.com")

        resp = client.get("/chat/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "messages" in data
        assert data["messages"] == []

    def test_chat_saves_user_msg_and_assistant_reply(self, client, db, monkeypatch):
        user = make_user(db, email="chatsave@example.com")
        login(client, email="chatsave@example.com")

        # Mock Groq client
        mock_groq = MockGroq()
        monkeypatch.setattr("routes.dashboard.groq_client", mock_groq)

        # Send a message
        resp = client.post("/chat", json={"message": "I want to lose weight."})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["reply"] == "This is a mock AI response from the coach."

        # Verify database contents
        messages = ChatMessage.query.filter_by(user_id=user.id).order_by(ChatMessage.created_at.asc()).all()
        assert len(messages) == 2

        assert messages[0].role == "user"
        assert messages[0].content == "I want to lose weight."

        assert messages[1].role == "assistant"
        assert messages[1].content == "This is a mock AI response from the coach."

    def test_chat_history_is_chronological(self, client, db):
        user = make_user(db, email="chatorder@example.com")
        login(client, email="chatorder@example.com")

        # Insert manual chat messages with sequential timestamps
        base_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        m1 = ChatMessage(user_id=user.id, role="user", content="First msg", created_at=base_time)
        m2 = ChatMessage(user_id=user.id, role="assistant", content="First reply", created_at=base_time + timedelta(seconds=5))
        m3 = ChatMessage(user_id=user.id, role="user", content="Second msg", created_at=base_time + timedelta(seconds=10))

        db.session.add_all([m1, m2, m3])
        db.session.commit()

        # Fetch history
        resp = client.get("/chat/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "messages" in data
        assert len(data["messages"]) == 3
        
        assert data["messages"][0]["content"] == "First msg"
        assert data["messages"][1]["content"] == "First reply"
        assert data["messages"][2]["content"] == "Second msg"

    def test_user_delete_cascades_to_chat_messages(self, db):
        user = make_user(db, email="cascadechat@example.com")
        
        m = ChatMessage(user_id=user.id, role="user", content="Temporary message")
        db.session.add(m)
        db.session.commit()

        # Ensure message is created
        assert ChatMessage.query.filter_by(user_id=user.id).count() == 1

        # Delete user
        db.session.delete(user)
        db.session.commit()

        # Ensure message is cascaded and deleted
        assert ChatMessage.query.filter_by(user_id=user.id).count() == 0
