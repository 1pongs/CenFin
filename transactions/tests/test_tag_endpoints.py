import pytest
from django.urls import reverse

from django.contrib.auth import get_user_model
from entities.models import Entity
from transactions.models import CategoryTag


@pytest.mark.django_db
def test_tag_list_requires_entity_and_filters(client):
    User = get_user_model()
    user = User.objects.create_user(username="tu1", password="pass")
    client.login(username="tu1", password="pass")

    ent1 = Entity.objects.create(user=user, entity_name="E1")
    ent2 = Entity.objects.create(user=user, entity_name="E2")

    CategoryTag.objects.create(
        user=user, entity=ent1, name="A", transaction_type="expense"
    )
    CategoryTag.objects.create(
        user=user, entity=ent2, name="B", transaction_type="income"
    )

    url = reverse("transactions:tags")
    # No entity => empty list
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.json() == []

    # With entity filter => returns only that entity's tags
    resp = client.get(url, {"entity": ent1.id})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1 and data[0]["name"] == "A"

    # With tx type filter
    resp = client.get(url, {"entity": ent1.id, "transaction_type": "income"})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.django_db
def test_tag_create_requires_entity_and_creates(client):
    User = get_user_model()
    user = User.objects.create_user(username="tu2", password="pass")
    client.login(username="tu2", password="pass")

    ent = Entity.objects.create(user=user, entity_name="Ecreate")

    url = reverse("transactions:tags")
    # Missing entity -> 400
    resp = client.post(url, {"name": "NewTag", "transaction_type": "expense"})
    assert resp.status_code == 400

    # With entity -> create
    resp = client.post(
        url, {"name": "NewTag", "transaction_type": "expense", "entity": ent.id}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "NewTag"
    assert CategoryTag.objects.filter(pk=data["id"]).exists()
