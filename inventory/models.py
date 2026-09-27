import secrets
from django.db import models
from django.core.validators import MinValueValidator


def generate_qr_token():
    return secrets.token_urlsafe(12)


class Product(models.Model):
    name = models.CharField("商品名", max_length=255)
    rakuten_url = models.URLField("楽天市場商品URL", max_length=1000, blank=True, default="")
    qr_token = models.CharField("QRトークン", max_length=64, unique=True, default=generate_qr_token, db_index=True)
    stock = models.IntegerField("現在庫", default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField("有効フラグ", default=True)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "商品"
        verbose_name_plural = "商品"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class InventoryHistory(models.Model):
    class ChangeType(models.TextChoices):
        USE = "USE", "商品使用"
        RESTOCK = "RESTOCK", "自動補充"
        ADJUST = "ADJUST", "在庫調整"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="inventory_histories", verbose_name="商品")
    change_type = models.CharField("変更種別", max_length=10, choices=ChangeType.choices)
    quantity = models.IntegerField("変動数量")
    created_at = models.DateTimeField("作成日時", auto_now_add=True)

    class Meta:
        verbose_name = "在庫変更履歴"
        verbose_name_plural = "在庫変更履歴"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name} - {self.get_change_type_display()} ({self.quantity:+d})"


class RestockSchedule(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="restock_schedules", verbose_name="商品")
    quantity = models.PositiveIntegerField("補充数量", default=1)
    scheduled_at = models.DateTimeField("補充予定日時")
    processed = models.BooleanField("処理済みフラグ", default=False)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)

    class Meta:
        verbose_name = "自動補充予定"
        verbose_name_plural = "自動補充予定"
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.product.name} - {self.scheduled_at} ({'処理済' if self.processed else '未処理'})"
