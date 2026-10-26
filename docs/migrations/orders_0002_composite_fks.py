"""Copy to backend/apps/orders/migrations/0002_composite_fks.py AFTER `makemigrations menu` and
`makemigrations orders` have created their new migrations (see the root README).

Same-restaurant integrity: an order's items, events and payments, and the menu item behind each
order line, must belong to the order's restaurant. Django cannot declare composite foreign keys,
so this is plain SQL. It relies on the (id, restaurant_id) unique constraints on orders_order and
menu_menuitem.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0001_initial"),
        ("menu", "__latest__"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE orders_orderitem ADD CONSTRAINT orders_item_order_same_restaurant
                    FOREIGN KEY (order_id, restaurant_id) REFERENCES orders_order (id, restaurant_id);
                ALTER TABLE orders_orderitem ADD CONSTRAINT orders_item_menuitem_same_restaurant
                    FOREIGN KEY (menu_item_id, restaurant_id) REFERENCES menu_menuitem (id, restaurant_id);
                ALTER TABLE orders_orderstatusevent ADD CONSTRAINT orders_event_order_same_restaurant
                    FOREIGN KEY (order_id, restaurant_id) REFERENCES orders_order (id, restaurant_id);
                ALTER TABLE orders_payment ADD CONSTRAINT orders_payment_order_same_restaurant
                    FOREIGN KEY (order_id, restaurant_id) REFERENCES orders_order (id, restaurant_id);
            """,
            reverse_sql="""
                ALTER TABLE orders_payment DROP CONSTRAINT orders_payment_order_same_restaurant;
                ALTER TABLE orders_orderstatusevent DROP CONSTRAINT orders_event_order_same_restaurant;
                ALTER TABLE orders_orderitem DROP CONSTRAINT orders_item_menuitem_same_restaurant;
                ALTER TABLE orders_orderitem DROP CONSTRAINT orders_item_order_same_restaurant;
            """,
        ),
    ]
