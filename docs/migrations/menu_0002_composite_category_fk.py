"""Copy to backend/apps/menu/migrations/0002_composite_category_fk.py AFTER `makemigrations menu` has
created 0001_initial.py (see the root README).

Same-restaurant integrity: an item's category must belong to the item's restaurant.

Django cannot declare composite foreign keys, so this is plain SQL. It relies on the
unique constraint (id, restaurant_id) that migration 0001 creates on the category table.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE menu_menuitem
                ADD CONSTRAINT menu_item_category_same_restaurant
                FOREIGN KEY (category_id, restaurant_id)
                REFERENCES menu_menucategory (id, restaurant_id)
                ON DELETE RESTRICT;
            """,
            reverse_sql="ALTER TABLE menu_menuitem DROP CONSTRAINT menu_item_category_same_restaurant;",
        ),
    ]
