import pytest

from django.contrib.auth import get_user_model

from transactions.forms import TransactionForm
from entities.models import Entity
from transactions.models import CategoryTag


@pytest.mark.django_db
def test_transaction_form_uses_entity_destination_for_income_and_transfer(db):
    User = get_user_model()
    user = User.objects.create_user(username="u1", password="pass")
    ent_src = Entity.objects.create(user=user, entity_name="Source")
    ent_dst = Entity.objects.create(user=user, entity_name="Destination")

    # Create tags for both entities
    CategoryTag.objects.create(user=user, entity=ent_src, name="SrcCat")
    CategoryTag.objects.create(user=user, entity=ent_dst, name="DstCat")

    # For income, should pick destination entity
    form = TransactionForm(
        user=user, data={"transaction_type": "income", "entity_destination": ent_dst.id}
    )
    qs = form.fields["category"].queryset
    assert [t.name for t in qs] == ["DstCat"]

    # For transfer, also use destination
    form = TransactionForm(
        user=user,
        data={"transaction_type": "transfer", "entity_destination": ent_dst.id},
    )
    qs = form.fields["category"].queryset
    assert [t.name for t in qs] == ["DstCat"]


@pytest.mark.django_db
def test_transaction_form_uses_entity_source_for_expense(db):
    User = get_user_model()
    user = User.objects.create_user(username="u2", password="pass")
    ent_src = Entity.objects.create(user=user, entity_name="Source2")
    ent_dst = Entity.objects.create(user=user, entity_name="Destination2")

    CategoryTag.objects.create(user=user, entity=ent_src, name="SrcCat2")
    CategoryTag.objects.create(user=user, entity=ent_dst, name="DstCat2")

    form = TransactionForm(
        user=user, data={"transaction_type": "expense", "entity_source": ent_src.id}
    )
    qs = form.fields["category"].queryset
    assert [t.name for t in qs] == ["SrcCat2"]


def test_edit_form_includes_existing_category_even_if_scoped_out(db):
    """Ensure the edit form shows the existing CategoryTag even when the
    normal scoping/filtering would exclude it.
    """
    User = get_user_model()
    user = User.objects.create_user(username="u3", password="pass")
    ent = Entity.objects.create(user=user, entity_name="E1")

    # Create a tag that would be scoped to a different transaction_type
    tag = CategoryTag.objects.create(user=user, entity=ent, name="SpecialCat", transaction_type="income")

    # Create a transaction with a different type but attach the tag directly
    from transactions.models import Transaction

    tx = Transaction.objects.create(
        user=user,
        transaction_type="expense",
        entity_source=ent,
        entity_destination=ent,
        account_source=None,
        account_destination=None,
    )
    tx.categories.add(tag)

    # Build the form for editing this transaction
    form = TransactionForm(instance=tx, user=user)
    # The queryset should include the existing tag so it can render as selected
    qs_names = [t.name for t in form.fields["category"].queryset]
    assert "SpecialCat" in qs_names
    # Initial should be set to the attached category
    assert form.initial.get("category") == tag.pk
