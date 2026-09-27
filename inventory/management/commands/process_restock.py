from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from inventory.models import Product, InventoryHistory, RestockSchedule


class Command(BaseCommand):
    help = "期限に達した自動補充予定を処理し、在庫数を増やします。"

    def handle(self, *args, **options):
        now = timezone.now()
        schedules = RestockSchedule.objects.filter(
            scheduled_at__lte=now,
            processed=False
        ).select_related("product")

        count = 0
        for schedule in schedules:
            with transaction.atomic():
                # Re-fetch schedule with select_for_update to avoid double processing in concurrent runs
                sched = RestockSchedule.objects.select_for_update().filter(
                    id=schedule.id,
                    processed=False
                ).first()
                if not sched:
                    continue

                product = Product.objects.select_for_update().get(id=sched.product_id)
                product.stock += sched.quantity
                product.save(update_fields=["stock", "updated_at"])

                InventoryHistory.objects.create(
                    product=product,
                    change_type=InventoryHistory.ChangeType.RESTOCK,
                    quantity=sched.quantity,
                )

                sched.processed = True
                sched.save(update_fields=["processed"])
                count += 1

        self.stdout.write(self.style.SUCCESS(f"補充処理が完了しました。件数: {count}"))
