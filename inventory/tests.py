from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.management import call_command

from inventory.models import Product, InventoryHistory, RestockSchedule


class InventoryTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.product_active = Product.objects.create(
            name="洗剤A",
            rakuten_url="https://item.rakuten.co.jp/test/detergent/",
            stock=2,
            is_active=True,
        )
        self.product_inactive = Product.objects.create(
            name="無効洗剤",
            rakuten_url="https://item.rakuten.co.jp/test/inactive/",
            stock=1,
            is_active=False,
        )

    # --- 商品テスト ---
    def test_product_registration(self):
        """商品登録"""
        response = self.client.post(reverse("manage_product_create"), {
            "name": "トイレットペーパー",
            "rakuten_url": "https://item.rakuten.co.jp/test/paper/",
            "stock": 3,
        })
        self.assertEqual(response.status_code, 302)
        p = Product.objects.get(name="トイレットペーパー")
        self.assertEqual(p.stock, 3)
        self.assertTrue(p.qr_token)
        # Verify initial stock adjustment history
        history = InventoryHistory.objects.filter(product=p, change_type=InventoryHistory.ChangeType.ADJUST).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.quantity, 3)

    def test_product_edit(self):
        """商品編集"""
        response = self.client.post(reverse("manage_product_edit", args=[self.product_active.id]), {
            "name": "洗剤A 改",
            "rakuten_url": "https://item.rakuten.co.jp/test/detergent_new/",
            "stock": 5,
            "is_active": True,
        })
        self.assertEqual(response.status_code, 302)
        self.product_active.refresh_from_db()
        self.assertEqual(self.product_active.name, "洗剤A 改")
        self.assertEqual(self.product_active.stock, 5)

        # ADJUST history check (2 -> 5 = +3)
        history = InventoryHistory.objects.filter(
            product=self.product_active,
            change_type=InventoryHistory.ChangeType.ADJUST
        ).order_by("-created_at").first()
        self.assertIsNotNone(history)
        self.assertEqual(history.quantity, 3)

    def test_product_deactivation(self):
        """商品無効化"""
        response = self.client.post(reverse("manage_product_edit", args=[self.product_active.id]), {
            "name": "洗剤A",
            "rakuten_url": self.product_active.rakuten_url,
            "stock": self.product_active.stock,
            "is_active": False,
        })
        self.assertEqual(response.status_code, 302)
        self.product_active.refresh_from_db()
        self.assertFalse(self.product_active.is_active)

        # Home screen should not display inactive product
        home_res = self.client.get(reverse("home"))
        self.assertNotIn("洗剤A", home_res.content.decode("utf-8"))

    # --- QRテスト ---
    def test_qr_identification(self):
        """正しいQRから商品を特定できる"""
        url = reverse("qr_process", args=[self.product_active.qr_token])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("洗剤A", response.content.decode("utf-8"))

    def test_nonexistent_qr_error(self):
        """存在しないQRでエラーになる"""
        url = reverse("qr_process", args=["invalid_token_123"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertIn("指定された商品が見つかりません。", response.content.decode("utf-8"))

    def test_inactive_qr_error(self):
        """無効な商品でエラーになる"""
        url = reverse("qr_process", args=[self.product_inactive.qr_token])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("この商品は現在使用できません。", response.content.decode("utf-8"))

    # --- 在庫 & 履歴 & 補充予定テスト ---
    def test_stock_decrement_2_to_1(self):
        """在庫2 → 1になる"""
        url = reverse("qr_process", args=[self.product_active.qr_token])
        response = self.client.post(url, {"action": "use"})
        self.assertEqual(response.status_code, 200)
        self.product_active.refresh_from_db()
        self.assertEqual(self.product_active.stock, 1)

        # USE history
        use_history = InventoryHistory.objects.filter(
            product=self.product_active,
            change_type=InventoryHistory.ChangeType.USE
        ).first()
        self.assertIsNotNone(use_history)
        self.assertEqual(use_history.quantity, -1)

        # RestockSchedule created 3 days later
        schedule = RestockSchedule.objects.filter(product=self.product_active).first()
        self.assertIsNotNone(schedule)
        self.assertEqual(schedule.quantity, 1)
        self.assertFalse(schedule.processed)

    def test_stock_decrement_1_to_0(self):
        """在庫1 → 0になる"""
        self.product_active.stock = 1
        self.product_active.save()

        url = reverse("qr_process", args=[self.product_active.qr_token])
        response = self.client.post(url, {"action": "use"})
        self.assertEqual(response.status_code, 200)
        self.product_active.refresh_from_db()
        self.assertEqual(self.product_active.stock, 0)
        self.assertIn("在庫がなくなりました", response.content.decode("utf-8"))

        # Restock schedule created
        self.assertEqual(RestockSchedule.objects.filter(product=self.product_active).count(), 1)

    def test_stock_0_does_not_become_negative(self):
        """在庫0 → -1にならない"""
        self.product_active.stock = 0
        self.product_active.save()

        url = reverse("qr_process", args=[self.product_active.qr_token])
        response = self.client.post(url, {"action": "use"})
        self.assertEqual(response.status_code, 200)
        self.product_active.refresh_from_db()
        self.assertEqual(self.product_active.stock, 0)
        self.assertIn("この商品の在庫はありません。", response.content.decode("utf-8"))

        # No new history or restock schedule created for stock 0 usage attempt
        self.assertEqual(InventoryHistory.objects.filter(product=self.product_active, change_type=InventoryHistory.ChangeType.USE).count(), 0)
        self.assertEqual(RestockSchedule.objects.filter(product=self.product_active).count(), 0)

    def test_multiple_restock_schedules_for_same_product(self):
        """同じ商品に複数の補充予定を登録できる"""
        url = reverse("qr_process", args=[self.product_active.qr_token])
        self.client.post(url, {"action": "use"}) # stock 2 -> 1
        self.client.post(url, {"action": "use"}) # stock 1 -> 0

        self.product_active.refresh_from_db()
        self.assertEqual(self.product_active.stock, 0)
        schedules = RestockSchedule.objects.filter(product=self.product_active)
        self.assertEqual(schedules.count(), 2)

    def test_process_restock_command(self):
        """期限到来した補充予定が処理される & 二重処理されない"""
        now = timezone.now()
        # Create a schedule that is due
        due_schedule = RestockSchedule.objects.create(
            product=self.product_active,
            quantity=1,
            scheduled_at=now - timedelta(hours=1),
            processed=False,
        )
        # Create a future schedule
        future_schedule = RestockSchedule.objects.create(
            product=self.product_active,
            quantity=1,
            scheduled_at=now + timedelta(days=2),
            processed=False,
        )

        initial_stock = self.product_active.stock

        # Execute command
        call_command("process_restock")

        self.product_active.refresh_from_db()
        self.assertEqual(self.product_active.stock, initial_stock + 1)

        due_schedule.refresh_from_db()
        future_schedule.refresh_from_db()
        self.assertTrue(due_schedule.processed)
        self.assertFalse(future_schedule.processed)

        # RESTOCK history check
        restock_history = InventoryHistory.objects.filter(
            product=self.product_active,
            change_type=InventoryHistory.ChangeType.RESTOCK
        ).first()
        self.assertIsNotNone(restock_history)
        self.assertEqual(restock_history.quantity, 1)

        # Running command again should not double process
        call_command("process_restock")
        self.product_active.refresh_from_db()
        self.assertEqual(self.product_active.stock, initial_stock + 1)

    def test_rakuten_link(self):
        """登録した楽天URLへ正しく遷移できる / 画面に存在する"""
        response = self.client.get(reverse("product_detail", args=[self.product_active.id]))
        self.assertIn(self.product_active.rakuten_url, response.content.decode("utf-8"))
